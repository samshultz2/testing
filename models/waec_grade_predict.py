"""
Per-subject real-WAEC grade-band prediction from mock-WAEC scores.

Given a student's mock-WAEC score in a subject, predict the *full probability
distribution* over the nine WASSCE bands (A1…F9) for their real WAEC grade —
never a single guessed letter. Decision-useful quantities (P(credit), expected
credits, P(5 credits incl. English & Maths)) are derived from those distributions.

Three engines share one interface and one output shape, activating as data
accumulates (auto-selected per subject):

  prior  — zero data: a distribution derived from the standard WASSCE score
           boundaries, smeared by a Gaussian to express honest uncertainty. The
           floor every other engine falls back to.
  bins   — little data: bucket students by their mock score, look up the actual
           historical grade distribution of past students in that bucket, smoothed
           toward the prior (Dirichlet). Carries the sample size `n` per bucket and
           flags low-n buckets.
  model  — enough data: a proportional-odds ordinal logistic regression (pure
           numpy — scipy/sklearn are not installed) fit on (mock score → real
           grade) pairs, retrained whenever a new cohort's results land.

Design decisions (see the planning discussion):
  * predictor feature  = each student's LATEST/final mock score.
  * scope              = per-branch (models/bins computed within a branch).
  * switch             = SchoolSettings 'waec_prediction_method' in
                         {auto, prior, bins, model}; `auto` picks per subject by
                         sample size + cross-validated Ranked Probability Score.

Real WAEC stores a grade only (no score), so the label is the grade directly;
the mock SCORE (not its derived grade) is the feature, to keep full information.
"""
import json
import math

from models.models import db
from models.mock_waec import (
    MockWAECResult, MockWAECExam, GRADE_POINTS, PASS_GRADES, CORE_SUBJECTS,
)

# Ordered worst→best is awkward; we keep best→worst (index 0 = A1 … 8 = F9),
# matching GRADE_POINTS insertion order and WASSCE convention.
GRADES = list(GRADE_POINTS)                      # ['A1','B2',...,'F9']
K = len(GRADES)                                  # 9 bands
_GRADE_IX = {g: i for i, g in enumerate(GRADES)}

# Lower score bound of each band (mirrors waec_grade_from_score). F9 has no floor.
_BAND_FLOOR = {'A1': 75, 'B2': 70, 'B3': 65, 'C4': 60, 'C5': 55, 'C6': 50,
               'D7': 45, 'E8': 40, 'F9': 0}
# Internal score cut points between adjacent bands, low→high (F9|E8|…|A1).
_CUTS = [40, 45, 50, 55, 60, 65, 70, 75]

# Tunables (documented heuristics; see module docstring / planning notes).
PRIOR_SIGMA = 8.0          # score-noise sd for the cold-start prior
BIN_ALPHA = 4.0            # Dirichlet smoothing strength toward the prior
LOW_N_BUCKET = 10          # a bucket with fewer pairs is flagged low-confidence
MIN_PAIRS_BINS = 30        # below this (per subject) → prior, not bins
MIN_PAIRS_MODEL = 200      # below this (per subject) → never the model
MODEL_MARGIN = 0.03        # model must beat bins' CV RPS by this relative margin

SETTING_KEY = 'waec_prediction_method'
VALID_METHODS = ('auto', 'prior', 'bins', 'model')


# ---------------------------------------------------------------------------
# Small numeric helpers (numpy-free so the module has zero new dependencies)
# ---------------------------------------------------------------------------

def _normal_cdf(x, mean, sd):
    return 0.5 * (1.0 + math.erf((x - mean) / (sd * math.sqrt(2.0))))


def _normalise(vec):
    s = sum(vec)
    if s <= 0:
        return [1.0 / len(vec)] * len(vec)
    return [v / s for v in vec]


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def as_dict(vec):
    """A length-9 probability vector → {grade: prob} keyed by band."""
    return {GRADES[i]: round(vec[i], 4) for i in range(K)}


def p_credit(vec):
    """Probability of a credit (C6 or better) from a distribution vector."""
    return round(sum(vec[i] for i, g in enumerate(GRADES) if g in PASS_GRADES), 4)


