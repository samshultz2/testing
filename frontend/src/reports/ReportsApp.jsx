// Reports — a school-at-a-glance summary (students, attendance, fees, exams,
// staff, library, events, communication), plus export / import of student
// data. Built on the results kit + app kit: one-column cards on phones, a
// dense dashboard grid on laptops, and a clean print layout.
import React, { useState } from 'react';
import { postFile } from '../lib/forms';
import { nairaShort } from '../lib/format';
import { useSection, NavCtx, useNav } from '../lib/section';
import { SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Blank, Meter, Ring } from '../subjects/results';
import { A, SecNav, Field, plural } from '../components/appkit';

const pct = (v) => (v == null ? '—' : `${v}%`);
const toneOf = (v, good = 85, mid = 70) => (v == null ? '' : v >= good ? 'good' : v >= mid ? 'mid' : 'bad');
const whole = (n) => '₦' + Math.round(n || 0).toLocaleString('en-NG');
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtDate = (iso) => { const t = new Date(iso + 'T00:00:00'); return `${t.getDate()} ${MONTHS[t.getMonth()]}`; };

function RNav({ d, active }) {
  const u = d.urls || {};
  return <SecNav label="Reports" active={active} items={[
    ['summary', 'fa-chart-pie', 'Summary', u.summary],
    ['index', 'fa-table-cells-large', 'Data & exports', u.index],
    ['export_class', 'fa-file-export', 'Export a class', canWrite(d, 'export') ? u.export_class : null],
    ['import', 'fa-file-import', 'Import students', canWrite(d, 'import') ? u.import : null],
  ]} />;
}

const Card = ({ icon, title, link, linkText, children, className }) => (
  <section className={'rs-card rp-card ' + (className || '')}>
    <div className="rs-card-h"><h3><i className={'fas ' + icon} aria-hidden="true" /> {title}</h3>
      {link && <A to={link} className="cm-link">{linkText || 'Open'} <i className="fas fa-arrow-right" aria-hidden="true" /></A>}</div>
    {children}
  </section>
);
const Stat = ({ label, value, sub, tone }) => (
  <div className={'rp-stat ' + (tone || '')}><span>{label}</span><b>{value}</b>{sub && <small>{sub}</small>}</div>
);

