import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { Banner, SectionShell, SectionTabs, Empty, Table } from '../components/ui';
import { canWrite } from '../lib/perms';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'], ['add_exam', 'fa-circle-plus', 'Exams'],
  ['bank', 'fa-layer-group', 'Question Bank'], ['passwords', 'fa-key', 'Student Passwords'],
  ['settings', 'fa-user-shield', 'Supervisor'], ['lab_setup', 'fa-desktop', 'Lab Setup'],
];
// Pages that should highlight the "Exams" tab.
const TAB_FOR = { dashboard: 'dashboard', exam_form: 'add_exam', results: 'add_exam', item_analysis: 'add_exam', settings: 'settings', lab_setup: 'lab_setup' };

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
      {d.nav.syllabus && <a href={d.nav.syllabus} className="fin-tab"><i aria-hidden="true" className="fas fa-list-check" /> Syllabus</a>}
      <a href={d.nav.portal} target="_blank" rel="noopener" className="fin-tab"><i aria-hidden="true" className="fas fa-up-right-from-square" /> Test Portal</a>
    </div>
  );
}

// ---- Dashboard -------------------------------------------------------------
const CB_STATE = {
  live: { label: 'Live now', icon: 'fa-circle-dot', tone: 'live' },
  today: { label: 'Later today', icon: 'fa-hourglass-half', tone: 'soon' },
  scheduled: { label: 'Scheduled', icon: 'fa-calendar', tone: 'sched' },
  closed: { label: 'Closed', icon: 'fa-lock', tone: 'closed' },
  draft: { label: 'Draft', icon: 'fa-pen-ruler', tone: 'draft' },
};

function CbMenu({ items }) {
  const [open, setOpen] = useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close); document.addEventListener('touchstart', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('touchstart', close); };
  }, [open]);
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="cb-menu" ref={ref}>
      <button type="button" className="cb-btn" aria-haspopup="true" aria-expanded={open} aria-label="More" onClick={() => setOpen((v) => !v)}><i aria-hidden="true" className="fas fa-ellipsis" /></button>
      {open && <div className="cb-menu-pop" role="menu">
        {list.map((it, i) => <a key={i} role="menuitem" href={it.href} {...(it.native ? { 'data-native': '1' } : {})} {...(it.download ? { download: true } : {})}
          target={it.blank ? '_blank' : undefined} rel={it.blank ? 'noopener' : undefined} onClick={() => setOpen(false)}>
          <i aria-hidden="true" className={'fas ' + it.icon} /> {it.label}</a>)}
      </div>}
    </div>
  );
}

