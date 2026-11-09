// SSS3 graduation-fund contributions — rebuilt on the results kit.
// Every screen can record a payment from one sheet (search a student → amount
// chips → save), so the common job is two taps from anywhere.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { submitJson } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Chips, Sheet, Menu, Blank, Bar, usePhone, Avatar } from '../subjects/results';

const money = (n) => { const v = Math.round(Number(n) || 0); return (v < 0 ? '−₦' : '₦') + Math.abs(v).toLocaleString(); };
const short = (n) => {
  const v = Math.round(Number(n) || 0), a = Math.abs(v), sign = v < 0 ? '−' : '';
  return a >= 1e6 ? sign + '₦' + (a / 1e6).toFixed(a % 1e6 ? 1 : 0) + 'm' : a >= 1e4 ? sign + '₦' + Math.round(a / 1e3) + 'k' : money(v);
};
const pct = (a, b) => (b > 0 ? Math.min(100, (a / b) * 100) : 0);
const pctTxt = (v) => { const r = Math.round(v * 10) / 10; return (Number.isInteger(r) ? r : r.toFixed(1)) + '%'; };
const STATUS = { 'Paid': ['good', 'Paid'], 'In Progress': ['mid', 'Part-paid'], 'Not Started': ['bad', 'Not started'] };
const isoToday = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const isoShift = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const lsGet = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } };
const studentUrl = (d, id) => (d.urls.student_base || '').replace(/0(\/?)$/, id + '$1');