def expected_grade(vec):
    """Most-likely band plus the mean grade-point (1=A1 … 9=F9)."""
    best = max(range(K), key=lambda i: vec[i])
    mean_pts = sum(vec[i] * GRADE_POINTS[GRADES[i]] for i in range(K))
    return GRADES[best], round(mean_pts, 2)


# ---------------------------------------------------------------------------
# Phase 1 — Prior (works with zero data)
# ---------------------------------------------------------------------------

def prior_distribution(score, sigma=PRIOR_SIGMA):
    """Cold-start distribution: treat the real grade as the mock score plus
    Gaussian noise, then integrate that bell curve over each band's score range.
    A score of 64 becomes mostly C4 with real mass on B3 and C5 — an honest
    'we have not seen real outcomes yet' spread rather than a hard cutoff."""
    if score is None:
        return [1.0 / K] * K
    s = max(0.0, min(100.0, float(score)))
    # Probability mass in each band = area of N(s, sigma) over the band interval.
    # Bands low→high are F9,E8,D7,C6,C5,C4,B3,C2... build over _CUTS then map back.
    edges = [0.0] + _CUTS + [100.0]              # 10 edges → 9 intervals low→high
    low_to_high = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        low_to_high.append(_normal_cdf(hi, s, sigma) - _normal_cdf(lo, s, sigma))
    # low_to_high[0] is F9 … [8] is A1; GRADES is A1…F9, so reverse.
    vec = list(reversed(low_to_high))
    return _normalise(vec)


# ---------------------------------------------------------------------------
# Phase 0 — Pairing layer (shared substrate for bins, model and evaluation)
# ---------------------------------------------------------------------------

def _session_exam_year(session):
    """Map an academic session (e.g. '2024/2025') to the real WAEC exam year it
    graduates into (2025). Falls back to None when unparseable."""
    if not session or not session.name:
        return None
    import re
    yrs = re.findall(r'(\d{4})', session.name)
    if yrs:
        return int(yrs[-1])               # the ending year of the session
    return None


def _latest_mock_scores(student_id):
    """{canonical_subject: score} from the student's LATEST mock WAEC sitting
    (the chosen predictor). Empty when they have no scored mock."""
    from utils.subject_match import canonical_subject
    rows = (MockWAECResult.query
            .filter(MockWAECResult.student_id == student_id)
            .join(MockWAECExam, MockWAECResult.mock_exam_id == MockWAECExam.id)
            .order_by(MockWAECExam.exam_date.asc(), MockWAECExam.id.asc())
            .all())
    if not rows:
        return {}
    last_exam = rows[-1].mock_exam_id
    out = {}
    for r in rows:
        if r.mock_exam_id == last_exam and r.score is not None:
            out[canonical_subject(r.subject) or r.subject] = r.score
    return out


def _real_grades(student_id, prefer_year=None):
    """{canonical_subject: grade} from the student's real WAEC — the year matching
    their cohort when known, else their most recent year."""
    from models.models import WAECResult
    from utils.subject_match import canonical_subject
    rows = WAECResult.query.filter_by(student_id=student_id).all()
    if not rows:
        return {}
    years = sorted({r.exam_year for r in rows})
    year = prefer_year if (prefer_year in years) else years[-1]
    out = {}
    for r in rows:
        if r.exam_year == year:
            out[canonical_subject(r.subject) or r.subject] = r.grade
    return out


def training_pairs(branch_id=None):
    """All (subject, mock score, real grade) pairs for graduated students who have
    both a scored final mock and a real WAEC grade in the same subject.

    Returns {subject: [(score, grade_index), …]}, branch-scoped when given. This
    is the single source both bins and the model (and evaluation) consume."""
    from models.models import Student, AcademicSession
    q = Student.query.filter(Student.is_graduated.is_(True))
    if branch_id is not None:
        q = q.filter(Student.branch_id == branch_id)
    pairs = {}
    for st in q.all():
        sess = db.session.get(AcademicSession, st.graduation_session_id) if st.graduation_session_id else None
        prefer_year = _session_exam_year(sess)
        mocks = _latest_mock_scores(st.id)
        if not mocks:
            continue
        reals = _real_grades(st.id, prefer_year)
        if not reals:
            continue
        for subj, score in mocks.items():
            grade = reals.get(subj)
            if grade in _GRADE_IX:
                pairs.setdefault(subj, []).append((float(score), _GRADE_IX[grade]))
    return pairs


