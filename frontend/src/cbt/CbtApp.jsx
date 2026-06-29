import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, SectionShell, SectionTabs, Empty, Table } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['add_exam', 'fa-circle-plus', 'Exams'],
  ['bank', 'fa-layer-group', 'Question Bank'], ['passwords', 'fa-key', 'Student Passwords'],
  ['settings', 'fa-user-shield', 'Supervisor'], ['lab_setup', 'fa-desktop', 'Lab Setup'],
];
// Pages that should highlight the "Exams" tab.
const TAB_FOR = { dashboard: 'dashboard', exam_form: 'add_exam', results: 'add_exam', settings: 'settings', lab_setup: 'lab_setup' };

function Tabs({ d }) {
  const nav = useNav();
  return (
    <div className="fin-tabs">
      {TABS.map(([key, icon, label]) => {
        const active = (TAB_FOR[d.page] || d.page) === key;
        const href = d.nav[key];
        return <a key={key} href={href} className={'fin-tab' + (active ? ' active' : '')}
          onClick={(e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); nav.go(href); }}>
          <i aria-hidden="true" className={'fas ' + icon} /> {label}</a>;
      })}
      <a href={d.nav.portal} target="_blank" rel="noopener" className="fin-tab"><i aria-hidden="true" className="fas fa-up-right-from-square" /> Test Portal</a>
    </div>
  );
}

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const nav = useNav();
  const kpis = [['blue', 'fa-file-pen', d.total, 'Exams'], ['green', 'fa-globe', d.published, 'Published'],
    ['amber', 'fa-calendar-day', d.today_count, 'Active today'], ['teal', 'fa-user-check', d.attempts, 'Submissions']];
  return (
    <>
      <div className="page-header"><h1>CBT / Online Tests</h1>
        <div className="page-header-actions">
          <a href={d.urls.export_all} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> All Results</a>
          <a href={d.urls.add} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> New Exam</a>
        </div>
      </div>
      <Tabs d={d} />
      <div className="card mb-3"><div className="card-body"><form className="filter-form">
        <div className="form-group"><label className="form-label">Term</label>
          <select className="form-control" value={d.show_all ? 'all' : d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })}>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            <option value="all">All terms (history)</option></select></div>
      </form></div></div>
      <div className="kpi-row">{kpis.map(([c, ic, v, l]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div><div><div className="v">{v}</div><div className="l">{l}</div></div></div>))}
      </div>
      <div className="card"><div className="card-header"><h3>All Exams</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(e) => e.id} rows={d.exams}
            empty={<Empty icon="fa-file-pen" title="No exams yet"><p>Create an online test, add questions, set the access password and publish.</p><a href={d.urls.add} className="btn btn-primary mt-2">New Exam</a></Empty>}
            columns={[
              { key: 'title', label: 'Title', render: (e) => <a href={e.detail_url}><strong>{e.title}</strong></a> },
              { key: 'subject', label: 'Subject', render: (e) => e.subject },
              { key: 'class', label: 'Class', render: (e) => e.class_name },
              { key: 'date', label: 'Date', render: (e) => e.exam_date },
              { key: 'qs', label: 'Qs', render: (e) => e.question_count },
              { key: 'status', label: 'Status', render: (e) => <span className={'badge ' + (e.is_published ? 'badge-success' : 'badge-secondary')}>{e.is_published ? 'Published' : 'Draft'}</span> },
              { key: 'act', label: '', render: (e) => (
                <div className="d-flex gap-1 justify-end">
                  <a href={e.detail_url} className="btn btn-secondary btn-sm" title="Manage"><i aria-hidden="true" className="fas fa-pen" /></a>
                  <a href={e.results_url} className="btn btn-secondary btn-sm" title="Results"><i aria-hidden="true" className="fas fa-chart-bar" /></a>
                </div>) },
            ]} />
        </div></div>
    </>
  );
}

// ---- Settings --------------------------------------------------------------
function Settings({ d, notify }) {
  const nav = useNav();
  const [pin, setPin] = useState(d.supervisor_pin);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, { supervisor_pin: pin });
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>CBT Settings</h1></div>
      <Tabs d={d} />
      <div className="card" style={{ maxWidth: 560 }}>
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-user-shield" /> Supervisor override</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm">If a supervisor needs to help a student during an exam (e.g. a network or laptop issue), they enter this PIN on the student's screen to <strong>pause the lockdown</strong> for a few minutes — leaving fullscreen during the pause is logged but <strong>not counted</strong> as a violation. Each unlock is recorded on the student's attempt.</p>
          <form onSubmit={submit}>
            <fieldset disabled={!d.is_admin} style={{ border: 0, padding: 0, margin: 0 }}>
              <div className="form-group"><label className="form-label">Supervisor PIN</label>
                <input type="text" className="form-control" style={{ maxWidth: 200 }} placeholder="e.g. 4827" autoComplete="off" value={pin} onChange={(e) => setPin(e.target.value)} />
                <span className="form-hint d-block">Leave blank to disable the override. Keep it private to invigilators.</span></div>
              <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
            </fieldset>
            {!d.is_admin && <p className="text-muted text-sm mt-2">Only admins can change this.</p>}
          </form>
        </div></div>
    </>
  );
}

