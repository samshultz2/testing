import React, { useEffect, useState } from 'react';
import { csrfToken } from '../lib/api';
import { NavCtx, useSection } from '../lib/section';
import { ErrorBoundary } from '../components/ui';

const money = (n) => '₦' + Math.round(Number(n) || 0).toLocaleString();
const initials = (name) => (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const TABS = [
  { k: 'home', label: 'Home', icon: 'fa-house' },
  { k: 'results', label: 'Results', icon: 'fa-file-lines' },
  { k: 'fees', label: 'Fees', icon: 'fa-wallet' },
  { k: 'more', label: 'More', icon: 'fa-grip' },
];
const gradeTone = (g) => {
  const c = (g || '').toUpperCase()[0];
  return c === 'A' ? 'a' : c === 'B' ? 'b' : c === 'C' ? 'c' : c === 'D' || c === 'E' || c === 'P' ? 'd' : c === 'F' ? 'f' : '';
};

function tabFromHash() {
  const h = (window.location.hash || '').slice(1);
  return TABS.some((t) => t.k === h) ? h : 'home';
}

function Header({ d }) {
  const sibs = d.siblings || [];
  return (
    <header className="pp-top">
      <div className="pp-wrap">
        <div className="pp-school">
          {d.school && d.school.logo_url
            ? <img src={d.school.logo_url} alt="" />
            : <span className="pp-school-ic" aria-hidden="true"><i className="fas fa-school" /></span>}
          <span>{(d.school && d.school.name) || 'Parent portal'}</span>
          <a className="pp-out" href={d.urls.logout} aria-label="Sign out"><i aria-hidden="true" className="fas fa-right-from-bracket" /><span> Sign out</span></a>
        </div>
        <div className="pp-child">
          <span className="pp-av" aria-hidden="true">{initials(d.student.full_name)}</span>
          <div className="pp-child-t">
            <h1>{d.student.full_name}</h1>
            <p>{[d.student.class_name, d.student.student_id].filter(Boolean).join(' · ')}</p>
          </div>
        </div>
        {sibs.length > 1 && (
          <nav className="pp-kids" aria-label="Your children">
            {sibs.map((s) => s.is_current
              ? <span key={s.id} className="on" aria-current="page"><span className="pp-av sm" aria-hidden="true">{initials(s.full_name)}</span>{s.full_name}</span>
              : <a key={s.id} href={s.switch_url}><span className="pp-av sm" aria-hidden="true">{initials(s.full_name)}</span>{s.full_name}</a>)}
          </nav>
        )}
      </div>
    </header>
  );
}

function Terms({ d, go }) {
  if (!d.terms || d.terms.length < 2) return null;
  return (
    <div className="pp-terms" role="radiogroup" aria-label="Term">
      {d.terms.map((t) => (
        <button key={t.id} type="button" role="radio" aria-checked={t.id === d.term_id} className={t.id === d.term_id ? 'on' : ''}
                onClick={() => t.id !== d.term_id && go(`${d.urls.self}?term_id=${t.id}${window.location.hash}`)}>{t.name}</button>
      ))}
    </div>
  );
}

function Flashes({ d }) {
  const [list, setList] = useState(d.flashes || []);
  if (!list.length) return null;
  return list.map((f, i) => (
    <div key={i} role="status" className={`pp-flash ${f.category}`}>
      <i aria-hidden="true" className={'fas ' + (f.category === 'success' ? 'fa-circle-check' : f.category === 'error' ? 'fa-circle-exclamation' : 'fa-circle-info')} />
      <span>{f.message}</span>
      <button type="button" aria-label="Dismiss" onClick={() => setList(list.filter((_, j) => j !== i))}><i aria-hidden="true" className="fas fa-xmark" /></button>
    </div>
  ));
}

function ResultState({ d }) {
  if (d.report) return null;
  if (d.needs_card) {
    return (
      <div className="pp-card pp-locked">
        <span className="ic"><i aria-hidden="true" className="fas fa-lock" /></span>
        <div><b>This term's result is ready</b><p>Unlock it once with a scratch card from the school. After that it stays here for you.</p></div>
        <a href={d.urls.result_checker} className="pp-btn primary" data-native><i aria-hidden="true" className="fas fa-ticket" /> Unlock with scratch card</a>
      </div>
    );
  }
  return (
    <div className="pp-card pp-empty"><i aria-hidden="true" className="fas fa-hourglass-half" />
      <p>Results for this term aren't out yet. They'll appear here once the school releases them.</p></div>
  );
}

function Home({ d, setTab }) {
  const r = d.report, b = d.bill;
  const owing = b && b.balance > 0.005;
  return (
    <>
      <div className="pp-tiles">
        <button type="button" className={'pp-tile ' + (b ? (owing ? 'bad' : 'good') : '')} onClick={() => setTab('fees')}>
          <span className="l">Fee balance</span>
          <span className="v">{b ? money(b.balance) : '—'}</span>
          <span className="s">{b ? (owing ? `of ${money(b.payable)} owed` : 'Fully paid') : 'No fee record'}</span>
        </button>
        <div className="pp-tile">
          <span className="l">Attendance</span>
          <span className="v">{d.attendance != null ? `${d.attendance}%` : '—'}</span>
          <span className="s">{d.attendance != null ? 'this term' : 'not recorded yet'}</span>
        </div>
        <button type="button" className="pp-tile" onClick={() => setTab('results')}>
          <span className="l">{r ? 'Position' : 'Results'}</span>
          <span className="v">{r ? (r.position || '—') : (d.needs_card ? 'Ready' : '—')}</span>
          <span className="s">{r ? `average ${r.average} · ${r.overall_grade}` : (d.needs_card ? 'tap to unlock' : 'not released yet')}</span>
        </button>
      </div>
      {!r && <ResultState d={d} />}
      {r && (
        <button type="button" className="pp-card pp-go" onClick={() => setTab('results')}>
          <span className="ic good"><i aria-hidden="true" className="fas fa-file-circle-check" /></span>
          <span className="t"><b>Report card is ready</b><small>{r.subjects.length} subjects · average {r.average}</small></span>
          <i aria-hidden="true" className="fas fa-chevron-right" />
        </button>
      )}
      {d.announcements.length > 0 && (
        <section className="pp-card">
          <h2><i aria-hidden="true" className="fas fa-bullhorn" /> From the school</h2>
          <ul className="pp-ann">
            {d.announcements.slice(0, 3).map((a, i) => (
              <li key={i}>{a.is_pinned && <span className="pp-pin">Pinned</span>}<b>{a.title}</b><p>{a.body}</p></li>
            ))}
          </ul>
          {d.announcements.length > 3 && <button type="button" className="pp-link" onClick={() => setTab('more')}>See all {d.announcements.length}</button>}
        </section>
      )}
    </>
  );
}

function Results({ d }) {
  const r = d.report;
  if (!r) return <ResultState d={d} />;
  return (
    <>
      <div className="pp-card pp-sum">
        <div><span className="l">Position</span><b>{r.position || '—'}</b></div>
        <div><span className="l">Average</span><b>{r.average}</b></div>
        <div><span className="l">Grade</span><b>{r.overall_grade || '—'}</b></div>
        <a href={r && d.urls.report_pdf} className="pp-btn" data-native><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>
      </div>
      <section className="pp-card flush">
        <h2 className="pad"><i aria-hidden="true" className="fas fa-book-open" /> Subjects</h2>
        <ul className="pp-subj">
          {r.subjects.map((row, i) => (
            <li key={i}>
              <div className="h"><b>{row.name}</b><span className={'pp-grade ' + gradeTone(row.grade)}>{row.grade || '–'}</span><strong>{row.total}</strong></div>
              <div className="parts">
                {r.assessment_types.map((at) => (
                  <span key={at.id}><small>{at.label}</small>{row.assessments[String(at.id)] != null ? row.assessments[String(at.id)] : '–'}</span>
                ))}
                {row.remark && <em>{row.remark}</em>}
              </div>
            </li>
          ))}
        </ul>
      </section>
      {r.affective.length > 0 && (
        <section className="pp-card">
          <h2><i aria-hidden="true" className="fas fa-hand-holding-heart" /> Behaviour</h2>
          <ul className="pp-traits">
            {r.affective.map((a, i) => (
              <li key={i}><span>{a.label}</span>
                <span className="dots" aria-label={`${a.rating} of 5`}>{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= a.rating ? 'on' : ''} />)}</span>
                <small>{a.rating_label}</small></li>
            ))}
          </ul>
        </section>
      )}
      {(r.teacher_comment || r.principal_comment) && (
        <section className="pp-card">
          <h2><i aria-hidden="true" className="fas fa-comment-dots" /> Comments</h2>
          {r.teacher_comment && <blockquote><small>Form teacher</small>{r.teacher_comment}</blockquote>}
          {r.principal_comment && <blockquote><small>Principal</small>{r.principal_comment}</blockquote>}
        </section>
      )}
      <p className="pp-tip"><i aria-hidden="true" className="fas fa-wifi" /> Once opened, this page works offline, and the PDF can be saved to your phone.</p>
    </>
  );
}