// ============================================================================
// Summary
// ============================================================================
function Summary({ d }) {
  const b = d.blocks || {};
  const L = d.links || {};
  const st = b.students, at = b.attendance, fi = b.finance, rs = b.results, sf = b.staff, lb = b.library, ev = b.events, cm = b.comms;
  const attn = [
    st && st.not_enrolled > 0 && { to: L.students, ic: 'fa-user-slash', tone: 'mid', t: `${plural(st.not_enrolled, 'student')} not in a class this term` },
    fi && fi.defaulters > 0 && { to: L.defaulters, ic: 'fa-money-bill-wave', tone: 'bad', t: `${plural(fi.defaulters, 'student')} owe ${nairaShort(fi.owed)}` },
    at && at.low_classes && at.low_classes[0] && at.low_classes[0].rate < 75 && { to: L.attendance, ic: 'fa-user-clock', tone: 'mid', t: `${at.low_classes[0].name} attendance is ${at.low_classes[0].rate}%` },
    lb && lb.overdue > 0 && { to: L.overdue, ic: 'fa-book', tone: 'mid', t: `${plural(lb.overdue, 'library book')} overdue` },
    cm && cm.without_contact > 0 && { to: L.contacts_missing, ic: 'fa-phone-slash', tone: 'info', t: `${plural(cm.without_contact, 'student')} without a parent phone` },
    sf && sf.absent_today > 0 && { to: L.staff, ic: 'fa-user-xmark', tone: 'info', t: `${plural(sf.absent_today, 'staff member')} absent today` },
  ].filter(Boolean);
  const classMax = st ? Math.max(1, ...st.by_class.map((c) => c.total)) : 1;
  const wkMax = 100;
  return (
    <div className="rs cm rp">
      <RNav d={d} active="summary" />
      <Head icon="fa-chart-pie" title="School summary" sub={[d.term, d.session].filter(Boolean).join(' · ') || 'No active term'}>
        <button type="button" className="rs-btn ghost rp-noprint" onClick={() => window.print()}><i className="fas fa-print" aria-hidden="true" /><span className="rs-hide-sm"> Print</span></button>
      </Head>

      <Tiles items={[
        st && { label: 'Students', value: st.total, sub: `${st.male} boys · ${st.female} girls` },
        at && { label: 'Attendance this term', value: at.term_rate == null ? '—' : at.term_rate, unit: at.term_rate == null ? '' : '%', tone: toneOf(at.term_rate),
          sub: at.today_rate == null ? 'not marked today' : `${at.today_rate}% today` },
        fi && { label: 'Fees collected', value: fi.rate == null ? '—' : fi.rate, unit: fi.rate == null ? '' : '%', tone: toneOf(fi.rate, 80, 50),
          sub: `${nairaShort(fi.collected)} of ${nairaShort(fi.payable)}` },
        sf && { label: 'Staff in today', value: sf.marked_today ? sf.present_today : '—', sub: sf.marked_today ? `of ${sf.total} · ${sf.late_today} late` : `${sf.total} staff · not marked` },
      ]} />

      {attn.length > 0 && (
        <section className="rs-card rp-attn"><span className="k">Needs attention</span>
          <div className="rp-attn-l">{attn.map((a) => (
            <A key={a.t} to={a.to} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.ic} aria-hidden="true" />{a.t}<i className="fas fa-chevron-right" aria-hidden="true" /></A>))}</div>
        </section>)}

      <div className="rp-grid">
        {st && (
          <Card icon="fa-users" title="Students" link={L.students} linkText="All students">
            <div className="rp-split">
              <Ring value={st.total ? st.enrolled / st.total * 100 : 0} label="in a class" size={92} />
              <div className="rp-stats">
                <Stat label="Enrolled this term" value={st.enrolled} sub={st.not_enrolled ? `${st.not_enrolled} not placed` : 'everyone placed'} />
                <Stat label="New this term" value={st.new_term} />
              </div>
            </div>
            <div className="rp-gender" aria-label="Boys and girls">
              <i className="m" style={{ flex: st.male || 0.0001 }} /><i className="f" style={{ flex: st.female || 0.0001 }} />
            </div>
            <div className="rp-legend"><span><i className="m" /> Boys {st.male}</span><span><i className="f" /> Girls {st.female}</span></div>
            {st.by_class.length > 0 && (
              <div className="rp-bars">{st.by_class.map((c) => (
                <div key={c.name} className="rp-bar"><span className="t">{c.name}</span>
                  <span className="b" style={{ width: (c.total / classMax * 100) + '%' }}><i className="m" style={{ flex: c.male || 0.0001 }} /><i className="f" style={{ flex: c.female || 0.0001 }} /></span>
                  <b>{c.total}</b></div>))}</div>)}
          </Card>)}

        {at && (
          <Card icon="fa-user-check" title="Attendance" link={L.attendance} linkText="Attendance">
            <div className="rp-stats row">
              <Stat label="This term" value={pct(at.term_rate)} tone={toneOf(at.term_rate)} />
              <Stat label="Today" value={pct(at.today_rate)} tone={toneOf(at.today_rate)} sub={at.today_marked ? `${at.today_marked} marked` : 'not marked yet'} />
            </div>
            {(at.weekly || []).length > 0 && (
              <div className="rp-spark" aria-label="Weekly attendance">
                {at.weekly.map((w) => (
                  <span key={w.label} title={`${w.label}: ${w.rate}%`} className={toneOf(w.rate)}>
                    <i style={{ height: Math.max(4, w.rate / wkMax * 100) + '%' }} /><small>{w.label.replace('Wk ', 'W')}</small></span>))}
              </div>)}
            {(at.low_classes || []).length > 0 && (
              <div className="rp-mini"><span className="k">Lowest classes</span>
                {at.low_classes.map((c) => <div key={c.name} className="rp-mini-r"><span>{c.name}</span><Meter value={c.rate} max={100} tone={toneOf(c.rate)} /><b>{c.rate}%</b></div>)}</div>)}
          </Card>)}

        {fi && (
          <Card icon="fa-wallet" title="Fees this term" link={L.finance} linkText="Finance">
            <div className="rp-big"><b>{whole(fi.collected)}</b><span>collected of {whole(fi.payable)}</span></div>
            <Meter value={fi.collected} max={fi.payable || 1} tone={toneOf(fi.rate, 80, 50)} />
            <div className="rp-stats row">
              <Stat label="Still owed" value={nairaShort(fi.outstanding)} tone={fi.outstanding ? 'bad' : 'good'} sub={fi.defaulters ? <A to={L.defaulters}>{plural(fi.defaulters, 'student')}</A> : 'all paid'} />
              <Stat label="Expenses" value={nairaShort(fi.expenses)} />
              <Stat label="Net" value={nairaShort(fi.net)} tone={fi.net >= 0 ? 'good' : 'bad'} />
            </div>
          </Card>)}

        {rs && (rs.waec_year || rs.jamb_year) && (
          <Card icon="fa-graduation-cap" title="External exams" link={L.waec} linkText="WAEC">
            {rs.waec_year && (
              <div className="rp-exam"><div className="h"><span className="cm-ch sms sm"><b>W</b></span>
                <div><b>WAEC {rs.waec_year}</b><small>{plural(rs.waec_candidates, 'candidate')}</small></div></div><div className="rp-stats row">
                <Stat label="5 credits incl. Eng & Maths" value={pct(rs.waec_five_rate)} tone={toneOf(rs.waec_five_rate, 70, 50)} />
                <Stat label="All subjects credit" value={pct(rs.waec_credit_rate)} />
              </div></div>)}
            {rs.jamb_year && (
              <div className="rp-exam"><div className="h"><span className="cm-ch app sm"><b>J</b></span>
                <div><b>JAMB {rs.jamb_year}</b><small>{plural(rs.jamb_candidates, 'candidate')}</small></div></div><div className="rp-stats row">
                <Stat label="Average score" value={rs.jamb_avg} sub="out of 400" />
                <Stat label="Scored 200+" value={rs.jamb_200} sub={rs.jamb_candidates ? `${Math.round(rs.jamb_200 / rs.jamb_candidates * 100)}%` : ''} />
              </div></div>)}
          </Card>)}

        {sf && (
          <Card icon="fa-user-tie" title="Staff" link={L.staff} linkText="Staff">
            <div className="rp-stats row">
              <Stat label="Teaching" value={sf.teaching} /><Stat label="Non-teaching" value={sf.non_teaching} />
            </div>
            {sf.marked_today > 0 ? (
              <div className="rp-today">
                <span className="good"><b>{sf.present_today - sf.late_today}</b> on time</span>
                <span className="mid"><b>{sf.late_today}</b> late</span>
                <span className="bad"><b>{sf.absent_today}</b> absent</span>
              </div>) : <p className="cm-mute">Staff attendance hasn’t been taken today.</p>}
          </Card>)}

        {ev && (
          <Card icon="fa-calendar" title="Coming up" link={L.events} linkText="Calendar">
            {ev.upcoming.length ? <div className="rp-events">{ev.upcoming.map((e, i) => (
              <div key={i} className="rp-ev" style={{ '--c': e.color }}><span className="d">{fmtDate(e.date)}</span>
                <span className="t"><b>{e.title}</b><small>{[e.category, e.time, e.end && e.end !== e.date ? `until ${fmtDate(e.end)}` : ''].filter(Boolean).join(' · ')}</small></span></div>))}</div>
              : <p className="cm-mute">Nothing on the calendar.</p>}
          </Card>)}

        {lb && (
          <Card icon="fa-book-open" title="Library" link={L.library} linkText="Library">
            <div className="rp-stats row">
              <Stat label="Titles" value={lb.titles} sub={`${lb.copies} copies`} />
              <Stat label="On loan" value={lb.on_loan} />
              <Stat label="Overdue" value={lb.overdue} tone={lb.overdue ? 'bad' : 'good'} />
            </div>
          </Card>)}

        {cm && (
          <Card icon="fa-comments" title="Parents" link={L.comms} linkText="Communication">
            <div className="rp-stats row">
              <Stat label="Parents reachable" value={`${cm.coverage}%`} tone={toneOf(cm.coverage, 90, 70)} sub={cm.without_contact ? `${cm.without_contact} missing a phone` : 'everyone'} />
              <Stat label="Campaigns" value={cm.campaigns} sub={`${cm.delivered} messages delivered`} />
            </div>
          </Card>)}
      </div>
      {!Object.keys(b).length && <Blank icon="fa-chart-pie" title="Nothing to show yet"><p>Add students, attendance and fees to see the school summary.</p></Blank>}
    </div>
  );
}