// ---- Lab setup -------------------------------------------------------------
const OS_CMDS = {
  win: [['Chrome — create a desktop shortcut with this target (or run in Command Prompt):',
    '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --kiosk --disable-pinch --overscroll-history-navigation=0 --disable-features=TranslateUI "{url}"'],
    ['Edge:', '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --kiosk "{url}" --edge-kiosk-type=fullscreen --no-first-run']],
  mac: [['Chrome — run in Terminal:', '/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --kiosk "{url}"']],
  linux: [['Chrome / Chromium — run in a terminal:', 'google-chrome --kiosk --disable-pinch "{url}"'],
    ['', 'chromium-browser --kiosk "{url}"']],
};
function LabSetup({ d }) {
  const [url, setUrl] = useState(d.portal_url);
  const [os, setOs] = useState('win');
  const [copied, setCopied] = useState(-1);
  const copy = (text, i) => { navigator.clipboard.writeText(text.replace('{url}', url)); setCopied(i); setTimeout(() => setCopied(-1), 1200); };
  return (
    <>
      <div className="page-header"><h1>Lab / Kiosk Setup</h1></div>
      <Tabs d={d} />
      <div className="card mb-3" style={{ borderColor: 'var(--info)' }}><div className="card-body">
        <p className="mb-2"><i aria-hidden="true" className="fas fa-circle-info" style={{ color: 'var(--info)' }} /> The in-app lockdown (fullscreen, leave-detection, paste/shortcut blocking) is a strong deterrent, but a normal browser can't truly stop a new tab or <kbd>Alt</kbd>+<kbd>Tab</kbd>. Launching the laptops in <strong>kiosk mode</strong> removes the address bar, tabs and most escapes — combine it with supervisors for genuinely exam-grade control.</p>
        <div className="form-group mb-0" style={{ maxWidth: 520 }}>
          <label className="form-label">Exam portal address (students open this)</label>
          <input type="text" className="form-control" value={url} onChange={(e) => setUrl(e.target.value)} />
          <span className="form-hint d-block">Edit if your lab reaches the server on a different address. Commands below update automatically.</span>
        </div>
      </div></div>
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-rocket" /> 1 · Launch the browser in kiosk mode</h3></div>
        <div className="card-body">
          <div className="os-tabs">
            {[['win', 'Windows'], ['mac', 'macOS'], ['linux', 'Linux']].map(([k, lbl]) => (
              <span key={k} className={'os-tab' + (os === k ? ' active' : '')} onClick={() => setOs(k)}>{lbl}</span>))}
          </div>
          {OS_CMDS[os].map(([label, tpl], i) => (
            <div key={i}>
              {label && <p className="text-sm mt-2">{label}</p>}
              <div className="cmd"><span>{tpl.replace('{url}', url)}</span>
                <button type="button" className="copy" onClick={() => copy(tpl, i)}>{copied === i ? 'Copied' : 'Copy'}</button></div>
            </div>))}
          <p className="text-sm text-muted mt-2">Exit (invigilator only) varies by OS. For the strongest lockdown use Windows Assigned Access, macOS guided access, or <strong>Safe Exam Browser</strong>.</p>
        </div></div>
      <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-list-check" /> 2 · Before the exam starts</h3></div>
        <div className="card-body">
          {[['Print the passwords.', 'Export each class arm\'s Student IDs + passwords (CBT → Student Passwords → Excel/Word/PDF) and hand them out.'],
            ['Set a Supervisor PIN', '(CBT → Supervisor) and share it only with invigilators — for helping students mid-exam without flagging them.'],
            ['Publish', 'the exam and confirm its date, time window and total mark. Students only see it for their class, on its day, within the window.'],
            ['Open the kiosk', 'on each laptop to the address above. Students log in with their Student ID + password, then enter the exam\'s access password.']].map(([b, t], i) => (
            <div className="step" key={i}><span className="n">{i + 1}</span><div><strong>{b}</strong> {t}</div></div>))}
        </div></div>
      <div className="card"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-shield-halved" /> 3 · Highest security (optional)</h3></div>
        <div className="card-body"><ul className="text-sm" style={{ lineHeight: 1.8, margin: 0, paddingLeft: '1.1rem' }}>
          <li><strong>Safe Exam Browser</strong> (safeexambrowser.org) — free, purpose-built lockdown browser that blocks tab/app switching, screenshots and copy at the OS level.</li>
          <li>Use <strong>guest / restricted accounts</strong> on the laptops, disable USB ports, and disable translate / autofill features.</li>
          <li>Keep the in-app <strong>Strict mode</strong> on with a low <strong>leave-page limit</strong> for high-stakes exams.</li>
          <li>Position invigilators to see screens; the <strong>integrity log</strong> records every leave, paste attempt and time away for review.</li>
        </ul></div></div>
    </>
  );
}