function Fees({ d }) {
  const b = d.bill;
  const [amount, setAmount] = useState(b ? Math.round(b.balance) : 0);
  if (!b) return <div className="pp-card pp-empty"><i aria-hidden="true" className="fas fa-receipt" /><p>No fee record for this term.</p></div>;
  const owing = b.balance > 0.005;
  const pct = b.payable ? Math.min(100, Math.round((b.paid / b.payable) * 100)) : 100;
  const presets = owing ? [...new Set([Math.round(b.balance), Math.round(b.balance / 2)].filter((v) => v >= 100))] : [];
  return (
    <>
      <div className={'pp-card pp-bal ' + (owing ? 'owe' : 'ok')}>
        <span className="l">{owing ? 'Outstanding balance' : 'Fees fully paid'}</span>
        <b>{money(b.balance)}</b>
        <div className="bar" role="img" aria-label={`${pct}% paid`}><i style={{ width: pct + '%' }} /></div>
        <div className="row"><span>Paid {money(b.paid)}</span><span>Billed {money(b.payable)}</span></div>
      </div>
      {owing && d.pay_enabled && (
        <form className="pp-card pp-pay" method="POST" action={d.urls.pay}>
          <h2><i aria-hidden="true" className="fas fa-credit-card" /> Pay online</h2>
          <input type="hidden" name="_csrf_token" value={csrfToken()} />
          <input type="hidden" name="term_id" value={d.term_id || ''} />
          <div className="presets">
            {presets.map((v) => (
              <button type="button" key={v} className={Number(amount) === v ? 'on' : ''} onClick={() => setAmount(v)}>
                {v === Math.round(b.balance) ? 'Full balance' : 'Half'}<b>{money(v)}</b></button>
            ))}
          </div>
          <label className="pp-amt"><span>Amount (₦)</span>
            <input type="number" inputMode="numeric" name="amount" min="100" step="50" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
          <button type="submit" className="pp-btn primary wide" disabled={!(Number(amount) >= 100)}>
            <i aria-hidden="true" className="fas fa-lock" /> Pay {Number(amount) >= 100 ? money(amount) : ''} securely</button>
          <small className="pp-muted">You'll be taken to the payment page and brought back here. Your receipt appears once it's confirmed.</small>
        </form>
      )}
      {owing && !d.pay_enabled && (
        <div className="pp-card pp-note"><i aria-hidden="true" className="fas fa-circle-info" /><span>Online payment isn't set up for this school yet. Please pay at the school office or by the school's bank details.</span></div>
      )}
    </>
  );
}