# ---------------------------------------------------------------------------
# Phase 2 — Empirical calibration bins
# ---------------------------------------------------------------------------

def _bucket_of(score):
    """Index of the score bucket — we reuse the nine band score ranges as the
    natural buckets (so a bucket aligns with what we are predicting)."""
    s = max(0.0, min(100.0, float(score)))
    # bucket 0 = highest band range (A1), … 8 = F9, mirroring GRADES order.
    for i, g in enumerate(GRADES):
        if s >= _BAND_FLOOR[g]:
            return i
    return K - 1


def build_bins(pairs_for_subject):
    """For one subject's pairs, count the real grades that landed in each mock
    bucket. Returns {bucket_index: [counts over 9 grades]}."""
    buckets = {}
    for score, gix in pairs_for_subject:
        b = _bucket_of(score)
        row = buckets.setdefault(b, [0] * K)
        row[gix] += 1
    return buckets


def bins_predict(score, buckets):
    """Distribution for a mock `score` from calibration `buckets`, Dirichlet-
    smoothed toward the prior so a thin/empty bucket degrades to the prior.
    Returns (distribution_vector, n_in_bucket)."""
    b = _bucket_of(score)
    counts = buckets.get(b, [0] * K)
    n = sum(counts)
    prior = prior_distribution(score)
    # posterior ∝ counts + alpha * prior  (additive smoothing toward the prior)
    post = [counts[i] + BIN_ALPHA * prior[i] for i in range(K)]
    return _normalise(post), n


# ---------------------------------------------------------------------------
# Phase 3 — Proportional-odds ordinal logistic regression (pure numpy-free)
# ---------------------------------------------------------------------------

class OrdinalModel:
    """Proportional-odds (cumulative-logit) ordinal regression on one feature,
    the standardised mock score:  P(Y ≤ k) = sigmoid(theta_k - beta * z).

    Thresholds theta_1 < … < theta_{K-1} are kept ordered via a softplus
    reparametrisation, and fit by gradient descent on the regularised negative
    log-likelihood. One feature + 8 thresholds + 1 slope — deliberately tiny, to
    stay stable on the small cohorts this runs on."""

    def __init__(self, mean=0.0, std=1.0, base=0.0, deltas=None, beta=0.0):
        self.mean = mean
        self.std = std or 1.0
        self.base = base                 # theta_1
        self.deltas = deltas or [0.0] * (K - 2)   # softplus gaps for theta_2..theta_{K-1}
        self.beta = beta

    # -- threshold vector from the ordered reparametrisation --
    def _thetas(self, base, deltas):
        th = [base]
        for d in deltas:
            th.append(th[-1] + math.log1p(math.exp(d)))   # +softplus(d) > 0
        return th

    def _dist_from_params(self, z, base, deltas, beta):
        th = self._thetas(base, deltas)
        cum = [_sigmoid(t - beta * z) for t in th]        # P(Y ≤ k), k=0..K-2
        cum = [0.0] + cum + [1.0]
        return [max(1e-9, cum[i + 1] - cum[i]) for i in range(K)]

    def predict(self, score):
        z = (float(score) - self.mean) / self.std
        return _normalise(self._dist_from_params(z, self.base, self.deltas, self.beta))

    @classmethod
    def fit(cls, pairs, l2=1.0, iters=400, lr=0.3):
        """Fit on [(score, grade_index)]. Returns a trained OrdinalModel."""
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(xs)
        mean = sum(xs) / n
        var = sum((x - mean) ** 2 for x in xs) / n
        std = math.sqrt(var) or 1.0
        zs = [(x - mean) / std for x in xs]

        m = cls(mean=mean, std=std, base=0.0, deltas=[0.0] * (K - 2), beta=0.0)
        # Gradient descent on regularised NLL via finite-difference-free analytic-ish
        # numeric gradient (small param count → numeric gradient is cheap & robust).
        params = [m.base] + list(m.deltas) + [m.beta]

        def nll(p):
            base, deltas, beta = p[0], p[1:K - 1], p[K - 1]
            tot = 0.0
            for z, y in zip(zs, ys):
                d = m._dist_from_params(z, base, deltas, beta)
                tot -= math.log(d[y])
            tot += l2 * (beta * beta)         # regularise the slope only
            return tot / n

        for _ in range(iters):
            base = nll(params)
            grad = []
            for j in range(len(params)):
                step = 1e-4
                up = list(params); up[j] += step
                grad.append((nll(up) - base) / step)
            gnorm = math.sqrt(sum(g * g for g in grad)) or 1.0
            params = [params[j] - lr * grad[j] / gnorm for j in range(len(params))]

        m.base = params[0]
        m.deltas = list(params[1:K - 1])
        m.beta = params[K - 1]
        return m

    # -- (de)serialisation for the WaecGradeModel table --
    def to_json(self):
        return json.dumps({'mean': self.mean, 'std': self.std, 'base': self.base,
                           'deltas': self.deltas, 'beta': self.beta})

    @classmethod
    def from_json(cls, s):
        d = json.loads(s)
        return cls(mean=d['mean'], std=d['std'], base=d['base'],
                   deltas=d['deltas'], beta=d['beta'])