// ============================================================================
// Data & exports hub
// ============================================================================
function Index({ d }) {
  const u = d.urls;
  const items = [
    { to: u.summary, ic: 'fa-chart-pie', tone: 'sms', t: 'School summary', s: 'Students, attendance, fees, exams, staff — at a glance' },
    canWrite(d, 'export') && { to: u.export_students, native: true, ic: 'fa-file-excel', tone: 'wa', t: 'Export all students', s: 'Every active student with parent contacts (Excel)' },
    canWrite(d, 'export') && { to: u.export_class, ic: 'fa-school', tone: 'em', t: 'Export a class', s: 'One class list at a time' },
    canWrite(d, 'import') && { to: u.import, ic: 'fa-file-import', tone: 'app', t: 'Import students', s: 'Add many students from Excel or CSV' },
    canWrite(d, 'export') && { to: u.export_template, native: true, ic: 'fa-file-arrow-down', tone: 'ann', t: 'Import template', s: 'The column layout for imports' },
  ].filter(Boolean);
  return (
    <div className="rs cm rp">
      <RNav d={d} active="index" />
      <Head icon="fa-table-cells-large" title="Reports & data" sub="Summaries, exports and imports." />
      <div className="cm-qa rp-hub">{items.map((q) => (
        <A key={q.t} to={q.to} native={q.native} className="cm-qa-i"><span className={'cm-ch lg ' + q.tone}><i className={'fas ' + q.ic} aria-hidden="true" /></span>
          <span><b>{q.t}</b><small>{q.s}</small></span></A>))}</div>
    </div>
  );
}