function More({ d }) {
  const a = d.aspiration;
  const first = (d.student.full_name || '').split(' ').slice(-1)[0] || 'your child';
  return (
    <>
      <section className="pp-card flush">
        <h2 className="pad"><i aria-hidden="true" className="fas fa-grip" /> More for {first}</h2>
        <div className="pp-links">
          {d.urls.result_checker && <a href={d.urls.result_checker} data-native><span className="ic"><i aria-hidden="true" className="fas fa-ticket" /></span><span className="t"><b>Check a result with a scratch card</b><small>Enter a card PIN to view a released result</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a>}
          {d.urls.cbt_portal && <a href={d.urls.cbt_portal} data-native><span className="ic"><i aria-hidden="true" className="fas fa-laptop-code" /></span><span className="t"><b>Take a CBT exam</b><small>Sign in to an online test scheduled for today</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a>}
          <a href={d.urls.logout}><span className="ic"><i aria-hidden="true" className="fas fa-right-from-bracket" /></span><span className="t"><b>Sign out</b><small>Leave the parent portal on this device</small></span><i aria-hidden="true" className="fas fa-chevron-right" /></a>
        </div>
      </section>
      {a && (
        <section className="pp-card">
          <h2><i aria-hidden="true" className="fas fa-graduation-cap" /> University goal</h2>
          <b className="pp-goal">{a.course || 'Target course'}{a.university ? ` — ${a.university}` : ''}</b>
          {a.department && <p className="pp-muted">{a.department}</p>}
          {a.status_label && <span className={'pp-pill ' + ({ ON_TRACK: 'good', CLOSE: 'mid', OFF_TRACK: 'bad' }[a.status] || '')}>{a.status_label}</span>}
          {a.target != null && a.projected != null && (
            <p className="pp-muted">Projected JAMB {a.projected} against a target of {a.target}{a.gap != null && a.gap > 0 ? ` · ${a.gap} to go` : ' · target met'}</p>)}
          {a.admission_status && <p className="pp-muted">Admission: <b>{a.admission_status}</b>{a.admitted_university ? ` — ${a.admitted_university}` : ''}{a.admitted_course ? ` (${a.admitted_course})` : ''}</p>}
        </section>
      )}
      {d.announcements.length > 0 && (
        <section className="pp-card">
          <h2><i aria-hidden="true" className="fas fa-bullhorn" /> Announcements</h2>
          <ul className="pp-ann">{d.announcements.map((x, i) => <li key={i}>{x.is_pinned && <span className="pp-pin">Pinned</span>}<b>{x.title}</b><p>{x.body}</p></li>)}</ul>
        </section>
      )}
    </>
  );
}