const A = ({ to, className, children, title }) => {
  const nav = useNav();
  return <a href={to} title={title} className={className} onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

function StatusPill({ status }) {
  const [t, l] = STATUS[status] || ['', status];
  return <span className={'sl-pill ' + t}>{l}</span>;
}

function Meter({ value, max, tone }) {
  const p = pct(value, max);
  return <span className={'rs-meter ' + (tone || (p >= 100 ? 'good' : p > 0 ? 'mid' : 'bad'))}><i style={{ width: p + '%' }} /></span>;
}

// ---- section nav ------------------------------------------------------------
const NAV = [
  { key: 'dashboard', icon: 'fa-gauge-high', label: 'Overview', sub: 'record' },
  { key: 'quick_entry', icon: 'fa-bolt', label: 'Quick entry', sub: 'record', write: true },
  { key: 'payments', icon: 'fa-list', label: 'Payments', sub: 'record' },
  { key: 'defaulters', icon: 'fa-user-clock', label: 'Owing', sub: 'reports' },
  { key: 'expenses', icon: 'fa-receipt', label: 'Expenses', sub: 'expenses' },
  { key: 'report', icon: 'fa-chart-column', label: 'Reports', sub: 'reports' },
];
const REPORT_PAGES = ['report', 'daily_summary', 'history', 'view_session'];
function canView(d, sub) {
  const p = d && d.perms;
  if (!p || !p.subs) return true;
  const s = p.subs[sub];
  return s ? !!s.level : true;
}
function CNav({ d }) {
  const u = d.urls;
  const active = REPORT_PAGES.includes(d.page) ? 'report' : d.page === 'add_payment' ? 'dashboard' : d.page === 'add_expense' ? 'expenses' : d.page === 'student_detail' ? 'dashboard' : d.page;
  const items = NAV.filter((it) => canView(d, it.sub) && (!it.write || canWrite(d, it.sub)) && u[it.key]);
  return (
    <nav className="sl-nav" aria-label="Contributions">
      {items.map((it) => (
        <A key={it.key} to={u[it.key]} className={active === it.key ? 'on' : ''}><i className={'fas ' + it.icon} aria-hidden="true" /><span>{it.label}</span></A>))}
    </nav>
  );
}

// ---- Record-a-payment sheet (shared by every screen) ------------------------
const PayCtx = React.createContext(null);
function usePay() { return React.useContext(PayCtx); }

function PaySheet({ d, initial, onClose, onDone }) {
  const [roster, setRoster] = useState(null);
  const [q, setQ] = useState('');
  const [stu, setStu] = useState(initial || null);
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState(isoToday());
  const [by, setBy] = useState(lsGet('contrib.receivedBy', ''));
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const amtRef = useRef(null);
  useEffect(() => {
    fetch(d.urls.roster, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then((r) => r.json()).then((j) => {
        setRoster(j);
        if (initial && initial.id) {
          const full = (j.students || []).find((s) => s.id === initial.id);
          if (full) setStu(full);
        }
      }).catch(() => setRoster({ students: [], collectors: [] }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (stu && amtRef.current) amtRef.current.focus(); }, [stu && stu.id]); // eslint-disable-line
  const ql = q.trim().toLowerCase();
  const matches = roster ? roster.students.filter((s) => !ql || s.name.toLowerCase().includes(ql) || (s.student_id || '').toLowerCase().includes(ql) || (s.arm || '').toLowerCase() === ql).slice(0, 40) : [];
  const remaining = stu && stu.remaining != null ? stu.remaining : null;
  const chips = [remaining > 0 && { v: remaining, l: `Full balance · ${money(remaining)}` }, ...[1000, 2000, 5000, 10000].filter((x) => remaining == null || x < remaining).map((x) => ({ v: x, l: money(x) }))].filter(Boolean);
  const amt = Number(amount) || 0;
  const save = async (next) => {
    setErr('');
    if (!stu) { setErr('Choose a student.'); return; }
    if (!(amt > 0)) { setErr('Enter the amount received.'); amtRef.current && amtRef.current.focus(); return; }
    setBusy(true);
    const r = await submitJson(d.urls.add_payment, { student_id: stu.id, amount: amt, payment_date: date, received_by: by.trim(), notes: note.trim() });
    setBusy(false);
    if (!r.ok) { setErr(r.error || 'Could not save.'); return; }
    if (by.trim()) lsSet('contrib.receivedBy', by.trim());
    onDone({ text: r.message, undo: r.undo_url, student: stu, amount: amt });
    if (next) {
      setRoster((ro) => ro && { ...ro, students: ro.students.map((s) => (s.id === stu.id ? { ...s, total_paid: s.total_paid + amt, remaining: Math.max(0, s.remaining - amt) } : s)) });
      setStu(null); setAmount(''); setNote(''); setQ('');
    } else onClose();
  };
  return (
    <Sheet title="Record a payment" onClose={onClose}>
      <div className="ct-pay">
        {!stu ? (
          <>
            <label className="rs-search ct-find"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input autoFocus type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a student by name or ID" aria-label="Search a student" /></label>
            <div className="ct-pick">
              {!roster ? <p className="rs-muted ct-p"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Loading students…</p>
                : matches.length ? matches.map((s) => (
                  <button key={s.id} type="button" className="ct-pick-row" onClick={() => setStu(s)}>
                    <Avatar name={s.name} />
                    <span className="ct-n"><b>{s.name}</b><small>{s.arm ? s.arm + ' · ' : ''}{s.remaining > 0 ? `owes ${money(s.remaining)}` : 'fully paid'}</small></span>
                    <StatusPill status={s.status} />
                  </button>))
                : <p className="rs-muted ct-p">No SSS3 student matches “{q}”.</p>}
            </div>
          </>
        ) : (
          <>
            <div className="ct-who">
              <Avatar name={stu.name} />
              <span className="ct-n"><b>{stu.name}</b><small>{stu.arm ? stu.arm + ' · ' : ''}paid {money(stu.total_paid || 0)}{remaining != null ? ` · balance ${money(remaining)}` : ''}</small></span>
              {!initial && <button type="button" className="rs-btn ghost sm" onClick={() => setStu(null)}>Change</button>}
            </div>
            {stu.total_paid != null && roster && <Meter value={stu.total_paid} max={roster.max_due} />}
            <label className="ct-f"><span>Amount received</span>
              <div className="ct-amt"><b>₦</b><input ref={amtRef} type="number" inputmode="numeric" min="1" step="50" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0"
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); save(false); } }} /></div></label>
            <div className="rs-chips ct-chips">{chips.map((c) => (
              <button key={c.l} type="button" className={'rs-chip' + (amt === c.v ? ' on' : '')} onClick={() => setAmount(String(c.v))}>{c.l}</button>))}</div>
            {remaining != null && amt > remaining && remaining > 0 && <p className="ct-warn"><i className="fas fa-circle-info" aria-hidden="true" /> That's {money(amt - remaining)} more than the balance.</p>}
            <div className="ct-row2">
              <div className="ct-f"><span>Date</span>
                <div className="ct-dates">
                  <button type="button" className={'rs-chip' + (date === isoToday() ? ' on' : '')} onClick={() => setDate(isoToday())}>Today</button>
                  <button type="button" className={'rs-chip' + (date === isoShift(-1) ? ' on' : '')} onClick={() => setDate(isoShift(-1))}>Yesterday</button>
                  <input type="date" value={date} max={isoToday()} onChange={(e) => setDate(e.target.value)} aria-label="Payment date" />
                </div></div>
              <label className="ct-f"><span>Received by</span>
                <input list="ctCollectors" value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name" />
                <datalist id="ctCollectors">{((roster && roster.collectors) || []).map((c) => <option key={c} value={c} />)}</datalist></label>
            </div>
            <label className="ct-f"><span>Note <em>(optional)</em></span><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. paid by mother, cash" /></label>
          </>
        )}
        {err && <p className="ct-err" role="alert">{err}</p>}
        {stu && (
          <div className="ct-acts">
            <button type="button" className="rs-btn ghost" disabled={busy} onClick={() => save(true)}><i className="fas fa-forward" aria-hidden="true" /> Save &amp; next</button>
            <button type="button" className="rs-btn primary" disabled={busy} onClick={() => save(false)}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save {amt > 0 ? money(amt) : ''}</button>
          </div>)}
      </div>
    </Sheet>
  );
}

// Header actions shared by every screen.
function HeadActions({ d, extra }) {
  const pay = usePay();
  const u = d.urls;
  const rec = canWrite(d, 'record');
  return (
    <>
      {rec && <button type="button" className="rs-btn primary" onClick={() => pay.open()}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Record payment</span></button>}
      <Menu items={[
        ...(extra || []),
        rec && { icon: 'fa-bolt', label: 'Quick entry (many students)', href: u.quick_entry },
        canWrite(d, 'expenses') && { icon: 'fa-receipt', label: 'Add an expense', href: u.add_expense },
        { heading: 'Reports' },
        { icon: 'fa-calendar-day', label: 'Daily summary', href: u.daily_summary },
        { icon: 'fa-chart-column', label: 'By arm', href: u.report },
        { icon: 'fa-clock-rotate-left', label: 'Past sessions', href: u.history },
        { icon: 'fa-file-excel', label: 'Download Excel', href: u.export, native: true },
        { heading: 'Manage' },
        rec && { icon: 'fa-file-import', label: 'Import from Excel', href: u.import },
        canWrite(d, 'settings') && { icon: 'fa-gear', label: 'Settings', href: u.settings },
        { icon: 'fa-right-from-bracket', label: 'Lock & exit', href: u.logout, native: true },
      ]} />
    </>
  );
}

// ---- Overview --------------------------------------------------------------
function Dashboard({ d }) {
  const s = d.stats;
  const pay = usePay();
  const phone = usePhone();
  const [q, setQ] = useState('');
  const [st, setSt] = useState('');
  const [arm, setArm] = useState('');
  const rec = canWrite(d, 'record');
  const ql = q.trim().toLowerCase();
  const rows = d.students.filter((x) => (!st || x.status === st) && (!arm || x.arm === arm) && (!ql || x.name.toLowerCase().includes(ql) || (x.student_id || '').toLowerCase().includes(ql)));
  const arms = d.arms_summary || [];
  const count = (k) => d.students.filter((x) => x.status === k && (!arm || x.arm === arm)).length;
  const balance = s.net_balance;
  return (
    <div className="rs bx ct">
      <Head icon="fa-hand-holding-dollar" title="Graduation fund" sub={`SSS3 contributions · ${money(s.max_due)} per student · ${s.total_students} students`}><HeadActions d={d} /></Head>
      <CNav d={d} />
      <Tiles items={[
        { label: 'Collected', value: short(s.total_received), sub: `${pctTxt(s.collection_rate)} of ${short(s.total_expected)}`, tone: s.collection_rate >= 75 ? 'good' : s.collection_rate >= 40 ? 'mid' : 'bad' },
        { label: 'Still owed', value: short(s.total_outstanding), sub: `${s.not_started_count + s.in_progress_count} students owing` },
        { label: 'Cash at hand', value: short(balance), sub: `after ${short(s.total_expenses)} spent`, tone: balance < 0 ? 'bad' : '' },
        { label: 'Today', value: short(s.today_collections), sub: `${short(s.week_collections)} this week` },
      ]} />

      <section className="rs-card ct-prog">
        <div className="ct-prog-h"><b>{pctTxt(s.collection_rate)} collected</b><span>{money(s.total_received)} of {money(s.total_expected)}</span></div>
        <div className="ct-stack" role="img" aria-label="Students by status">
          {[['Paid', s.fully_paid_count, 'good'], ['In Progress', s.in_progress_count, 'mid'], ['Not Started', s.not_started_count, 'bad']].map(([k, n, t]) => n > 0 && (
            <button key={k} type="button" className={'ct-seg ' + t + (st === k ? ' on' : '')} style={{ flexGrow: n }} onClick={() => setSt(st === k ? '' : k)} title={`${n} ${STATUS[k][1]}`}>{n}</button>))}
        </div>
        <div className="ct-legend">
          <span><i className="good" /> Paid {s.fully_paid_count}</span><span><i className="mid" /> Part-paid {s.in_progress_count}</span><span><i className="bad" /> Not started {s.not_started_count}</span>
        </div>
      </section>

      <div className="ct-two">
        <section className="rs-card flush">
          <div className="ct-tools">
            <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student" aria-label="Find a student" />
              {(q || st || arm) && <span className="bx-count">{rows.length} of {d.students.length}</span>}</label>
            <Seg label="Status" value={st} onChange={setSt} options={[
              { value: '', label: 'All' }, { value: 'Not Started', label: 'Not started', count: count('Not Started') },
              { value: 'In Progress', label: 'Part-paid', count: count('In Progress') }, { value: 'Paid', label: 'Paid', count: count('Paid') }]} />
          </div>
          {arms.length > 1 && <div className="ct-arms"><Chips label="Arm" value={arm} onChange={(v) => setArm(v === arm ? '' : v)}
            items={[{ value: '', label: 'All arms' }, ...arms.map((a) => ({ value: a.name, label: a.name, sub: `${a.paid}/${a.total}` }))]} /></div>}
          <ul className="ct-list">
            {rows.map((x) => (
              <li key={x.id} className="ct-li">
                <button type="button" className="ct-li-main" onClick={() => (rec ? pay.open(x) : null)} disabled={!rec} title={rec ? 'Record a payment' : ''}>
                  <Avatar name={x.name} />
                  <span className="ct-n"><b>{x.name}</b><small>{x.arm}{x.arm ? ' · ' : ''}{x.status === 'Paid' ? 'fully paid' : `owes ${money(x.remaining)}`}</small></span>
                  <span className="ct-amt-col"><Meter value={x.total_paid} max={x.max_due} /><small>{money(x.total_paid)}</small></span>
                  {!phone && <StatusPill status={x.status} />}
                </button>
                <A to={x.detail_url} className="rs-icon-btn" title="History"><i className="fas fa-chevron-right" aria-hidden="true" /></A>
              </li>))}
          </ul>
          {!rows.length && <Blank icon="fa-users" title={d.students.length ? 'No one matches' : 'No SSS3 students'}><p>{d.students.length ? 'Try another search or filter.' : 'Enrol SSS3 students for the active term to start collecting.'}</p></Blank>}
        </section>

        <div className="ct-side">
          {arms.length > 0 && (
            <section className="rs-card">
              <div className="rs-card-h"><h3><i className="fas fa-people-group" aria-hidden="true" /> By arm</h3></div>
              <div className="ct-armbars">{arms.map((a) => (
                <button key={a.name} type="button" className={'ct-armbar' + (arm === a.name ? ' on' : '')} onClick={() => setArm(arm === a.name ? '' : a.name)}>
                  <span className="t"><b>{a.name || '—'}</b><small>{a.paid}/{a.total} paid · {short(a.collected)}</small></span>
                  <Meter value={a.percentage} max={100} /><em>{pctTxt(a.percentage)}</em></button>))}</div>
            </section>)}
          <section className="rs-card flush">
            <div className="rs-card-h pad"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Latest payments</h3><A to={d.urls.payments} className="ct-link">All</A></div>
            {(d.recent_payments || []).length ? <ul className="ct-mini">{d.recent_payments.map((p, i) => (
              <li key={i}><A to={p.detail_url}><span>{p.student_name}</span><small>{p.date_short}</small><b>{money(p.amount)}</b></A></li>))}</ul>
              : <p className="rs-muted ct-p">No payments yet this session.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}

// ---- Quick entry -----------------------------------------------------------
function QuickEntry({ d, notify }) {
  const nav = useNav();
  const [amounts, setAmounts] = useState({});
  const [date, setDate] = useState(d.today);
  const [by, setBy] = useState(lsGet('contrib.receivedBy', ''));
  const [arm, setArm] = useState('');
  const [q, setQ] = useState('');
  const [owingOnly, setOwingOnly] = useState(true);
  const [busy, setBusy] = useState(false);
  const arms = [...new Set(d.students.map((s) => s.arm))].filter(Boolean).sort();
  const ql = q.trim().toLowerCase();
  const rows = d.students.filter((s) => (!arm || s.arm === arm) && (!owingOnly || s.remaining > 0 || amounts[s.id]) && (!ql || s.name.toLowerCase().includes(ql)));
  const entered = Object.entries(amounts).filter(([, v]) => Number(v) > 0);
  const total = entered.reduce((t, [, v]) => t + Number(v), 0);
  const set = (id, v) => setAmounts((m) => ({ ...m, [id]: v }));
  const save = async () => {
    if (!entered.length) { notify('error', 'Type at least one amount.'); return; }
    if (!await confirm(`Save ${entered.length} payment${entered.length === 1 ? '' : 's'} totalling ${money(total)} for ${date}?`)) return;
    setBusy(true);
    const payload = { payment_date: date, received_by: by.trim() };
    entered.forEach(([id, v]) => { payload['amount_' + id] = v; });
    const r = await submitJson(d.submit_url, payload);
    setBusy(false);
    if (r.ok) { if (by.trim()) lsSet('contrib.receivedBy', by.trim()); notify('success', r.message); setAmounts({}); nav.refresh(); }
    else notify('error', r.error || 'Could not save.');
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-bolt" title="Quick entry" sub="Type what each student paid, then save them all at once"><HeadActions d={d} /></Head>
      <CNav d={d} />
      <section className="rs-pick">
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Date received</span><input type="date" className="ct-in" value={date} max={d.today} onChange={(e) => setDate(e.target.value)} /></label>
          <label className="rs-sel grow"><span>Received by</span><input className="ct-in" value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name" /></label>
        </div>
        <div className="ct-tools nopad">
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student" aria-label="Find a student" /></label>
          <button type="button" className={'rs-chip' + (owingOnly ? ' on' : '')} onClick={() => setOwingOnly((v) => !v)}><i className="fas fa-filter" aria-hidden="true" /> Owing only</button>
        </div>
        {arms.length > 1 && <Chips label="Arm" value={arm} onChange={(v) => setArm(v === arm ? '' : v)} items={[{ value: '', label: 'All arms' }, ...arms.map((a) => ({ value: a, label: a }))]} />}
      </section>
      <section className="rs-card flush">
        <ul className="ct-list">
          {rows.map((s) => {
            const v = amounts[s.id] || '';
            return (
              <li key={s.id} className={'ct-li ct-qe' + (Number(v) > 0 ? ' on' : '')}>
                <span className="ct-n"><b>{s.name}</b><small>{s.arm}{s.arm ? ' · ' : ''}{s.remaining > 0 ? `owes ${money(s.remaining)}` : 'fully paid'}</small></span>
                {s.remaining > 0 && <button type="button" className="rs-chip ct-full" onClick={() => set(s.id, String(s.remaining))} title="Fill the full balance">Full</button>}
                <span className="ct-amt sm"><b>₦</b><input type="number" inputMode="numeric" min="0" step="50" value={v} placeholder="0" aria-label={`Amount for ${s.name}`}
                  onChange={(e) => set(s.id, e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); const all = Array.from(document.querySelectorAll('.ct-qe input')); const i = all.indexOf(e.currentTarget); if (all[i + 1]) all[i + 1].focus(); } }} /></span>
              </li>);
          })}
        </ul>
        {!rows.length && <Blank icon="fa-circle-check" title="Nothing to enter"><p>{owingOnly ? 'Everyone shown has fully paid. Untick “Owing only” to see all.' : 'No students match.'}</p></Blank>}
      </section>
      <Bar>
        <div className="rs-bar-t"><b>{entered.length ? `${entered.length} payment${entered.length === 1 ? '' : 's'} · ${money(total)}` : 'Type amounts to save'}</b><small>Enter moves to the next student</small></div>
        {entered.length > 0 && <button type="button" className="rs-btn ghost" onClick={() => setAmounts({})}>Clear</button>}
        <button type="button" className="rs-btn primary" disabled={busy || !entered.length} onClick={save}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save all</button>
      </Bar>
    </div>
  );
}

// ---- Add payment (deep-link page: opens the sheet) -------------------------
function AddPayment({ d }) {
  const pay = usePay();
  const nav = useNav();
  useEffect(() => {
    const s = d.preselect ? (d.students || []).find((x) => x.id === d.preselect) : null;
    pay.open(s ? { id: s.id, name: s.name.replace(/ \(.*\)$/, '') } : null, () => nav.go(d.urls.dashboard));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="rs bx ct">
      <Head icon="fa-plus" title="Record a payment" sub="Search the student, enter the amount, save"><HeadActions d={d} /></Head>
      <CNav d={d} />
      <Blank icon="fa-hand-holding-dollar" title="Record a payment"><button type="button" className="rs-btn primary" onClick={() => pay.open()}><i className="fas fa-plus" aria-hidden="true" /> Open the payment form</button></Blank>
    </div>
  );
}

// ---- Payments ----------------------------------------------------------------
function PaymentsList({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState('');
  const canDel = canWrite(d, 'record');
  const today = isoToday();
  const weekStart = (() => { const x = new Date(); const day = (x.getDay() + 6) % 7; x.setDate(x.getDate() - day); return x.toISOString().slice(0, 10); })();
  const monthStart = today.slice(0, 8) + '01';
  const range = d.filter_date ? (d.filter_date === today ? 'today' : 'day') : d.from_date === weekStart && !d.to_date ? 'week' : d.from_date === monthStart && !d.to_date ? 'month' : (d.from_date || d.to_date) ? 'custom' : 'all';
  const goRange = (k) => {
    const base = d.urls.payments;
    const qs = k === 'today' ? `?date=${today}` : k === 'week' ? `?from=${weekStart}` : k === 'month' ? `?from=${monthStart}` : '';
    nav.go(base + qs);
  };
  const ql = q.trim().toLowerCase();
  const rows = d.payments.filter((p) => !ql || p.student_name.toLowerCase().includes(ql) || (p.received_by || '').toLowerCase().includes(ql));
  const days = [];
  const idx = {};
  rows.forEach((p) => { if (!(p.iso in idx)) { idx[p.iso] = days.length; days.push({ iso: p.iso, label: p.date, list: [], total: 0 }); } days[idx[p.iso]].list.push(p); days[idx[p.iso]].total += p.amount; });
  const del = async (p) => {
    if (!await confirm(`Delete the ${money(p.amount)} payment from ${p.student_name}?`)) return;
    const r = await submitJson(p.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const shownTotal = rows.reduce((t, p) => t + p.amount, 0);
  return (
    <div className="rs bx ct">
      <Head icon="fa-list" title="Payments" sub={`${d.payments.length} payment${d.payments.length === 1 ? '' : 's'} · ${money(d.total_amount)}`}><HeadActions d={d} /></Head>
      <CNav d={d} />
      <section className="rs-pick">
        <Seg label="Period" value={range} onChange={goRange} options={[
          { value: 'today', label: 'Today' }, { value: 'week', label: 'This week' }, { value: 'month', label: 'This month' }, { value: 'all', label: 'All' },
          ...(range === 'day' || range === 'custom' ? [{ value: range, label: d.filter_date || 'Custom' }] : [])]} />
        <div className="ct-tools nopad">
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student or collector" aria-label="Search payments" />
            {q && <span className="bx-count">{rows.length} · {money(shownTotal)}</span>}</label>
          <label className="ct-daypick"><span className="rs-hide-sm">Day</span><input type="date" className="ct-in" value={d.filter_date || ''} max={today} onChange={(e) => nav.go(d.urls.payments + (e.target.value ? `?date=${e.target.value}` : ''))} aria-label="Pick a day" /></label>
        </div>
      </section>
      {days.length ? days.map((g) => (
        <section key={g.iso} className="rs-card flush">
          <div className="rs-card-h pad"><h3>{g.label}</h3><small>{g.list.length} · <b>{money(g.total)}</b></small></div>
          <ul className="ct-list">{g.list.map((p) => (
            <li key={p.id} className="ct-li">
              <A to={p.detail_url} className="ct-li-main"><Avatar name={p.student_name} />
                <span className="ct-n"><b>{p.student_name}</b><small>{p.received_by !== '-' ? `by ${p.received_by}` : 'collector not recorded'}{p.notes && p.notes !== '-' ? ' · ' + p.notes : ''}</small></span>
                <b className="ct-money">{money(p.amount)}</b></A>
              {canDel && <button type="button" className="rs-icon-btn danger" title="Delete" aria-label={`Delete payment from ${p.student_name}`} onClick={() => del(p)}><i className="fas fa-trash" aria-hidden="true" /></button>}
            </li>))}</ul>
        </section>
      )) : <Blank icon="fa-receipt" title="No payments in this period"><p>Pick another period, or record a payment.</p></Blank>}
    </div>
  );
}

// ---- Expenses ----------------------------------------------------------------
function ExpenseSheet({ d, onClose, onSaved }) {
  const [f, setF] = useState({ expense_date: isoToday(), description: '', amount: '', notes: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const save = async () => {
    if (!f.description.trim()) { setErr('What was it for?'); return; }
    if (!(Number(f.amount) > 0)) { setErr('Enter the amount spent.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.add_expense, { ...f, description: f.description.trim() });
    setBusy(false);
    if (r.ok) { onSaved(r.message); onClose(); } else setErr(r.error || 'Could not save.');
  };
  const sugg = ['Venue', 'Food & drinks', 'Photography', 'Gowns', 'Printing', 'Decoration', 'Transport', 'Sound'];
  return (
    <Sheet title="Add an expense" onClose={onClose}>
      <div className="ct-pay">
        <label className="ct-f"><span>What was it for?</span><input autoFocus value={f.description} onChange={(e) => set('description', e.target.value)} placeholder="e.g. Venue deposit" /></label>
        <div className="rs-chips ct-chips">{sugg.map((x) => <button key={x} type="button" className={'rs-chip' + (f.description === x ? ' on' : '')} onClick={() => set('description', x)}>{x}</button>)}</div>
        <div className="ct-row2">
          <label className="ct-f"><span>Amount</span><div className="ct-amt"><b>₦</b><input type="number" inputMode="numeric" min="1" value={f.amount} onChange={(e) => set('amount', e.target.value)} placeholder="0" /></div></label>
          <label className="ct-f"><span>Date</span><input type="date" className="ct-in" value={f.expense_date} max={isoToday()} onChange={(e) => set('expense_date', e.target.value)} /></label>
        </div>
        <label className="ct-f"><span>Note <em>(optional)</em></span><input value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Receipt number, who was paid…" /></label>
        {err && <p className="ct-err" role="alert">{err}</p>}
        <div className="ct-acts"><button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={save}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save expense</button></div>
      </div>
    </Sheet>
  );
}

function Expenses({ d, notify }) {
  const nav = useNav();
  const [open, setOpen] = useState(false);
  const can = canWrite(d, 'expenses');
  const del = async (e) => {
    if (!await confirm(`Delete “${e.description}” (${money(e.amount)})?`)) return;
    const r = await submitJson(e.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-receipt" title="Expenses" sub="What the fund has been spent on">
        {can && <button type="button" className="rs-btn primary" onClick={() => setOpen(true)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Add expense</span></button>}
      </Head>
      <CNav d={d} />
      <Tiles items={[
        { label: 'Collected', value: short(d.total_collected) },
        { label: 'Spent', value: short(d.total_expenses), sub: `${pctTxt(d.expense_rate)} of collected` },
        { label: 'Cash at hand', value: short(d.available_balance), tone: d.available_balance < 0 ? 'bad' : 'good' },
        { label: 'Expenses', value: d.expenses.length, sub: 'recorded' },
      ]} />
      {d.category_summary && d.category_summary.length > 1 && (
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-chart-pie" aria-hidden="true" /> Where the money went</h3></div>
          <div className="an-hbars">{d.category_summary.map((c) => (
            <div key={c.name} className="ct-armbar static"><span className="t"><b>{c.name}</b><small>{money(c.amount)}</small></span><Meter value={c.amount} max={d.total_expenses} tone="n" /><em>{pctTxt(pct(c.amount, d.total_expenses))}</em></div>))}</div>
        </section>)}
      <section className="rs-card flush">
        {d.expenses.length ? <ul className="ct-list">{d.expenses.map((e) => (
          <li key={e.id} className="ct-li">
            <span className="ct-li-main static"><span className="ct-ic"><i className="fas fa-receipt" aria-hidden="true" /></span>
              <span className="ct-n"><b>{e.description}</b><small>{e.date}{e.notes && e.notes !== '-' ? ' · ' + e.notes : ''}</small></span>
              <b className="ct-money out">−{money(e.amount)}</b></span>
            {can && <button type="button" className="rs-icon-btn danger" title="Delete" aria-label={`Delete ${e.description}`} onClick={() => del(e)}><i className="fas fa-trash" aria-hidden="true" /></button>}
          </li>))}</ul>
          : <Blank icon="fa-receipt" title="No expenses yet"><p>Record what the fund pays for, so the balance is always right.</p>{can && <button type="button" className="rs-btn primary" onClick={() => setOpen(true)}><i className="fas fa-plus" aria-hidden="true" /> Add expense</button>}</Blank>}
      </section>
      {open && <ExpenseSheet d={d} onClose={() => setOpen(false)} onSaved={(m) => { notify('success', m); nav.refresh(); }} />}
    </div>
  );
}

function AddExpense({ d, notify }) {
  const nav = useNav();
  return <ExpenseSheet d={{ ...d, urls: { ...d.urls, add_expense: d.submit_url } }} onClose={() => nav.go(d.back_url)} onSaved={(m) => notify('success', m)} />;
}

// ---- Defaulters ----------------------------------------------------------------
function Defaulters({ d, notify }) {
  const pay = usePay();
  const [st, setSt] = useState('');
  const [arm, setArm] = useState('');
  const rec = canWrite(d, 'record');
  const arms = [...new Set(d.defaulters.map((x) => x.arm))].filter(Boolean).sort();
  const rows = d.defaulters.filter((x) => (!st || x.status === st) && (!arm || x.arm === arm));
  const owed = rows.reduce((t, x) => t + x.remaining, 0);
  const copy = () => {
    const lines = rows.map((x, i) => `${i + 1}. ${x.name}${x.arm ? ' (' + x.arm + ')' : ''} — owes ${money(x.remaining)}`);
    const text = `SSS3 graduation fund — still owing${arm ? ' · ' + arm : ''}\n${lines.join('\n')}\nTotal: ${money(owed)}`;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(
      () => notify('success', `Copied ${rows.length} names — paste into WhatsApp or SMS.`),
      () => notify('error', 'Copy is not available in this browser.'));
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-user-clock" title="Still owing" sub={`${d.defaulters.length} student${d.defaulters.length === 1 ? '' : 's'} with a balance`}>
        <HeadActions d={d} extra={[{ icon: 'fa-copy', label: 'Copy list for WhatsApp', onClick: copy }, { icon: 'fa-file-excel', label: 'Download owing list', href: d.export_url, native: true }]} />
      </Head>
      <CNav d={d} />
      <Tiles items={[
        { label: 'Owing', value: d.defaulters.length, sub: `${d.not_started_count} haven't started`, tone: d.defaulters.length ? 'mid' : 'good' },
        { label: 'Total owed', value: short(d.total_outstanding) },
        { label: 'Average balance', value: short(d.avg_outstanding), sub: `of ${short(d.max_due)}` },
      ]} />
      <section className="rs-card flush">
        <div className="ct-tools">
          <Seg label="Status" value={st} onChange={setSt} options={[{ value: '', label: 'All' }, { value: 'Not Started', label: 'Not started', count: d.not_started_count }, { value: 'In Progress', label: 'Part-paid', count: d.defaulters.length - d.not_started_count }]} />
          <button type="button" className="rs-btn ghost sm" onClick={copy}><i className="fas fa-copy" aria-hidden="true" /> Copy list</button>
        </div>
        {arms.length > 1 && <div className="ct-arms"><Chips label="Arm" value={arm} onChange={(v) => setArm(v === arm ? '' : v)} items={[{ value: '', label: 'All arms' }, ...arms.map((a) => ({ value: a, label: a }))]} /></div>}
        <ul className="ct-list">{rows.map((x) => (
          <li key={x.id} className="ct-li">
            <A to={x.detail_url} className="ct-li-main"><Avatar name={x.name} />
              <span className="ct-n"><b>{x.name}</b><small>{x.arm}{x.arm ? ' · ' : ''}paid {money(x.total_paid)} · last {x.last_payment === 'Never' ? 'never' : x.last_payment}</small></span>
              <b className="ct-money out">{money(x.remaining)}</b></A>
            {rec && <button type="button" className="rs-btn primary sm" onClick={() => pay.open(x)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Pay</span></button>}
          </li>))}</ul>
        {!rows.length && <Blank icon="fa-circle-check" title="Nobody owing">{d.defaulters.length ? <p>No one matches this filter.</p> : <p>Every SSS3 student has paid in full.</p>}</Blank>}
      </section>
    </div>
  );
}

// ---- Reports -------------------------------------------------------------------
function ReportTabs({ d }) {
  const u = d.urls;
  const on = d.page === 'view_session' ? 'history' : d.page;
  return (
    <nav className="sl-sub" aria-label="Reports">
      <A to={u.report} className={on === 'report' ? 'on' : ''}><i className="fas fa-people-group" aria-hidden="true" /> By arm</A>
      <A to={u.daily_summary} className={on === 'daily_summary' ? 'on' : ''}><i className="fas fa-calendar-day" aria-hidden="true" /> By day</A>
      <A to={u.history} className={on === 'history' ? 'on' : ''}><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Past sessions</A>
    </nav>
  );
}

function Report({ d }) {
  const [open, setOpen] = useState('');
  return (
    <div className="rs bx ct">
      <Head icon="fa-chart-column" title="Reports" sub={`By arm · ${money(d.max_due)} per student`}><HeadActions d={d} /></Head>
      <CNav d={d} /><ReportTabs d={d} />
      <div className="ct-grid">{d.arms.map((a) => {
        const p = pct(a.total_paid, a.total_expected);
        return (
          <section key={a.name} className="rs-card ct-armcard">
            <div className="rs-card-h"><h3>{a.name || 'SSS3'}</h3><small>{a.total_students} students</small></div>
            <div className="ct-prog-h"><b>{pctTxt(p)}</b><span>{money(a.total_paid)} of {money(a.total_expected)}</span></div>
            <Meter value={p} max={100} />
            <div className="ct-legend"><span><i className="good" /> {a.fully_paid} paid</span><span><i className="mid" /> {a.total_students - a.fully_paid - a.not_started} part</span><span><i className="bad" /> {a.not_started} not started</span></div>
            <button type="button" className="ct-link" onClick={() => setOpen(open === a.name ? '' : a.name)}>{open === a.name ? 'Hide students' : 'Show students'}</button>
            {open === a.name && <ul className="ct-mini">{a.students.map((s) => (
              <li key={s.name}><span>{s.name}</span><StatusPill status={s.status} /><b>{money(s.total_paid)}</b></li>))}</ul>}
          </section>);
      })}</div>
      {!d.arms.length && <Blank icon="fa-chart-column" title="No SSS3 arms this term" />}
    </div>
  );
}

function DailySummary({ d }) {
  const max = Math.max(1, ...d.daily_data.map((x) => x.amount));
  const recent = d.daily_data.slice(0, 14).reverse();
  return (
    <div className="rs bx ct">
      <Head icon="fa-calendar-day" title="Reports" sub="Money collected each day"><HeadActions d={d} /></Head>
      <CNav d={d} /><ReportTabs d={d} />
      <Tiles items={[
        { label: 'Collection days', value: d.days_count },
        { label: 'Average a day', value: short(d.avg_daily) },
        d.best_day && { label: 'Best day', value: short(d.best_day.amount), sub: d.best_day.date_short, tone: 'good' },
      ]} />
      {recent.length > 1 && (
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-chart-column" aria-hidden="true" /> Last {recent.length} collection days</h3></div>
          <div className="bx-dist ct-days">{recent.map((x) => (
            <div key={x.date} className="bx-dist-c" title={`${x.date}: ${money(x.amount)}`}>
              <b>{short(x.amount)}</b><span className="bar"><i className="c4" style={{ height: (x.amount / max * 100).toFixed(1) + '%' }} /></span><small>{x.date.slice(0, 6)}</small></div>))}</div>
        </section>)}
      <section className="rs-card flush">
        <ul className="ct-list">{d.daily_data.map((x) => (
          <li key={x.date} className="ct-li"><A to={x.view_url} className="ct-li-main">
            <span className="ct-ic"><i className="fas fa-calendar-day" aria-hidden="true" /></span>
            <span className="ct-n"><b>{x.day}, {x.date}</b><small>{x.count} payment{x.count === 1 ? '' : 's'} · {x.collectors !== '-' ? 'by ' + x.collectors : 'collector not recorded'}</small></span>
            <b className="ct-money">{money(x.amount)}</b></A></li>))}</ul>
        {!d.daily_data.length && <Blank icon="fa-calendar-day" title="No collections yet" />}
      </section>
    </div>
  );
}

function History({ d }) {
  return (
    <div className="rs bx ct">
      <Head icon="fa-clock-rotate-left" title="Reports" sub="Every session's fund at a glance"><HeadActions d={d} /></Head>
      <CNav d={d} /><ReportTabs d={d} />
      <section className="rs-card flush">
        <ul className="ct-list">{d.sessions.map((s) => (
          <li key={s.id} className="ct-li"><A to={s.view_url} className="ct-li-main">
            <span className="ct-ic"><i className="fas fa-graduation-cap" aria-hidden="true" /></span>
            <span className="ct-n"><b>{s.name} {s.is_active && <span className="sl-pill good">Current</span>}</b><small>{s.payment_count} payments · collected {money(s.total_collected)} · spent {money(s.total_expenses)}</small></span>
            <b className={'ct-money' + (s.net_balance < 0 ? ' out' : '')}>{money(s.net_balance)}</b></A></li>))}</ul>
        {!d.sessions.length && <Blank icon="fa-clock-rotate-left" title="No past sessions yet" />}
      </section>
    </div>
  );
}

function ViewSession({ d }) {
  return (
    <div className="rs bx ct">
      <Head icon="fa-graduation-cap" title={d.session.name} sub={`${d.payments_count} payments`}><HeadActions d={d} /></Head>
      <CNav d={d} /><ReportTabs d={d} />
      <Tiles items={[{ label: 'Collected', value: short(d.total_collected) }, { label: 'Spent', value: short(d.total_expenses) }, { label: 'Balance', value: short(d.net_balance), tone: d.net_balance < 0 ? 'bad' : 'good' }]} />
      <div className="ct-two">
        <section className="rs-card flush"><div className="rs-card-h pad"><h3>Students</h3></div>
          <ul className="ct-mini">{d.student_totals.map((s, i) => <li key={i}><span>{s.name}</span><small>{s.payment_count}×</small><b>{money(s.total)}</b></li>)}</ul></section>
        <section className="rs-card flush"><div className="rs-card-h pad"><h3>Expenses</h3></div>
          {d.expenses.length ? <ul className="ct-mini">{d.expenses.map((e, i) => <li key={i}><span>{e.description}</span><small>{e.date}</small><b>−{money(e.amount)}</b></li>)}</ul> : <p className="rs-muted ct-p">No expenses.</p>}</section>
      </div>
    </div>
  );
}

// ---- Student ----------------------------------------------------------------------
function StudentDetail({ d, notify }) {
  const pay = usePay();
  const nav = useNav();
  const rec = canWrite(d, 'record');
  const p = pct(d.total_paid, d.max_due);
  const maxW = Math.max(1, ...d.weekly_data.map((w) => w.amount));
  const del = async (x) => {
    if (!await confirm(`Delete the ${money(x.amount)} payment of ${x.date}?`)) return;
    const r = await submitJson(x.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-user" title={d.student.name} sub={`${d.student.student_id || ''} · graduation fund`}>
        {rec && d.remaining > 0 && <button type="button" className="rs-btn primary" onClick={() => pay.open({ id: d.student.id, name: d.student.name, total_paid: d.total_paid, remaining: d.remaining })}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Record payment</span></button>}
      </Head>
      <CNav d={d} />
      <section className="rs-card ct-prog">
        <div className="ct-prog-h"><b>{pctTxt(p)} paid</b><span>{money(d.total_paid)} of {money(d.max_due)}</span><StatusPill status={d.status} /></div>
        <Meter value={d.total_paid} max={d.max_due} />
        <p className="rs-muted ct-p0">{d.remaining > 0 ? <>Balance <b>{money(d.remaining)}</b></> : 'Fully paid — thank you!'}</p>
      </section>
      <div className="ct-two">
        <section className="rs-card flush"><div className="rs-card-h pad"><h3><i className="fas fa-list" aria-hidden="true" /> Payments</h3><small>{d.payments.length}</small></div>
          {d.payments.length ? <ul className="ct-list">{d.payments.map((x) => (
            <li key={x.id} className="ct-li"><span className="ct-li-main static"><span className="ct-ic"><i className="fas fa-money-bill" aria-hidden="true" /></span>
              <span className="ct-n"><b>{x.date}</b><small>{x.received_by !== '-' ? 'by ' + x.received_by : ''}{x.notes ? ' · ' + x.notes : ''}</small></span><b className="ct-money">{money(x.amount)}</b></span>
              {rec && <button type="button" className="rs-icon-btn danger" title="Delete" onClick={() => del(x)}><i className="fas fa-trash" aria-hidden="true" /></button>}</li>))}</ul>
            : <Blank icon="fa-money-bill" title="No payments yet" />}
        </section>
        {d.weekly_data.some((w) => w.amount > 0) && (
          <section className="rs-card"><div className="rs-card-h"><h3><i className="fas fa-chart-column" aria-hidden="true" /> Week by week</h3></div>
            <div className="bx-dist ct-days">{d.weekly_data.slice(-16).map((w) => (
              <div key={w.week} className="bx-dist-c" title={`Week ${w.week} (${w.period}): ${money(w.amount)}`}>
                <b>{w.amount ? short(w.amount) : ''}</b><span className="bar"><i className="c4" style={{ height: (w.amount / maxW * 100).toFixed(1) + '%' }} /></span><small>W{w.week}</small></div>))}</div></section>)}
      </div>
    </div>
  );
}

// ---- Settings / Import --------------------------------------------------------------
function Settings({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ max_due: d.max_due, start_date: d.start_date, access_code: '' });
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) { notify('success', r.message); setF((x) => ({ ...x, access_code: '' })); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-gear" title="Settings" sub="Amount per student, start date and access code"><HeadActions d={d} /></Head>
      <CNav d={d} />
      <form className="rs-card ct-form" onSubmit={save}>
        <label className="ct-f"><span>Amount each student pays</span><div className="ct-amt"><b>₦</b><input type="number" min="0" step="500" value={f.max_due} onChange={(e) => setF({ ...f, max_due: e.target.value })} /></div></label>
        <label className="ct-f"><span>Collection started on</span><input type="date" className="ct-in" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /><small>Used for the week-by-week view.</small></label>
        <label className="ct-f"><span>New access code <em>(leave blank to keep the current one)</em></span><input type="password" className="ct-in" autoComplete="new-password" value={f.access_code} onChange={(e) => setF({ ...f, access_code: e.target.value })} placeholder={d.has_custom_code ? '••••••' : 'Set a code so other staff can open this module'} /></label>
        <div className="ct-acts"><button type="submit" className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> Save settings</button></div>
      </form>
    </div>
  );
}

function Import({ d, notify }) {
  const nav = useNav();
  const isAdmin = d.perms && d.perms.level === 'edit';
  const clear = async () => {
    if (!await confirm('Delete EVERY contribution payment and expense? This cannot be undone.')) return;
    const r = await submitJson(d.clear_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not clear.');
  };
  return (
    <div className="rs bx ct">
      <Head icon="fa-file-import" title="Import from Excel" sub="Bring in payments from a contributions workbook"><HeadActions d={d} /></Head>
      <CNav d={d} />
      <form className="rs-card ct-form" method="POST" action={d.submit_url} encType="multipart/form-data">
        <input type="hidden" name="_csrf_token" value={csrfToken()} />
        <p className="rs-muted ct-p0">The workbook needs a <b>Students</b> sheet (ID, Name) and a <b>Payments</b> sheet (Student ID, Date, Received by, Amount). Names are matched to this term's SSS3 students.</p>
        <label className="ct-file"><i className="fas fa-file-excel" aria-hidden="true" /><span>Choose an .xlsx file</span><input type="file" name="file" accept=".xlsx" required /></label>
        <div className="ct-acts"><button type="submit" className="rs-btn primary"><i className="fas fa-upload" aria-hidden="true" /> Import</button></div>
      </form>
      {isAdmin && (
        <section className="rs-card ct-danger">
          <div><b>Clear all contribution data</b><small>Deletes every payment and expense. Download an Excel copy first.</small></div>
          <button type="button" className="rs-btn danger" onClick={clear}><i className="fas fa-trash" aria-hidden="true" /> Clear all</button>
        </section>)}
    </div>
  );
}

const SCREENS = {
  dashboard: Dashboard, quick_entry: QuickEntry, add_payment: AddPayment,
  payments: PaymentsList, expenses: Expenses, add_expense: AddExpense,
  report: Report, defaulters: Defaulters, daily_summary: DailySummary,
  history: History, view_session: ViewSession, student_detail: StudentDetail,
  settings: Settings, import: Import,
};

export default function ContributionsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const [sheet, setSheet] = useState(null);   // {student, onClose}
  const notify = (tone, text) => setToast({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  const pay = useMemo(() => ({ open: (student, onClose) => setSheet({ student: student || null, onClose }) }), []);
  const undo = async (url) => {
    setToast(null);
    const r = await submitJson(url, {});
    if (r.ok) { setToast({ tone: 'info', text: 'Payment undone.' }); refresh(); } else setToast({ tone: 'error', text: r.error || 'Could not undo.' });
  };
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <PayCtx.Provider value={pay}>
        <SectionShell go={go}>
          <Screen d={d} notify={notify} />
          {sheet && <PaySheet d={d} initial={sheet.student} onClose={() => { const cb = sheet.onClose; setSheet(null); if (cb) cb(); }}
            onDone={(res) => { setToast({ tone: 'success', text: res.text, undo: res.undo }); refresh(); }} />}
          {toast && (
            <Toast tone={toast.tone} duration={toast.undo ? 7000 : 4000} onClose={() => setToast(null)}>
              {toast.text}{toast.undo && <button type="button" className="ct-undo" onClick={() => undo(toast.undo)}>Undo</button>}
            </Toast>)}
        </SectionShell>
      </PayCtx.Provider>
    </NavCtx.Provider>
  );
}