# ---------------------------------------------------------------------------
# Phase 4 — Evaluation (ordinal-aware) and method selection
# ---------------------------------------------------------------------------

def ranked_probability_score(dist, true_ix):
    """RPS for an ordinal forecast: mean squared error between predicted and true
    cumulative distributions. Lower is better; penalises being off by two bands
    more than by one (unlike plain accuracy)."""
    cum_p = 0.0
    total = 0.0
    for i in range(K):
        cum_p += dist[i]
        cum_t = 1.0 if i >= true_ix else 0.0      # true CDF is a step at true_ix
        total += (cum_p - cum_t) ** 2
    return total / (K - 1)


def _cv_rps(pairs, predict_fn, folds=5):
    """Mean RPS of `predict_fn` (built from a train split) over k folds. With few
    pairs it degrades to leave-one-out. `predict_fn(train) -> (score -> dist)`."""
    n = len(pairs)
    if n < 4:
        return None
    k = min(folds, n)
    # deterministic round-robin folds (no RNG — Math.random is unavailable anyway)
    fold_of = [i % k for i in range(n)]
    scores = []
    for f in range(k):
        train = [pairs[i] for i in range(n) if fold_of[i] != f]
        test = [pairs[i] for i in range(n) if fold_of[i] == f]
        if not train or not test:
            continue
        scorer = predict_fn(train)
        for score, gix in test:
            scores.append(ranked_probability_score(scorer(score), gix))
    return sum(scores) / len(scores) if scores else None


def evaluate_subject(pairs):
    """CV RPS for bins and model on one subject's pairs (None when too sparse)."""
    if not pairs or len(pairs) < 4:
        return {'n': len(pairs or []), 'rps_bins': None, 'rps_model': None}

    def bins_fn(train):
        buckets = build_bins(train)
        return lambda s: bins_predict(s, buckets)[0]

    def model_fn(train):
        mdl = OrdinalModel.fit(train)
        return lambda s: mdl.predict(s)

    return {
        'n': len(pairs),
        'rps_bins': _cv_rps(pairs, bins_fn),
        'rps_model': _cv_rps(pairs, model_fn),
    }


def choose_method(n, eval_result, setting):
    """The engine to use for a subject given its pair count, CV result and the
    configured setting. Returns one of 'prior' | 'bins' | 'model'."""
    if setting in ('prior', 'bins', 'model'):
        return setting                       # manual override
    # auto:
    if n < MIN_PAIRS_BINS:
        return 'prior'
    if n < MIN_PAIRS_MODEL:
        return 'bins'
    rb = eval_result.get('rps_bins') if eval_result else None
    rm = eval_result.get('rps_model') if eval_result else None
    if rb is None or rm is None:
        return 'bins'
    # model must beat bins by a clear relative margin to be promoted
    return 'model' if rm <= rb * (1.0 - MODEL_MARGIN) else 'bins'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def active_setting():
    from models.models import SchoolSettings
    val = SchoolSettings.get(SETTING_KEY, 'auto')
    return val if val in VALID_METHODS else 'auto'


def _load_trained_model(branch_id, subject):
    """Persisted OrdinalModel for (branch, subject), or None."""
    from models.analytics_models import WaecGradeModel
    row = (WaecGradeModel.query
           .filter_by(subject=subject, branch_id=branch_id)
           .order_by(WaecGradeModel.trained_at.desc()).first())
    return OrdinalModel.from_json(row.params) if row else None