function Dashboard({ d }) {
  const nav = useNav();
  const [filter, setFilter] = useState('');
  const [q, setQ] = useState('');
  const exams = d.exams || [];
  const count = (st) => exams.filter((e) => e.state === st).length;
  const live = exams.filter((e) => e.state === 'live');
  const t = q.trim().toLowerCase();
  const order = { live: 0, today: 1, scheduled: 2, draft: 3, closed: 4 };
  const shown = exams.filter((e) => (!filter || e.state === filter)
    && (!t || `${e.title} ${e.subject} ${e.class_name}`.toLowerCase().includes(t)))
    .slice().sort((x, y) => (order[x.state] - order[y.state]) || (x.state === 'closed' ? (y.iso_date || '').localeCompare(x.iso_date || '') : (x.iso_date || '').localeCompare(y.iso_date || '')));
  const graded = exams.filter((e) => e.avg != null);
  const avgAll = graded.length ? Math.round(graded.reduce((s2, e) => s2 + e.avg * e.done, 0) / Math.max(1, graded.reduce((s2, e) => s2 + e.done, 0))) : null;
  const termName = d.show_all ? 'All terms' : ((d.terms.find((x) => String(x.id) === String(d.term_id)) || {}).full_name || 'Term');
  const canCreate = canWrite(d, 'exams_create');
  const scoreTone = (v) => (v == null ? '' : v >= 70 ? 'good' : v >= 50 ? 'warn' : 'bad');
  const window_ = (e) => (e.opens || e.closes ? `${e.opens || 'start of day'} – ${e.closes || 'end of day'}` : 'All day');

  return (
    <div className="cb">
      <header className="cb-head">
        <span className="cb-logo" aria-hidden="true"><i className="fas fa-laptop-code" /></span>
        <div className="cb-head-t">
          <span className="cb-kick">CBT · {termName}</span>
          <h1>Online tests</h1>
        </div>
        <div className="cb-head-a">
          <label className="cb-term"><i aria-hidden="true" className="fas fa-calendar" />
            <select value={d.show_all ? 'all' : d.term_id} onChange={(e) => navParams(nav.go, d.self_url, { term_id: e.target.value })} aria-label="Term">
              {d.terms.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}
              <option value="all">All terms (history)</option></select></label>
          {canCreate && <a href={d.urls.add} className="cb-btn primary"><i aria-hidden="true" className="fas fa-plus" /> <span>New exam</span></a>}
          <CbMenu items={[
            d.urls.subject_topics && { href: d.urls.subject_topics, icon: 'fa-diagram-project', label: 'Subject topics' },
            canWrite(d, 'results_export') && { href: d.urls.export_all, icon: 'fa-file-excel', label: 'Export all results', native: true, download: true },
            d.nav && d.nav.portal && { href: d.nav.portal, icon: 'fa-arrow-up-right-from-square', label: 'Open student portal', native: true, blank: true },
          ]} />
        </div>
      </header>

      <Tabs d={d} />

      {live.length > 0 && (
        <section className="cb-live">
          <div className="cb-live-h"><span className="cb-pulse" aria-hidden="true" /><b>{live.length} test{live.length === 1 ? '' : 's'} open right now</b></div>
          <ul>
            {live.map((e) => (
              <li key={e.id}>
                <span className="cb-pn"><strong>{e.title}</strong><small>{e.class_name} · {e.subject} · closes {e.closes || 'end of day'}</small></span>
                <span className="cb-live-n"><b>{e.live}</b> writing · <b>{e.done}</b> done</span>
                <a href={e.monitor_url} className="cb-btn primary" data-native="1"><i aria-hidden="true" className="fas fa-display" /> <span>Monitor</span></a>
              </li>))}
          </ul>
        </section>
      )}

      {(() => {
        const pend = exams.filter((e) => e.is_published && e.state !== 'closed');
        const noQ = pend.filter((e) => !e.question_count);
        const noPw = pend.filter((e) => !e.has_password);
        if (!noQ.length && !noPw.length) return null;
        return (
          <div className="cb-warn">
            <i aria-hidden="true" className="fas fa-triangle-exclamation" />
            <div>
              {noQ.length > 0 && <p><b>{noQ.length} published test{noQ.length === 1 ? ' has' : 's have'} no questions yet:</b> {noQ.map((e, i) => <React.Fragment key={e.id}>{i ? ', ' : ''}<a href={e.detail_url}>{e.title}</a></React.Fragment>)}</p>}
              {noPw.length > 0 && <p><b>{noPw.length} published test{noPw.length === 1 ? ' has' : 's have'} no access password</b> — any student could open {noPw.length === 1 ? 'it' : 'them'}: {noPw.map((e, i) => <React.Fragment key={e.id}>{i ? ', ' : ''}<a href={e.detail_url}>{e.title}</a></React.Fragment>)}</p>}
            </div>
          </div>);
      })()}

      <div className="cb-tiles">
        {[['', 'Exams', d.total, 'fa-file-pen', `${d.published} published`],
          ['live', 'Live now', count('live'), 'fa-circle-dot', count('today') ? `${count('today')} later today` : 'open for students'],
          ['scheduled', 'Upcoming', count('scheduled') + count('today'), 'fa-calendar', 'published, not yet open'],
          ['draft', 'Drafts', count('draft'), 'fa-pen-ruler', 'not visible to students'],
          ['closed', 'Submissions', d.attempts, 'fa-user-check', avgAll != null ? `average ${avgAll}%` : 'finished attempts'],
        ].map(([k, l, v, ic, sub]) => (
          <button key={l} type="button" className={'cb-tile ' + (k || 'all') + (filter === k ? ' on' : '')} onClick={() => setFilter(k === 'scheduled' ? (filter === 'scheduled' ? '' : 'scheduled') : (filter === k ? '' : k))}
                  aria-pressed={filter === k}>
            <span className="l"><i aria-hidden="true" className={'fas ' + ic} />{l}</span><span className="v">{v}</span><span className="s">{sub}</span>
          </button>))}
      </div>

      <section className="cb-card">
        <header className="cb-card-h">
          <div className="cb-search"><i aria-hidden="true" className="fas fa-search" />
            <input type="search" placeholder="Search title, subject or class…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search exams" /></div>
          <div className="cb-seg" role="radiogroup" aria-label="Status">
            {[['', 'All', exams.length], ['live', 'Live', count('live')], ['today', 'Today', count('today')], ['scheduled', 'Upcoming', count('scheduled')], ['draft', 'Drafts', count('draft')], ['closed', 'Closed', count('closed')]]
              .filter(([k, , n]) => !k || n).map(([k, l, n]) => (
                <button key={k || 'all'} type="button" role="radio" aria-checked={filter === k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{l}<span>{n}</span></button>))}
          </div>
        </header>
        {shown.length ? (
          <ul className="cb-list">
            {shown.map((e) => {
              const st = CB_STATE[e.state] || CB_STATE.draft;
              return (
                <li key={e.id} className={'cb-exam ' + st.tone}>
                  <a href={e.detail_url} className="cb-exam-main">
                    <span className={'cb-state ' + st.tone}><i aria-hidden="true" className={'fas ' + st.icon} /> {st.label}</span>
                    <strong>{e.title}</strong>
                    <small>{e.subject} · {e.class_name}</small>
                  </a>
                  <div className="cb-exam-when">
                    <span><i aria-hidden="true" className="fas fa-calendar-day" /> {e.exam_date || 'No date'}</span>
                    <span><i aria-hidden="true" className="fas fa-clock" /> {window_(e)} · {e.duration} min</span>
                  </div>
                  <div className="cb-exam-facts">
                    <span className={e.question_count ? '' : 'warn'} title="Questions"><i aria-hidden="true" className="fas fa-list-ol" /> {e.question_count} Q{e.question_count === 1 ? '' : 's'}</span>
                    {e.strict && <span title="Fullscreen lockdown on"><i aria-hidden="true" className="fas fa-lock" /> Lockdown</span>}
                    {!e.has_password && e.is_published && <span className="warn" title="No access password set"><i aria-hidden="true" className="fas fa-key" /> No password</span>}
                  </div>
                  <div className="cb-exam-res">
                    {e.done || e.live ? (<>
                      <b>{e.done}</b><small>done{e.live ? ` · ${e.live} writing` : ''}</small>
                      {e.avg != null && <span className={'cb-avg ' + scoreTone(e.avg)}>{e.avg}%</span>}
                    </>) : <small className="cb-dim">No attempts yet</small>}
                  </div>
                  <div className="cb-exam-a">
                    {e.state === 'live' && <a href={e.monitor_url} className="cb-btn primary" data-native="1" title="Watch students live"><i aria-hidden="true" className="fas fa-display" /><span> Monitor</span></a>}
                    <a href={e.results_url} className="cb-btn" title="Results"><i aria-hidden="true" className="fas fa-chart-column" /><span> Results</span></a>
                    <a href={e.detail_url} className="cb-btn" title="Manage questions and settings"><i aria-hidden="true" className="fas fa-pen" /><span> Manage</span></a>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="cb-empty-wrap">
            <Empty icon="fa-file-pen" title={exams.length ? 'No exams match' : 'No exams yet'}>
              <p>{exams.length ? 'Try another search or status.' : 'Create an online test, add questions, set the access password and publish.'}</p>
              {!exams.length && canCreate && <a href={d.urls.add} className="btn btn-primary mt-2"><i aria-hidden="true" className="fas fa-plus" /> New exam</a>}
            </Empty>
          </div>
        )}
      </section>
    </div>
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
        <div className="page-header-actions">
          {d.urls.item_analysis && <a href={d.urls.item_analysis} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-microscope" /> Item analysis</a>}
          {canWrite(d, 'results_export') && <a href={d.urls.export} className="btn btn-primary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Download Excel</a>}
        </div>
      </div>
      <div className="card mb-3"><div className="card-body d-flex justify-between flex-wrap gap-2">
        <div><div className="text-muted text-sm">Submissions</div><strong style={{ fontSize: 'var(--text-lg)' }}>{submittedCount}</strong></div>
        <div><div className="text-muted text-sm">Average score</div><strong style={{ fontSize: 'var(--text-lg)' }}>{d.avg} / {e.total_marks}</strong></div>
        <div><div className="text-muted text-sm">Questions</div><strong style={{ fontSize: 'var(--text-lg)' }}>{e.question_count}</strong></div>
      </div></div>
      <div className="card"><div className="card-header"><h3>{d.attempts.length} attempt(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(a) => a.id} rows={d.attempts} pageSize={25} sticky maxHeight="65vh"
            empty={<Empty icon="fa-chart-bar" title="No attempts yet"><p>Results appear here once students take the test.</p></Empty>}
            columns={[
              { key: 'student', label: 'Student', sortable: true, sortValue: (a) => a.student, render: (a) => <>{a.student}<div className="text-muted text-sm">{a.student_id}</div></> },
              { key: 'raw', label: 'Raw', align: 'right', render: (a) => a.raw_total ? `${Math.round(a.raw_score)}/${Math.round(a.raw_total)}` : '—' },
              { key: 'score', label: 'Score', align: 'right', render: (a) => `${a.score} / ${a.total}` },
              { key: 'pct', label: '%', align: 'right', sortable: true, sortValue: (a) => Number(a.percentage) || 0, render: (a) => <span className={'badge ' + (a.percentage >= 50 ? 'badge-success' : 'badge-danger')}>{a.percentage}%</span> },
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

// ---- Psychometric item analysis -------------------------------------------
const VERDICT_STYLE = {
  keep: { bg: 'var(--success-light,#e6f4ec)', fg: 'var(--success,#1c8c53)', label: 'Keep' },
  review: { bg: '#fdf3d7', fg: '#9a7b0a', label: 'Review' },
  reject: { bg: '#fbe6e3', fg: '#b43a2e', label: 'Reject' },
};
const TONE_ICON = { positive: 'fa-circle-check', negative: 'fa-triangle-exclamation', watch: 'fa-eye' };
const TONE_BORDER = { positive: 'var(--success,#1c8c53)', negative: '#b43a2e', watch: '#c9a227' };

function IaBars({ bars }) {
  const max = Math.max(1, ...bars.map((b) => b.count));
  return (
    <div>{bars.map((b) => (
      <div key={b.band} style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.25rem 0' }}>
        <span style={{ width: 60, fontSize: 'var(--text-sm)', textAlign: 'right' }} className="text-muted">{b.band}</span>
        <div style={{ flex: 1, background: 'var(--gray-100,#eef0f4)', borderRadius: 6, height: 16, overflow: 'hidden' }}>
          <div style={{ width: `${(b.count / max) * 100}%`, height: '100%', background: 'var(--primary,#0D6A4E)' }} /></div>
        <span style={{ width: 26, fontWeight: 600, fontSize: 'var(--text-sm)' }}>{b.count}</span>
      </div>))}</div>
  );
}

// Per-student × topic heatmap (weakest students / topics first).
function TopicMatrix({ cols, students }) {
  const [all, setAll] = useState(false);
  const shown = all ? students : students.slice(0, 15);
  const cellColour = (v) => (v < 50 ? '#fbe6e3' : v < 70 ? '#fdf3d7' : 'var(--success-light,#e6f4ec)');
  const cellText = (v) => (v < 50 ? '#b43a2e' : v < 70 ? '#9a7b0a' : 'var(--success,#1c8c53)');
  return (
    <div style={{ marginTop: '1rem' }}>
      <div className="d-flex justify-between" style={{ alignItems: 'baseline', marginBottom: '.35rem' }}>
        <strong className="text-sm">Per-student topic mastery</strong>
        <span className="text-muted text-sm">neediest first · red &lt;50% · amber 50–70% · green ≥70%</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ minWidth: 360 }}>
          <thead><tr>
            <th style={{ position: 'sticky', left: 0, background: 'var(--bg-card)' }}>Student</th>
            <th className="text-center">Overall</th>
            {cols.map((c) => <th key={c} className="text-center" title={c}>{c.length > 12 ? c.slice(0, 12) + '…' : c}</th>)}
            <th>Weakest</th>
          </tr></thead>
          <tbody>{shown.map((s, i) => (
            <tr key={s.student_id || i}>
              <td style={{ position: 'sticky', left: 0, background: 'var(--bg-card)', whiteSpace: 'nowrap' }}>{s.name}</td>
              <td className="text-center" style={{ fontWeight: 700, color: cellText(s.overall) }}>{s.overall}%</td>
              {cols.map((c) => {
                const v = s.cells[c];
                return <td key={c} className="text-center" style={{ background: cellColour(v), color: cellText(v), fontWeight: 600 }}>{v}%</td>;
              })}
              <td className="text-muted text-sm">{s.weakest}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {students.length > 15 && (
        <button type="button" className="btn btn-light btn-sm mt-2" onClick={() => setAll((x) => !x)}>
          {all ? 'Show top 15 neediest' : `Show all ${students.length}`}
        </button>
      )}
    </div>
  );
}

function ItemRow({ it }) {
  const [open, setOpen] = useState(false);
  const vs = VERDICT_STYLE[it.verdict] || VERDICT_STYLE.keep;
  const pColor = it.p_band === 'ideal' ? 'var(--success)' : (it.p_band === 'too_easy' || it.p_band === 'too_hard' ? '#e74a3b' : 'var(--text-primary)');
  const dColor = it.d == null ? 'var(--text-muted)' : (it.d < 0.2 ? '#e74a3b' : (it.d >= 0.4 ? 'var(--success)' : 'var(--text-primary)'));
  return (
    <>
      <tr onClick={() => setOpen((o) => !o)} style={{ cursor: 'pointer' }}>
        <td style={{ fontWeight: 700 }}>{it.number}</td>
        <td className="text-center"><span className="badge badge-secondary">{it.key}</span></td>
        <td className="text-right" style={{ color: pColor, fontWeight: 600 }}>{it.p_pct}%</td>
        <td className="text-muted text-sm">{it.p_label}</td>
        <td className="text-right" style={{ color: dColor, fontWeight: 600 }}>{it.d == null ? '—' : it.d}</td>
        <td className="text-right">{it.rpb == null ? '—' : it.rpb}</td>
        <td className="text-right">{it.dead_distractors ? <span className="badge badge-warning">{it.dead_distractors}</span> : ''}</td>
        <td><span className="badge" style={{ background: vs.bg, color: vs.fg }}>{vs.label}</span></td>
      </tr>
      {open && (
        <tr><td colSpan={8} style={{ background: 'var(--bg-secondary,#f8f9fb)' }}>
          <div style={{ padding: '.5rem .75rem' }}>
            <div className="text-sm mb-2">{it.text}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.4rem' }}>
              {it.options.map((o) => (
                <div key={o.option} style={{ border: '1px solid var(--border-color,#e2e6ea)', borderRadius: 6, padding: '.35rem .5rem', background: o.is_key ? 'var(--success-light,#e6f4ec)' : '#fff' }}>
                  <div className="d-flex justify-between" style={{ fontSize: 'var(--text-sm)' }}>
                    <strong>{o.option}{o.is_key ? ' ✓' : ''}</strong><span>{o.rate}%</span></div>
                  <div className="text-muted text-sm">↑{o.upper} ↓{o.lower}{o.flag ? ` · ${o.flag}` : ''}</div>
                </div>))}
            </div>
            <div className="text-muted text-sm mt-1">{it.verdict_label} · {it.d_label} discrimination</div>
          </div></td></tr>
      )}
    </>
  );
}

function ItemAnalysis({ d }) {
  const a = d.analysis;
  const meta = (a && a.meta) || {};
  const s = (a && a.summary) || {};
  if (!a || meta.insufficient) {
    return (
      <>
        <div className="page-header"><h1>Item analysis · {d.exam.title}</h1>
          <div className="page-header-actions"><a href={d.urls.results} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Results</a></div></div>
        <div className="card"><div className="card-body"><Empty icon="fa-microscope" title="Not enough data">
          <p>{meta.reason || 'Item analysis needs at least 5 submitted attempts.'}</p></Empty></div></div>
      </>
    );
  }
  const krTone = s.kr20 == null ? 'var(--text-muted)' : (s.kr20 >= 0.8 ? 'var(--success)' : (s.kr20 >= 0.7 ? '#c9a227' : '#e74a3b'));
  return (
    <>
      <div className="page-header"><h1>Item analysis · {d.exam.title}</h1>
        <div className="page-header-actions">
          {canWrite(d, 'results_export') && <a href={d.urls.export_pdf} className="btn btn-success" data-native download><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</a>}
          {canWrite(d, 'results_export') && <a href={d.urls.export_excel} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>}
          <a href={d.urls.results} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Results</a>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: krTone }}>{s.kr20 == null ? '—' : s.kr20}</div><div className="text-muted text-sm">KR-20 reliability</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.mean_pct}%</div><div className="text-muted text-sm">Mean score</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.sem == null ? '—' : s.sem}</div><div className="text-muted text-sm">Std error (SEM)</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.mean_difficulty}</div><div className="text-muted text-sm">Avg difficulty (p)</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.mean_discrimination}</div><div className="text-muted text-sm">Avg discrimination</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}><span style={{ color: 'var(--success)' }}>{s.keep}</span> / <span style={{ color: '#c9a227' }}>{s.review}</span> / <span style={{ color: '#e74a3b' }}>{s.reject}</span></div><div className="text-muted text-sm">Keep / Review / Reject</div></div></div>
      </div>
      <div className="text-muted text-sm mb-2" style={{ marginTop: '-.4rem' }}>
        {meta.respondents} candidates · {meta.question_count} items · reliability: <strong>{s.kr20_label}</strong>
        {s.small_groups && <> · <span className="badge badge-warning">small group</span></>}
      </div>

      {a.recommendations && a.recommendations.length > 0 && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-flask" /> Findings &amp; recommendations</h3></div>
          <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '.6rem' }}>
            {a.recommendations.map((r, i) => (
              <div key={i} style={{ borderLeft: `4px solid ${TONE_BORDER[r.tone] || 'var(--primary)'}`, background: 'var(--bg-secondary,#f8f9fb)', borderRadius: 6, padding: '.6rem .8rem' }}>
                <div style={{ fontWeight: 700, marginBottom: '.2rem' }}><i aria-hidden="true" className={`fas ${TONE_ICON[r.tone] || 'fa-lightbulb'}`} style={{ color: TONE_BORDER[r.tone] || 'var(--primary)', marginRight: '.4rem' }} />{r.title}</div>
                <div className="text-sm" style={{ color: 'var(--text-secondary,#4a5568)' }}>{r.text}</div>
              </div>))}
          </div></div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
        <div className="card"><div className="card-header"><h3>Difficulty spread (% correct)</h3></div><div className="card-body"><IaBars bars={a.difficulty_hist} /></div></div>
        <div className="card"><div className="card-header"><h3>Discrimination spread (D)</h3></div><div className="card-body"><IaBars bars={a.discrimination_hist} /></div></div>
      </div>

      {a.topics && a.topics.has_topics && a.topics.items.length > 0 && (
        <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-diagram-project" /> Topic mastery</h3>
          <span className="text-muted text-sm">weakest first · tag questions with a topic to power this</span></div>
          <div className="card-body">
            {a.topics.items.map((t) => {
              const col = t.band === 'weak' ? '#e74a3b' : (t.band === 'secure' ? 'var(--success,#1c8c53)' : '#c9a227');
              return (
                <div key={t.topic} style={{ marginBottom: '.6rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                    <span><strong>{t.topic}</strong> <span className="text-muted">· {t.questions} item(s)</span></span>
                    <span style={{ color: col, fontWeight: 700 }}>{t.mastery}%</span>
                  </div>
                  <div style={{ height: 12, background: 'var(--gray-100,#eef0f4)', borderRadius: 99, overflow: 'hidden', marginTop: '.2rem' }}>
                    <div style={{ height: '100%', width: `${t.mastery}%`, background: col }} /></div>
                  <div className="text-muted text-sm" style={{ marginTop: '.15rem' }}>{t.below_half} of the cohort ({t.below_half_pct}%) scored under half on this topic</div>
                </div>
              );
            })}
            {a.topics.students && a.topics.students.length > 0 && a.topics.columns.length > 0 && (
              <TopicMatrix cols={a.topics.columns} students={a.topics.students} />
            )}
          </div></div>
      )}

      <div className="card"><div className="card-header"><h3>Item statistics</h3><span className="text-muted text-sm">tap a row for distractor detail</span></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table"><thead><tr>
            <th>Q</th><th className="text-center">Key</th><th className="text-right">Difficulty</th><th>Band</th>
            <th className="text-right" title="Discrimination (upper 27% − lower 27%)">Discr.</th>
            <th className="text-right" title="Point-biserial item-total correlation">r_pb</th>
            <th className="text-right" title="Non-functioning distractors">Dead</th><th>Verdict</th>
          </tr></thead>
            <tbody>{a.items.map((it) => <ItemRow key={it.number} it={it} />)}</tbody></table>
        </div></div>
    </>
  );
}

function SubjectTopics({ d }) {
  const nav = useNav();
  const a = d.analysis;
  const meta = (a && a.meta) || {};
  const s = (a && a.summary) || {};
  const go = (extra) => navParams(nav.go, d.self_url, { subject_id: d.selected_subject_id, term_id: d.selected_term_id, ...extra });
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-diagram-project" /> Subject topic mastery</h1>
        <div className="page-header-actions">
          {a && !meta.insufficient && canWrite(d, 'syllabus_view') && <a href={d.urls.export_excel} className="btn btn-secondary" data-native download><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>}
          <a href={d.urls.dashboard} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> CBT</a>
        </div>
      </div>
      <div className="filter-bar mb-3">
        <div className="form-group mb-0"><label className="form-label">Subject</label>
          <select className="form-control" value={d.selected_subject_id} onChange={(e) => go({ subject_id: e.target.value })}>
            {d.subjects.length === 0 && <option value="">No CBT subjects</option>}
            {d.subjects.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></div>
        <div className="form-group mb-0"><label className="form-label">Term</label>
          <select className="form-control" value={d.selected_term_id} onChange={(e) => go({ term_id: e.target.value })}>
            <option value="">All terms</option>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></div>
      </div>

      {!a || meta.insufficient ? (
        <div className="card"><div className="card-body"><Empty icon="fa-diagram-project" title="No topic data">
          <p>{(meta && meta.reason) || 'Tag CBT questions with a syllabus topic to see mastery across a subject’s exams.'}</p></Empty></div></div>
      ) : (<>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
          <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.mean_mastery}%</div><div className="text-muted text-sm">Mean topic mastery</div></div></div>
          <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.topics}</div><div className="text-muted text-sm">Topics assessed</div></div></div>
          <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{s.exams}</div><div className="text-muted text-sm">Exams</div></div></div>
          <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}><span style={{ color: '#e74a3b' }}>{s.weak}</span> / <span style={{ color: 'var(--success)' }}>{s.secure}</span></div><div className="text-muted text-sm">Weak / Secure</div></div></div>
        </div>
        <div className="text-muted text-sm mb-2" style={{ marginTop: '-.4rem' }}>{meta.subject} · {s.submitted} submission(s) across {s.exams} exam(s)</div>

        {a.recommendations && a.recommendations.length > 0 && (
          <div className="card mb-3"><div className="card-header"><h3><i aria-hidden="true" className="fas fa-lightbulb" /> Findings &amp; recommendations</h3></div>
            <div className="card-body" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '.6rem' }}>
              {a.recommendations.map((r, i) => { const [ic, col] = TONE_ICON[r.tone] ? [TONE_ICON[r.tone], TONE_BORDER[r.tone]] : ['fa-lightbulb', 'var(--primary)']; return (
                <div key={i} style={{ borderLeft: `4px solid ${col}`, background: 'var(--bg-secondary,#f8f9fb)', borderRadius: 6, padding: '.6rem .8rem' }}>
                  <div style={{ fontWeight: 700, marginBottom: '.2rem' }}><i aria-hidden="true" className={`fas ${ic}`} style={{ color: col, marginRight: '.4rem' }} />{r.title}</div>
                  <div className="text-sm" style={{ color: 'var(--text-secondary,#4a5568)' }}>{r.text}</div>
                </div>); })}
            </div></div>
        )}

        <div className="card"><div className="card-header"><h3>Topic league (weakest first)</h3></div>
          <div className="card-body">
            {a.topics.map((t) => {
              const col = t.band === 'weak' ? '#e74a3b' : (t.band === 'secure' ? 'var(--success,#1c8c53)' : '#c9a227');
              return (
                <div key={t.topic} style={{ marginBottom: '.7rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                    <span><strong>{t.topic}</strong> <span className="text-muted">· {t.items} item(s) · {t.exams} exam(s) · {t.students} student(s)</span></span>
                    <span style={{ color: col, fontWeight: 700 }}>{t.mastery}%</span>
                  </div>
                  <div style={{ height: 12, background: 'var(--gray-100,#eef0f4)', borderRadius: 99, overflow: 'hidden', marginTop: '.2rem' }}>
                    <div style={{ height: '100%', width: `${t.mastery}%`, background: col }} /></div>
                  {t.trend && t.trend.length > 1 && (
                    <div className="text-muted text-sm" style={{ marginTop: '.15rem' }}>
                      trend: {t.trend.map((x, i) => <span key={i}>{i > 0 ? ' → ' : ''}{x.mastery}%</span>)}
                    </div>
                  )}
                </div>
              );
            })}
          </div></div>
      </>)}
    </>
  );
}

const SCREENS = { dashboard: Dashboard, settings: Settings, lab_setup: LabSetup, exam_form: ExamForm, results: Results, item_analysis: ItemAnalysis, subject_topics: SubjectTopics };

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