function Shell({ d, go }) {
  const [tab, setTabState] = useState(tabFromHash);
  const setTab = (k) => {
    setTabState(k);
    try { window.history.replaceState(null, '', '#' + k); } catch (e) { /* ignore */ }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  useEffect(() => {
    const on = () => setTabState(tabFromHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  const owing = d.bill && d.bill.balance > 0.005;
  const badge = { fees: owing ? '!' : null, results: d.needs_card ? '•' : null };
  return (
    <div className="pp">
      <Header d={d} />
      <nav className="pp-tabs" aria-label="Sections">
        <div className="pp-wrap">
          {TABS.map((t) => (
            <button key={t.k} type="button" className={tab === t.k ? 'on' : ''} aria-current={tab === t.k ? 'page' : undefined} onClick={() => setTab(t.k)}>
              <i aria-hidden="true" className={'fas ' + t.icon} /><span>{t.label}</span>{badge[t.k] && <em aria-hidden="true">{badge[t.k]}</em>}
            </button>
          ))}
        </div>
      </nav>
      <main className="pp-wrap pp-main">
        <Flashes d={d} />
        {tab !== 'more' && <Terms d={d} go={go} />}
        {tab === 'home' && <Home d={d} setTab={setTab} />}
        {tab === 'results' && <Results d={d} />}
        {tab === 'fees' && <Fees key={d.term_id} d={d} />}
        {tab === 'more' && <More d={d} />}
      </main>
    </div>
  );
}

export default function ParentApp({ data }) {
  const { data: d, go } = useSection(data);
  return (
    <NavCtx.Provider value={{ go, refresh: () => go(window.location.href, { replace: true }) }}>
      <ErrorBoundary><Shell d={d} go={go} /></ErrorBoundary>
    </NavCtx.Provider>
  );
}