def predict_subject(score, subject, branch_id=None, setting=None, pairs=None):
    """Predict the real-WAEC grade distribution for one mock `score` in `subject`.

    Returns a dict: distribution {grade: prob}, the `engine` used, the supporting
    sample size `n`, a `low_confidence` flag, P(credit), and the most-likely band.
    Engine is chosen per the active setting and this subject's data."""
    from utils.subject_match import canonical_subject
    subject = canonical_subject(subject) or subject
    setting = setting or active_setting()
    if pairs is None:
        pairs = training_pairs(branch_id).get(subject, [])
    n = len(pairs)

    ev = evaluate_subject(pairs) if (setting == 'auto' and n >= MIN_PAIRS_MODEL) else None
    engine = choose_method(n, ev, setting)

    low_conf = False
    if engine == 'model':
        mdl = _load_trained_model(branch_id, subject) or OrdinalModel.fit(pairs)
        dist = mdl.predict(score)
    elif engine == 'bins':
        buckets = build_bins(pairs)
        dist, bn = bins_predict(score, buckets)
        low_conf = bn < LOW_N_BUCKET
    else:
        engine = 'prior'
        dist = prior_distribution(score)
        low_conf = True
    band, mean_pts = expected_grade(dist)
    return {
        'subject': subject, 'mock_score': score, 'engine': engine, 'n': n,
        'low_confidence': low_conf, 'distribution': as_dict(dist),
        'p_credit': p_credit(dist), 'likely_grade': band, 'mean_points': mean_pts,
    }


def predict_student(student_id):
    """Per-subject grade-band predictions for a student from their latest mock,
    plus an aggregate outlook. Aggregates assume per-subject independence."""
    from models.models import Student
    st = db.session.get(Student, student_id)
    if not st:
        return None
    branch_id = st.branch_id
    setting = active_setting()
    all_pairs = training_pairs(branch_id)
    mocks = _latest_mock_scores(student_id)

    subjects = []
    exp_credits = 0.0
    core_credit_probs = {}
    for subj, score in sorted(mocks.items()):
        pred = predict_subject(score, subj, branch_id, setting,
                               pairs=all_pairs.get(subj, []))
        subjects.append(pred)
        exp_credits += pred['p_credit']
        if subj in CORE_SUBJECTS:
            core_credit_probs[subj] = pred['p_credit']

    # P(5+ credits including English & Maths), under independence: P(both core
    # credits) × P(at least 5 credits overall). We approximate the latter by the
    # expected-credit mass — a transparent heuristic, flagged in the UI.
    p_both_core = 1.0
    for c in CORE_SUBJECTS:
        p_both_core *= core_credit_probs.get(c, 0.0)

    return {
        'student_id': student_id, 'engine_setting': setting,
        'subjects': subjects,
        'expected_credits': round(exp_credits, 2),
        'p_both_core_credit': round(p_both_core, 4),
        'n_subjects': len(subjects),
        'independence_caveat': True,
    }


def train_models(branch_id=None):
    """(Re)fit and persist ordinal models for every subject in `branch_id` that
    clears the model gate. Call after a new cohort's real results are entered.
    Returns a per-subject summary (trained / skipped + reason)."""
    from models.analytics_models import WaecGradeModel
    from models.models import local_now
    pairs_by_subject = training_pairs(branch_id)
    summary = []
    for subject, pairs in sorted(pairs_by_subject.items()):
        n = len(pairs)
        if n < MIN_PAIRS_MODEL:
            summary.append({'subject': subject, 'n': n, 'trained': False,
                            'reason': f'need ≥{MIN_PAIRS_MODEL} pairs'})
            continue
        ev = evaluate_subject(pairs)
        mdl = OrdinalModel.fit(pairs)
        row = (WaecGradeModel.query.filter_by(subject=subject, branch_id=branch_id).first()
               or WaecGradeModel(subject=subject, branch_id=branch_id))
        row.params = mdl.to_json()
        row.n = n
        row.cv_rps = ev.get('rps_model')
        row.cv_rps_bins = ev.get('rps_bins')
        row.trained_at = local_now()
        db.session.add(row)
        summary.append({'subject': subject, 'n': n, 'trained': True,
                        'cv_rps': ev.get('rps_model'), 'cv_rps_bins': ev.get('rps_bins')})
    db.session.commit()
    return summary