// ---- Exam form (add / edit) ------------------------------------------------
function ExamForm({ d, notify }) {
  const nav = useNav();
  const e0 = d.exam;
  const [f, setF] = useState(e0 || { title: '', subject_id: '', class_id: '', arm_id: '',
    term_id: d.active_term_id || '', exam_date: '', start_time: '', end_time: '', duration_minutes: 30,
    max_score: '', access_password: '', instructions: '', shuffle: true, strict_mode: true, violation_limit: 3 });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (ev) => {
    ev.preventDefault();
    if (!f.title.trim() || !f.access_password.trim()) { notify('error', 'Title and an access password are required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, shuffle: f.shuffle ? 'on' : '', strict_mode: f.strict_mode ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <div className="page-header"><h1>{d.mode === 'edit' ? 'Edit Exam' : 'New Exam'}</h1></div>
      {d.mode === 'add' && <Tabs d={d} />}
      <div className="card"><div className="card-body"><form onSubmit={submit}>
        <div className="form-group"><label className="form-label">Title <span className="required">*</span></label>
          <input type="text" className="form-control" required placeholder="e.g., Mathematics — Week 6 Test" value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Subject</label><select className="form-control" value={f.subject_id} onChange={(e) => set('subject_id', e.target.value)}><option value="">—</option>{d.subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Class</label><select className="form-control" value={f.class_id} onChange={(e) => set('class_id', e.target.value)}><option value="">—</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Arm <span className="text-muted text-sm">(optional)</span></label><select className="form-control" value={f.arm_id} onChange={(e) => set('arm_id', e.target.value)}><option value="">All arms</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Term</label><select className="form-control" value={f.term_id} onChange={(e) => set('term_id', e.target.value)}><option value="">—</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Exam date <span className="required">*</span></label><input type="date" className="form-control" required value={f.exam_date} onChange={(e) => set('exam_date', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Duration (minutes)</label><input type="number" className="form-control" min="1" value={f.duration_minutes} onChange={(e) => set('duration_minutes', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Total mark (out of)</label><input type="number" className="form-control" min="1" step="0.5" placeholder="e.g., 30" value={f.max_score} onChange={(e) => set('max_score', e.target.value)} /><span className="form-hint d-block">Blank = sum of question marks.</span></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Opens at <span className="text-muted text-sm">(time)</span></label><input type="time" className="form-control" value={f.start_time} onChange={(e) => set('start_time', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Closes at <span className="text-muted text-sm">(time)</span></label><input type="time" className="form-control" value={f.end_time} onChange={(e) => set('end_time', e.target.value)} /></div>
          <div className="form-group" style={{ alignSelf: 'center' }}><span className="form-hint">Students can only access the test on the date, within this window. Leave blank for all-day access.</span></div>
        </div>
        <div className="form-row">
          <div className="form-group"><label className="form-label">Access password <span className="required">*</span></label><input type="text" className="form-control" required placeholder="Read out to students at start" value={f.access_password} onChange={(e) => set('access_password', e.target.value)} /><span className="form-hint d-block">Per-exam password students must enter to begin.</span></div>
          <div className="form-group" style={{ alignSelf: 'center' }}><label className="form-check"><input type="checkbox" checked={f.shuffle} onChange={(e) => set('shuffle', e.target.checked)} /> Shuffle question &amp; option order</label></div>
        </div>
        <div className="form-row" style={{ background: 'var(--gray-50)', borderRadius: 'var(--radius-md)', padding: '.5rem .75rem' }}>
          <div className="form-group" style={{ alignSelf: 'center' }}><label className="form-check"><input type="checkbox" checked={f.strict_mode} onChange={(e) => set('strict_mode', e.target.checked)} /> <strong>Strict / lockdown mode</strong></label><span className="form-hint d-block">Fullscreen + record tab/app switching.</span></div>
          <div className="form-group"><label className="form-label">Leave-page limit</label>
            <select className="form-control" value={f.violation_limit} onChange={(e) => set('violation_limit', e.target.value)}>
              <option value="1">1 — strictest (auto-submit on first leave)</option><option value="2">2</option>
              <option value="3">3 — default</option><option value="5">5 — lenient</option>
              <option value="0">0 — never auto-submit (just record)</option></select>
            <span className="form-hint d-block">How many times a student may leave before auto-submit.</span></div>
        </div>
        <div className="form-group"><label className="form-label">Instructions</label><textarea className="form-control" rows="2" value={f.instructions} onChange={(e) => set('instructions', e.target.value)} /></div>
        <div className="page-header-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> {d.mode === 'edit' ? 'Save' : 'Create & add questions'}</button>
          <a href={d.cancel_url} className="btn btn-secondary">Cancel</a>
        </div>
      </form></div></div>
    </>
  );
}

// ---- Results ---------------------------------------------------------------
function Results({ d }) {
  const e = d.exam;
  const submittedCount = d.attempts.filter((a) => a.status === 'Submitted').length;
  return (
    <>
      <div className="page-header"><h1>Results · {e.title}</h1>
        <div className="page-header-actions"><a href={d.urls.export} className="btn btn-primary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Download Excel</a></div>
      </div>
      <div className="card mb-3"><div className="card-body d-flex justify-between flex-wrap gap-2">
        <div><div className="text-muted text-sm">Submissions</div><strong style={{ fontSize: '1.2rem' }}>{submittedCount}</strong></div>
        <div><div className="text-muted text-sm">Average score</div><strong style={{ fontSize: '1.2rem' }}>{d.avg} / {e.total_marks}</strong></div>
        <div><div className="text-muted text-sm">Questions</div><strong style={{ fontSize: '1.2rem' }}>{e.question_count}</strong></div>
      </div></div>
      <div className="card"><div className="card-header"><h3>{d.attempts.length} attempt(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(a) => a.id} rows={d.attempts}
            empty={<Empty icon="fa-chart-bar" title="No attempts yet"><p>Results appear here once students take the test.</p></Empty>}
            columns={[
              { key: 'student', label: 'Student', render: (a) => <>{a.student}<div className="text-muted text-sm">{a.student_id}</div></> },
              { key: 'raw', label: 'Raw', align: 'right', render: (a) => a.raw_total ? `${Math.round(a.raw_score)}/${Math.round(a.raw_total)}` : '—' },
              { key: 'score', label: 'Score', align: 'right', render: (a) => `${a.score} / ${a.total}` },
              { key: 'pct', label: '%', align: 'right', render: (a) => <span className={'badge ' + (a.percentage >= 50 ? 'badge-success' : 'badge-danger')}>{a.percentage}%</span> },
              { key: 'flags', label: 'Flags', render: (a) => a.violations ? <span className="badge badge-danger" title={`Left the exam page ${a.violations} time(s)`}><i aria-hidden="true" className="fas fa-flag" /> {a.violations}</span> : <span className="text-muted">—</span> },
              { key: 'status', label: 'Status', render: (a) => <span className={'badge ' + (a.status === 'Submitted' ? 'badge-success' : 'badge-warning')}>{a.status}</span> },
              { key: 'act', label: '', render: (a) => a.status === 'Submitted' && <a href={a.review_url} className="btn btn-secondary btn-sm" title="Review answers" data-native><i aria-hidden="true" className="fas fa-list-check" /></a> },
            ]} />
        </div></div>
      {d.analysis.length > 0 && submittedCount > 0 && (
        <div className="card mt-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-chart-simple" /> Question analysis</h3><span className="text-muted text-sm">% of {submittedCount} submission(s) correct</span></div>
          <div className="card-body">{d.analysis.map((it, i) => (
            <div key={i} style={{ marginBottom: '.7rem' }}>
              <div className="d-flex justify-between text-sm"><span>{i + 1}. {it.text.length > 70 ? it.text.slice(0, 70) + '…' : it.text}</span><span><strong>{it.pct}%</strong> ({it.correct}/{submittedCount})</span></div>
              <div style={{ height: 8, background: 'var(--gray-100)', borderRadius: 99, overflow: 'hidden', marginTop: '.25rem' }}>
                <div style={{ height: '100%', width: it.pct + '%', background: it.pct >= 50 ? 'var(--success)' : 'var(--danger)' }} /></div>
            </div>))}
          </div></div>
      )}
    </>
  );
}

const SCREENS = { dashboard: Dashboard, settings: Settings, lab_setup: LabSetup, exam_form: ExamForm, results: Results };

export default function CbtApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