// ============================================================================
// Export a class
// ============================================================================
function ExportClass({ d }) {
  const nav = useNav();
  const total = d.assignments.reduce((a, x) => a + (x.student_count || 0), 0);
  return (
    <div className="rs cm rp">
      <RNav d={d} active="export_class" />
      <Head icon="fa-file-export" title="Export a class" sub={d.assignments.length ? `${plural(d.assignments.length, 'class', 'classes')} · ${plural(total, 'student')}` : 'Pick a term to see its classes.'}>
        <select className="cm-sel" value={d.term_id} onChange={(e) => nav.go(d.urls.self + '?term_id=' + e.target.value)} aria-label="Term">
          <option value="">Choose a term…</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
      </Head>
      {d.assignments.length ? (
        <section className="rs-card"><div className="cm-list">{d.assignments.map((a) => (
          <div key={a.id} className="rp-cls">
            <span className="cm-ch sms"><i className="fas fa-school" aria-hidden="true" /></span>
            <span className="t"><b>{a.display_name}</b><small>{plural(a.student_count, 'student')}</small></span>
            <a href={a.export_url} data-native className="rs-btn primary sm"><i className="fas fa-file-excel" aria-hidden="true" /> Download</a>
          </div>))}</div></section>
      ) : <Blank icon={d.term_id ? 'fa-school' : 'fa-hand-pointer'} title={d.term_id ? 'No classes set up for this term' : 'Choose a term'} />}
    </div>
  );
}

// ============================================================================
// Import students
// ============================================================================
function Import({ d, notify }) {
  const [file, setFile] = useState(null);
  const [classId, setClassId] = useState('');
  const [armId, setArmId] = useState('');
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState(null);
  const submit = async () => {
    if (!file) { notify('error', 'Choose a file first.'); return; }
    setBusy(true); setResult(null);
    const r = await postFile(d.upload_url, file, { class_id: classId, arm_id: armId });
    setBusy(false);
    if (r.ok) { setResult({ message: r.message, warnings: r.warnings || [], more: r.more || 0 }); setFile(null); }
    else notify('error', r.error || 'Could not import the file.');
  };
  return (
    <div className="rs cm rp">
      <RNav d={d} active="import" />
      <Head icon="fa-file-import" title="Import students" sub="Add many students at once from Excel or CSV.">
        <a href={d.template_url} data-native className="rs-btn ghost"><i className="fas fa-file-arrow-down" aria-hidden="true" /><span className="rs-hide-sm"> Template</span></a>
      </Head>
      {result && (
        <section className="rs-card rp-done"><b><i className="fas fa-circle-check" aria-hidden="true" /> {result.message}</b>
          {result.warnings.length > 0 && <ul>{result.warnings.map((w, i) => <li key={i}>{w}</li>)}{result.more > 0 && <li>… and {result.more} more</li>}</ul>}</section>)}
      <section className={'rs-card rp-drop' + (drag ? ' drag' : '')}
               onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
               onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}>
        <span className="rp-drop-ic"><i className={'fas ' + (file ? 'fa-file-excel' : 'fa-cloud-arrow-up')} aria-hidden="true" /></span>
        <h3>{file ? file.name : 'Drop the spreadsheet here'}</h3>
        <p>Only <b>Surname</b> and <b>First name</b> are required. Use the template for the other columns.</p>
        <label className="rs-btn ghost"><i className="fas fa-folder-open" aria-hidden="true" /> {file ? 'Choose another file' : 'Choose a file'}
          <input type="file" hidden accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files[0] || null)} /></label>
      </section>
      <section className="rs-card rp-form">
        <div className="rs-card-h"><h3>Put them in a class <small className="cm-mute">(optional)</small></h3></div>
        <div className="cm-row2">
          <Field label="Class" grow><select value={classId} onChange={(e) => setClassId(e.target.value)}>
            <option value="">Don’t place in a class</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="Arm" grow><select value={armId} onChange={(e) => setArmId(e.target.value)}>
            <option value="">—</option>{d.arms.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
        </div>
        <small className="cm-mute">Pick both a class and an arm to enrol everyone into it for the current term.</small>
        <div className="rp-form-f"><button type="button" className="rs-btn primary" disabled={busy || !file} onClick={submit}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-upload')} aria-hidden="true" /> {busy ? 'Importing…' : 'Import students'}</button></div>
      </section>
    </div>
  );
}

const SCREENS = { index: Index, summary: Summary, export_class: ExportClass, import: Import };

export default function ReportsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = (tone, text) => setToast({ tone, text, at: Date.now() });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        <Screen d={d} notify={notify} />
        {toast && <Toast key={toast.at} tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      </SectionShell>
    </NavCtx.Provider>
  );
}
