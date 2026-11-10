// Finance & Fees — one React app for the whole section (overview, taking
// payments, payments, owing, expenses, fee setup, collections, reports,
// statements). Built on the shared results kit so it feels like a native app
// on phones and keeps scrolling short on laptops. Server routes, payloads and
// permissions are unchanged: every action posts to the same endpoints.
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { chartPalette } from '../lib/hooks';
import { submitJson } from '../lib/forms';
import { naira, nairaShort } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Chips, Sheet, Menu, Blank, Bar, Ring, Meter, Avatar } from '../subjects/results';

// ---- small helpers ---------------------------------------------------------
const num = (v) => Number(v) || 0;
const pct = (a, b) => (b > 0 ? Math.round((a / b) * 1000) / 10 : 0);
const toneOf = (p) => (p >= 75 ? 'good' : p >= 40 ? 'mid' : 'bad');
const A = ({ to, className, children, title, native }) => {
  const nav = useNav();
  if (native) return <a href={to} className={className} title={title} data-native>{children}</a>;
  return <a href={to} title={title} className={className} onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};
const METHOD_IC = { Cash: 'fa-money-bill', Transfer: 'fa-building-columns', 'Bank Transfer': 'fa-building-columns', POS: 'fa-credit-card', Cheque: 'fa-money-check', Online: 'fa-globe' };
const MethodPill = ({ m }) => <span className="fn-pill"><i className={'fas ' + (METHOD_IC[m] || 'fa-wallet')} aria-hidden="true" />{m || '—'}</span>;

// ---- section navigation ------------------------------------------------------
const NAV = [
  ['dashboard', 'fa-gauge-high', 'Overview'],
  ['record_payment', 'fa-cash-register', 'Take payment'],
  ['payments', 'fa-receipt', 'Payments'],
  ['defaulters', 'fa-user-clock', 'Owing'],
  ['expenses', 'fa-money-bill-trend-up', 'Expenses'],
  ['structure', 'fa-table-list', 'Fee setup'],
  ['reports', 'fa-chart-column', 'Reports'],
];
const ACTIVE = { edit_payment: 'payments', statement: 'defaulters', items: 'structure', collections: 'reports' };
function FNav({ d }) {
  const u = d.nav || {};
  const active = ACTIVE[d.page] || d.page;
  return (
    <nav className="sl-nav fn-nav" aria-label="Finance">
      {NAV.filter(([k]) => u[k]).map(([k, ic, l]) => (
        <A key={k} to={u[k]} className={active === k ? 'on' : ''}><i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></A>))}
    </nav>
  );
}
function SubNav({ d, items }) {
  return (
    <nav className="sl-sub" aria-label="Section pages">
      {items.filter((it) => it[1]).map(([k, url, label, native]) => (
        <A key={k} to={url} native={native} className={d.page === k ? 'on' : ''}>{label}</A>))}
    </nav>
  );
}
const setupNav = (d) => <SubNav d={d} items={[['structure', d.nav.structure, 'Fee structure'], ['items', d.nav.items, 'Fee items'],
  ['billing_tools', d.nav.billing_tools, 'Charges & penalties', true], ['installments', d.nav.installments, 'Installments', true]]} />;
const reportNav = (d) => <SubNav d={d} items={[['reports', d.nav.reports, 'Term summary'], ['collections', d.nav.collections, 'Collections'],
  ['overview', d.nav.overview, 'Ledger', true], ['accounting', d.nav.accounting, 'Accounting', true]]} />;

function moreItems(d) {
  const u = d.nav || {};
  return [
    { heading: 'More finance' },
    u.search && { icon: 'fa-magnifying-glass', label: 'Find a payment or student', href: u.search, native: true },
    u.collections && { icon: 'fa-calendar-day', label: 'Collections day-book', href: u.collections },
    u.overview && { icon: 'fa-book', label: 'Ledger & multi-term overview', href: u.overview, native: true },
    u.accounting && { icon: 'fa-scale-balanced', label: 'Accounting', href: u.accounting, native: true },
    u.billing_tools && { icon: 'fa-wand-magic-sparkles', label: 'Extra charges & penalties', href: u.billing_tools, native: true },
    u.installments && { icon: 'fa-calendar-check', label: 'Installment plans', href: u.installments, native: true },
    u.items && { icon: 'fa-tags', label: 'Fee items', href: u.items },
  ];
}

function TermPick({ d, onChange, allLabel }) {
  if (!d.terms || !d.terms.length) return null;
  return (
    <label className="fn-term"><i className="fas fa-calendar" aria-hidden="true" />
      <select aria-label="Term" value={d.term_id || ''} onChange={(e) => onChange(e.target.value)}>
        {allLabel && <option value="">{allLabel}</option>}
        {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
      </select>
    </label>
  );
}

function Shell({ d, icon, title, sub, actions, sub2, children }) {
  return (
    <div className="rs bx fn">
      <Head icon={icon} title={title} sub={sub}>{actions}</Head>
      <FNav d={d} />
      {sub2}
      {children}
    </div>
  );
}
const Card = ({ icon, title, right, children, flush, className }) => (
  <section className={'rs-card' + (flush ? ' flush' : '') + (className ? ' ' + className : '')}>
    {(title || right) && <div className={'rs-card-h' + (flush ? ' fn-pad' : '')}><h3>{icon && <i className={'fas ' + icon} aria-hidden="true" />}{title}</h3>{right}</div>}
    {children}
  </section>
);

// A list of label / amount / share rows with a proportion bar (replaces doughnuts).
function BarList({ rows, labelKey = 'name', valueKey = 'amount', empty, colorful, extra }) {
  const total = rows.reduce((t, r) => t + num(r[valueKey]), 0);
  if (!rows.length) return <p className="rs-muted fn-pad">{empty}</p>;
  const pal = chartPalette().categorical;
  return (
    <div className="fn-bars">
      {rows.map((r, i) => {
        const p = pct(num(r[valueKey]), total);
        return (
          <div className="fn-bar" key={i}>
            <span className="n">{colorful && <i className="dot" style={{ background: pal[i % pal.length] }} />}{r[labelKey]}{extra && <small>{extra(r)}</small>}</span>
            <b>{nairaShort(r[valueKey])}</b><span className="p">{p}%</span>
            <span className="t"><i style={{ width: p + '%', background: colorful ? pal[i % pal.length] : undefined }} /></span>
          </div>);
      })}
    </div>
  );
}

function useLineChart(ref, rows, color) {
  useEffect(() => {
    if (!ref.current || !window.Chart || !rows.length) return undefined;
    window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-secondary') || '#666';
    const c = new window.Chart(ref.current, {
      type: rows.length > 16 ? 'bar' : 'line',
      data: { labels: rows.map((x) => x.label), datasets: [{ data: rows.map((x) => x.amount), borderColor: color, backgroundColor: rows.length > 16 ? color : 'rgba(22,163,74,.10)', fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2.5, borderRadius: 4 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => ' ' + naira(x.raw) } } },
        scales: { y: { beginAtZero: true, grid: { color: 'rgba(128,128,128,.13)' }, ticks: { callback: (v) => nairaShort(v) } }, x: { grid: { display: false } } } },
    });
    return () => c.destroy();
  }, [rows]); // eslint-disable-line react-hooks/exhaustive-deps
}

function PayRow({ p, d, notify, onDelete }) {
  const items = [
    { icon: 'fa-receipt', label: 'Receipt', href: p.receipt_url, native: true },
    p.statement_url && { icon: 'fa-file-lines', label: 'Student statement', href: p.statement_url },
    canWrite(d, 'payments_edit') && p.edit_url && { icon: 'fa-pen', label: 'Edit payment', href: p.edit_url },
    canWrite(d, 'payments_delete') && p.delete_url && onDelete && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => onDelete(p) },
  ].filter(Boolean);
  return (
    <div className="fn-row">
      <Avatar name={p.student} gender={p.gender} />
      <div className="fn-row-t">
        <strong>{p.student}{p.student_id && <small> · {p.student_id}</small>}</strong>
        <span><a href={p.receipt_url} data-native>{p.receipt_no}</a> · {p.date}{p.received_by && p.received_by !== '—' ? ' · ' + p.received_by : ''}</span>
      </div>
      <MethodPill m={p.method} />
      <b className="fn-amt">{naira(p.amount)}</b>
      {items.length > 1 ? <Menu items={items} label="" /> : <a className="rs-icon-btn fn-ic" href={p.receipt_url} data-native title="Receipt"><i className="fas fa-receipt" aria-hidden="true" /></a>}
    </div>
  );
}

// ---- Overview -----------------------------------------------------------------
function Dashboard({ d }) {
  const nav = useNav();
  const trend = useRef();
  useLineChart(trend, d.trend_chart || [], chartPalette().green);
  const classes = (d.class_chart || []).map((c) => ({ ...c, rate: pct(c.collected, c.expected) })).sort((a, b) => a.rate - b.rate);
  const go = (v) => navParams(nav.go, d.self_url, { term_id: v });
  return (
    <Shell d={d} icon="fa-coins" title="Finance" sub={d.selected_term ? `${d.selected_term} · ${d.enrolled} students enrolled` : 'School fees, payments and spending'}
      actions={<>
        <TermPick d={d} onChange={go} />
        {canWrite(d, 'payments_create') && <A to={d.urls.record_payment} className="rs-btn primary"><i className="fas fa-cash-register" aria-hidden="true" /><span>Take payment</span></A>}
        <Menu items={moreItems(d)} label="More" />
      </>}>

      {!d.has_structure && (
        <Card icon="fa-route" title="Set up fees for this term" className="fn-setup">
          <ol className="fn-steps">
            <li><A to={d.urls.items}><b>1</b><span><strong>Fee items</strong>Tuition, levies, PTA — what you charge.</span></A></li>
            <li><A to={d.urls.structure}><b>2</b><span><strong>Fee structure</strong>How much each class pays this term.</span></A></li>
            <li><A to={d.urls.record_payment}><b>3</b><span><strong>Take payments</strong>Find a student, enter the amount, print the receipt.</span></A></li>
          </ol>
          <p className="rs-muted">Every bill, balance and figure here is worked out from steps 1–2 and the payments you record.</p>
        </Card>
      )}

      <div className="fn-hero">
        <section className="rs-card fn-prog">
          <Ring value={d.rate} size={124} label="collected" />
          <div className="fn-prog-t">
            <span className="k">Collected this term</span>
            <strong>{naira(d.collected)}</strong>
            <span className="of">of {naira(d.payable_total)} expected{d.discounts ? ` · ${nairaShort(d.discounts)} waived` : ''}</span>
            <Meter value={d.collected} max={d.payable_total} />
            <div className="fn-prog-f">
              <A to={d.urls.defaulters}><b className="bad">{d.defaulter_count}</b> students owing <i className="fas fa-chevron-right" aria-hidden="true" /></A>
              <span><b>{nairaShort(d.outstanding)}</b> outstanding</span>
            </div>
          </div>
        </section>
        <Tiles items={[
          { label: 'Collected', value: nairaShort(d.collected), sub: `${d.rate}% of expected`, tone: 'good' },
          { label: 'Outstanding', value: nairaShort(d.outstanding), sub: `${d.defaulter_count} students`, tone: d.outstanding > 0 ? 'bad' : 'good' },
          { label: 'Expenses', value: nairaShort(d.expenses), sub: 'this term' },
          { label: 'Net cash', value: nairaShort(d.net), sub: 'collected − expenses', tone: d.net >= 0 ? 'good' : 'bad' },
        ]} />
      </div>

      <div className="fn-grid2">
        <Card icon="fa-chart-line" title="Collections by week" right={<A to={d.nav.collections} className="rs-link">Day-book</A>}>
          <div className="fn-chart">{(d.trend_chart || []).length ? <canvas ref={trend} /> : <Blank icon="fa-chart-line" title="No payments yet" />}</div>
        </Card>
        <Card icon="fa-school" title="By class" right={<small>lowest collection first</small>}>
          {classes.length ? (
            <div className="fn-cls">
              {classes.map((c) => (
                <div className="fn-cls-r" key={c.name}>
                  <span className="n">{c.name}</span>
                  <span className="v">{nairaShort(c.collected)} <small>/ {nairaShort(c.expected)}</small></span>
                  <b className={'tone-' + toneOf(c.rate)}>{c.rate}%</b>
                  <Meter value={c.collected} max={c.expected} />
                </div>))}
            </div>) : <Blank icon="fa-school" title="No fee structure yet" />}
        </Card>
      </div>

      <div className="fn-grid3">
        <Card icon="fa-layer-group" title="Expected by fee"><BarList rows={d.item_chart || []} colorful empty="No fee structure for this term." /></Card>
        <Card icon="fa-wallet" title="How parents paid"><BarList rows={d.method_chart || []} labelKey="method" colorful empty="No payments yet." /></Card>
        <Card icon="fa-money-bill-trend-up" title="Spending" right={<A to={d.nav.expenses} className="rs-link">Expenses</A>}><BarList rows={d.expense_chart || []} empty="No expenses recorded." /></Card>
      </div>

      <Card icon="fa-receipt" title="Latest payments" flush right={<A to={d.urls.payments} className="rs-link">See all</A>}>
        {(d.recent || []).length ? <div className="fn-list cols">{d.recent.map((p) => <PayRow key={p.id} p={p} d={d} />)}</div>
          : <Blank icon="fa-receipt" title="No payments for this term yet" />}
      </Card>
    </Shell>
  );
}

// ---- Take a payment ---------------------------------------------------------------
function RecordPayment({ d, notify }) {
  const nav = useNav();
  const goWith = (params) => navParams(nav.go, d.self_url, params);
  const sub = d.terms && d.terms.length ? (d.terms.find((t) => String(t.id) === String(d.term_id)) || {}).full_name : '';
  return (
    <Shell d={d} icon="fa-cash-register" title="Take payment" sub={sub}
      actions={<TermPick d={d} onChange={(v) => goWith({ term_id: v, assignment_id: d.assignment_id })} />}>
      {d.student ? <PayDesk d={d} notify={notify} /> : <FindStudent d={d} goWith={goWith} />}
    </Shell>
  );
}

function FindStudent({ d, goWith }) {
  const [mode, setMode] = useState(d.assignment_id || !d.search_url ? 'class' : 'class');
  const [q, setQ] = useState('');
  const [show, setShow] = useState('owing');
  const roster = d.roster || [];
  const owing = roster.filter((r) => r.balance > 0.005);
  const paid = roster.filter((r) => r.balance <= 0.005);
  const list = (show === 'owing' ? owing : show === 'paid' ? paid : roster)
    .filter((r) => !q || (r.full_name + ' ' + r.student_id).toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <div className="rs-pick">
        <Seg value={mode} onChange={setMode} label="Find a student" options={[
          { value: 'class', label: 'Pick a class', icon: 'fa-users' }, { value: 'search', label: 'Search by name', icon: 'fa-magnifying-glass' }]} />
        {mode === 'class' ? (
          <div className="fn-clsbar">
            <Chips value={d.assignment_id} onChange={(v) => goWith({ term_id: d.term_id, assignment_id: v })} label="Class"
              items={(d.assignments || []).map((a) => ({ value: a.id, label: a.display_name }))} />
          </div>
        ) : <StudentSearch url={d.search_url} termId={d.term_id} onPick={(id) => goWith({ student_id: id, term_id: d.term_id })} />}
      </div>

      {mode === 'class' && (d.assignment_id ? (roster.length ? (
        <Card flush icon="fa-users" title={`${roster.length} students`} right={<span className="fn-mini">{owing.length} owing · {nairaShort(owing.reduce((t, r) => t + r.balance, 0))}</span>}>
          <div className="fn-tools fn-pad">
            <label className="rs-search"><i className="fas fa-search" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name or ID" aria-label="Filter students" /></label>
            <Seg value={show} onChange={setShow} label="Show" options={[
              { value: 'owing', label: 'Owing', count: owing.length }, { value: 'all', label: 'All', count: roster.length }, { value: 'paid', label: 'Paid', count: paid.length }]} />
          </div>
          <div className="fn-list">
            {list.map((r) => (
              <A key={r.id} to={r.pick_url} className="fn-row fn-tap">
                <Avatar name={r.full_name} gender={r.gender} />
                <div className="fn-row-t"><strong>{r.full_name}</strong><span>{r.student_id}{r.billed ? ` · paid ${nairaShort(r.paid)} of ${nairaShort(r.billed)}` : ''}</span>
                  {r.billed > 0 && <Meter value={r.paid} max={r.billed} />}</div>
                <b className={'fn-amt ' + (r.balance > 0.005 ? 'bad' : 'good')}>{r.balance > 0.005 ? naira(r.balance) : 'Paid'}</b>
                <i className="fas fa-chevron-right fn-chev" aria-hidden="true" />
              </A>))}
            {!list.length && <p className="rs-muted fn-pad">No students match.</p>}
          </div>
        </Card>
      ) : <Blank icon="fa-users" title="No students in this class">There are no active students in this class arm for the selected term.</Blank>)
        : <Blank icon="fa-hand-pointer" title="Pick a class to see who owes what"><p>Or switch to <b>Search by name</b> to jump straight to a student.</p></Blank>)}
    </>
  );
}

function StudentSearch({ url, termId, onPick }) {
  const [text, setText] = useState('');
  const [list, setList] = useState(null);
  const tRef = useRef();
  const onInput = (v) => {
    setText(v); clearTimeout(tRef.current);
    if (v.trim().length < 2) { setList(null); return; }
    tRef.current = setTimeout(async () => {
      try {
        const r = await fetch(url + '?term_id=' + (termId || '') + '&q=' + encodeURIComponent(v.trim()), { credentials: 'same-origin' });
        setList(await r.json());
      } catch (_) { /* ignore */ }
    }, 220);
  };
  return (
    <div className="fn-search">
      <label className="rs-search"><i className="fas fa-search" aria-hidden="true" />
        <input type="search" autoFocus value={text} onChange={(e) => onInput(e.target.value)} placeholder="Type a name or student ID…" aria-label="Student name or ID" autoComplete="off" /></label>
      {list && (
        <div className="fn-list fn-results">
          {list.length ? list.map((s) => (
            <button type="button" key={s.id} className="fn-row fn-tap" onClick={() => onPick(s.id)}>
              <Avatar name={s.name} />
              <div className="fn-row-t"><strong>{s.name}</strong><span>{s.sid}{s.cls ? ' · ' + s.cls : ''}</span></div>
              <i className="fas fa-chevron-right fn-chev" aria-hidden="true" />
            </button>)) : <p className="rs-muted fn-pad">No matches.</p>}
        </div>)}
    </div>
  );
}

function BillCard({ bill, structureUrl, statementUrl, compact }) {
  if (!bill.lines.length) {
    return <Blank icon="fa-circle-info" title="No fee structure for this class">{structureUrl && <A to={structureUrl} className="rs-btn sm">Set fee structure</A>}</Blank>;
  }
  return (
    <div className="fn-bill">
      {!compact && bill.lines.map((l, i) => <div className="fn-line" key={i}><span>{l.name}</span><span>{naira(l.amount)}</span></div>)}
      <div className="fn-line sub"><span>Total billed</span><span>{naira(bill.billed)}</span></div>
      {bill.discount > 0 && <div className="fn-line"><span>Discount / waiver</span><span>− {naira(bill.discount)}</span></div>}
      <div className="fn-line"><span>Already paid</span><span className="good">{naira(bill.paid)}</span></div>
      <div className="fn-line total"><span>Balance</span><span className={bill.balance > 0.005 ? 'bad' : 'good'}>{naira(bill.balance)}</span></div>
      {statementUrl && <A to={statementUrl} className="rs-link"><i className="fas fa-file-lines" aria-hidden="true" /> Full statement</A>}
    </div>
  );
}

function PayDesk({ d, notify }) {
  const nav = useNav();
  const s = d.student;
  const bill = d.bill;
  const bal = bill ? Math.max(num(bill.balance), 0) : 0;
  const [f, setF] = useState({ amount: bal > 0 ? String(bal) : '', payment_date: d.today, method: (d.methods || ['Cash'])[0], reference: '', received_by: d.current_user || '', notes: '' });
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const amt = num(f.amount);
  const quick = [bal > 0 && ['Full balance', bal], bal > 0 && ['Half', Math.round(bal / 2)], [null, 10000], [null, 20000], [null, 50000]]
    .filter(Boolean).filter(([l, v], i, arr) => v > 0 && arr.findIndex((x) => x[1] === v) === i);
  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!(amt > 0)) { notify('error', 'Enter a positive amount.'); return; }
    if (bal > 0 && amt > bal + 0.005 && !await confirm(`₦${amt.toLocaleString()} is more than the balance (${naira(bal)}). Record it anyway?`)) return;
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, student_id: s.id, term_id: d.term_id });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  if (!bill) {
    return <Blank icon="fa-circle-info" title={`${s.full_name} has no active class this term`}><A to={d.urls.change_student} className="rs-btn sm">Pick another student</A></Blank>;
  }
  return (
    <div className="fn-desk">
      <Card className="fn-who">
        <div className="fn-who-h">
          <Avatar name={s.full_name} gender={s.gender} />
          <div><strong>{s.full_name}</strong><span>{s.student_id}</span></div>
          <A to={d.urls.change_student} className="rs-btn sm ghost"><i className="fas fa-arrow-left" aria-hidden="true" /><span>Change</span></A>
        </div>
        <BillCard bill={bill} structureUrl={d.urls.structure} statementUrl={d.urls.statement} />
      </Card>

      <form id="fnPayForm" className="rs-card fn-form" onSubmit={submit}>
        <div className="rs-card-h"><h3><i className="fas fa-money-bill-wave" aria-hidden="true" />Payment</h3>{bal <= 0.005 && <span className="fn-pill good">Fully paid</span>}</div>
        <label className="fn-big"><span>₦</span>
          <input type="number" inputMode="decimal" min="0" step="50" required value={f.amount} onChange={(e) => set('amount', e.target.value)} aria-label="Amount in naira" placeholder="0" />
        </label>
        <div className="fn-quick">{quick.map(([l, v]) => (
          <button type="button" key={v} className={'rs-chip' + (amt === v ? ' on' : '')} onClick={() => set('amount', String(v))}>{l ? <>{l} <small>{nairaShort(v)}</small></> : nairaShort(v)}</button>))}
        </div>
        {bal > 0 && amt > 0 && <p className="fn-after">Balance after this payment: <b className={bal - amt > 0.005 ? 'bad' : 'good'}>{naira(Math.max(bal - amt, 0))}</b>{amt > bal + 0.005 && <> · <b className="mid">{naira(amt - bal)} overpaid</b></>}</p>}
        <div className="fn-lbl">Method</div>
        <Seg value={f.method} onChange={(v) => set('method', v)} label="Payment method"
          options={(d.methods || []).map((m) => ({ value: m, label: m, icon: METHOD_IC[m] }))} />
        <div className="fn-fields">
          <label className="rs-sel"><span>Date</span><input type="date" value={f.payment_date} onChange={(e) => set('payment_date', e.target.value)} /></label>
          <label className="rs-sel"><span>Reference / teller no.</span><input type="text" value={f.reference} onChange={(e) => set('reference', e.target.value)} placeholder="Optional" /></label>
        </div>
        <button type="button" className="rs-link" onClick={() => setMore((m) => !m)}><i className={'fas fa-chevron-' + (more ? 'up' : 'down')} aria-hidden="true" /> {more ? 'Fewer details' : 'Received by & notes'}</button>
        {more && (
          <div className="fn-fields">
            <label className="rs-sel"><span>Received by</span><input type="text" value={f.received_by} onChange={(e) => set('received_by', e.target.value)} placeholder="Bursar name" /></label>
            <label className="rs-sel"><span>Notes</span><input type="text" value={f.notes} onChange={(e) => set('notes', e.target.value)} placeholder="Optional" /></label>
          </div>)}
        <Bar>
          <div className="rs-bar-t"><b>{amt > 0 ? naira(amt) : '₦0.00'}</b><small>{s.full_name} · {f.method}</small></div>
          <button type="submit" form="fnPayForm" className="rs-btn primary" disabled={busy || !(amt > 0)}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{busy ? 'Saving…' : 'Save & print receipt'}</button>
        </Bar>
      </form>
    </div>
  );
}

// ---- Payments -------------------------------------------------------------------
function Payments({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [limit, setLimit] = useState(40);
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, q, ...extra });
  const del = async (p) => {
    if (!await confirm(`Delete receipt ${p.receipt_no} (${naira(p.amount)})? This can't be undone.`)) return;
    const r = await submitJson(p.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const byMethod = useMemo(() => {
    const m = {};
    d.payments.forEach((p) => { m[p.method] = (m[p.method] || 0) + num(p.amount); });
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [d.payments]);
  return (
    <Shell d={d} icon="fa-receipt" title="Payments" sub={`${d.payments.length} payments · ${naira(d.total)}`}
      actions={<>
        <TermPick d={d} onChange={(v) => go({ term_id: v })} />
        {canWrite(d, 'payments_create') && <A to={d.record_url} className="rs-btn primary"><i className="fas fa-cash-register" aria-hidden="true" /><span>Take payment</span></A>}
      </>}>
      <div className="rs-pick">
        <form className="fn-tools" onSubmit={(e) => { e.preventDefault(); go(); }}>
          <label className="rs-search"><i className="fas fa-search" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, student ID or receipt no." aria-label="Search payments" /></label>
          <button type="submit" className="rs-btn">Search</button>
        </form>
        <Chips value={d.class_id} onChange={(v) => go({ class_id: v })} label="Class"
          items={[{ value: '', label: 'All classes' }, ...d.classes.map((c) => ({ value: c.id, label: c.name }))]} />
      </div>
      {byMethod.length > 0 && (
        <div className="fn-strip">
          <span className="fn-strip-t"><b>{naira(d.total)}</b> from {d.payments.length} payments</span>
          {byMethod.map(([m, v]) => <span key={m} className="fn-pill"><i className={'fas ' + (METHOD_IC[m] || 'fa-wallet')} aria-hidden="true" />{m} <b>{nairaShort(v)}</b></span>)}
        </div>)}
      <Card flush>
        {d.payments.length ? (
          <div className="fn-list cols">
            {d.payments.slice(0, limit).map((p) => <PayRow key={p.id} p={p} d={d} notify={notify} onDelete={del} />)}
            {d.payments.length > limit && <button type="button" className="fn-more" onClick={() => setLimit((l) => l + 60)}>Show more ({d.payments.length - limit} left)</button>}
          </div>
        ) : <Blank icon="fa-receipt" title="No payments found">Record a payment or change the filters.</Blank>}
      </Card>
    </Shell>
  );
}

// ---- Owing (defaulters) ---------------------------------------------------------
function Defaulters({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('balance');
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, ...extra });
  const rows = useMemo(() => {
    let r = d.rows.filter((x) => !q || (x.student + ' ' + x.student_id).toLowerCase().includes(q.toLowerCase()));
    r = r.slice().sort(sort === 'name' ? (a, b) => a.student.localeCompare(b.student)
      : sort === 'class' ? (a, b) => (a.class_name + (a.arm_name || '')).localeCompare(b.class_name + (b.arm_name || '')) || b.balance - a.balance
        : (a, b) => b.balance - a.balance);
    return r;
  }, [d.rows, q, sort]);
  const copy = async () => {
    const txt = rows.map((r, i) => `${i + 1}. ${r.student} (${r.class_name}${r.arm_name ? ' ' + r.arm_name : ''}) — ${naira(r.balance)}`).join('\n');
    try { await navigator.clipboard.writeText(txt); notify('success', `Copied ${rows.length} names — paste into WhatsApp or a message.`); }
    catch (_) { notify('error', 'Could not copy on this device.'); }
  };
  const T = d.totals;
  return (
    <Shell d={d} icon="fa-user-clock" title="Owing" sub={`${d.rows.length} students · ${naira(T.balance)} outstanding`}
      actions={<>
        <TermPick d={d} onChange={(v) => go({ term_id: v })} />
        {d.rows.length > 0 && <Menu label="Remind" items={[
          { icon: 'fa-paper-plane', label: 'Message parents (SMS / WhatsApp)', href: d.message_url, native: true },
          { icon: 'fa-copy', label: 'Copy list for WhatsApp', onClick: copy },
        ]} />}
      </>}>
      <Tiles items={[
        { label: 'Students owing', value: d.rows.length, sub: 'with a balance' },
        { label: 'Outstanding', value: nairaShort(T.balance), sub: naira(T.balance), tone: T.balance > 0 ? 'bad' : 'good' },
        { label: 'Paid so far', value: nairaShort(T.paid), sub: `${pct(T.paid, T.billed)}% of their bills`, tone: 'good' },
        { label: 'Their bills', value: nairaShort(T.billed), sub: 'after discounts' },
      ]} />
      <div className="rs-pick">
        <Chips value={d.class_id} onChange={(v) => go({ class_id: v })} label="Class"
          items={[{ value: '', label: 'All classes' }, ...d.classes.map((c) => ({ value: c.id, label: c.name }))]} />
        <div className="fn-tools">
          <label className="rs-search"><i className="fas fa-search" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student" aria-label="Find a student" /></label>
          <Seg value={sort} onChange={setSort} label="Sort" options={[{ value: 'balance', label: 'Largest' }, { value: 'class', label: 'Class' }, { value: 'name', label: 'A–Z' }]} />
        </div>
      </div>
      <Card flush>
        {rows.length ? (
          <div className="fn-list cols">
            {rows.map((r, i) => (
              <div className="fn-row" key={i}>
                <Avatar name={r.student} gender={r.gender} />
                <div className="fn-row-t">
                  <strong>{r.student}<small> · {r.class_name}{r.arm_name ? ' ' + r.arm_name : ''}</small></strong>
                  <span>Paid {naira(r.paid)} of {naira(r.billed)}</span>
                  <Meter value={r.paid} max={r.billed} />
                </div>
                <b className="fn-amt bad">{naira(r.balance)}</b>
                <div className="fn-acts">
                  <A to={r.statement_url} className="rs-icon-btn fn-ic" title="Statement"><i className="fas fa-file-lines" aria-hidden="true" /></A>
                  {canWrite(d, 'payments_create') && <A to={r.record_url} className="rs-btn sm primary" title="Take payment"><i className="fas fa-cash-register" aria-hidden="true" /><span>Pay</span></A>}
                </div>
              </div>))}
          </div>
        ) : <Blank icon="fa-circle-check" title={d.rows.length ? 'No one matches' : 'No outstanding fees'}>{d.rows.length ? 'Try another name.' : 'Every enrolled student has cleared their bill for this selection.'}</Blank>}
      </Card>
    </Shell>
  );
}

// ---- Collections (day-book) -----------------------------------------------------
function iso(dt) { return dt.toISOString().slice(0, 10); }
function Collections({ d }) {
  const nav = useNav();
  const ref = useRef();
  useLineChart(ref, d.day_chart || [], chartPalette().green);
  const go = (extra) => navParams(nav.go, d.self_url, { from: d.from_date, to: d.to_date, term_id: d.term_id, ...extra });
  const today = new Date();
  const day = 864e5;
  const mon = new Date(today.getTime() - ((today.getDay() + 6) % 7) * day);
  const presets = [
    ['Today', iso(today), iso(today)], ['Yesterday', iso(new Date(today - day)), iso(new Date(today - day))],
    ['This week', iso(mon), iso(today)], ['This month', iso(new Date(today.getFullYear(), today.getMonth(), 1)), iso(today)],
    ['Last 30 days', iso(new Date(today - 29 * day)), iso(today)],
  ];
  const cur = presets.find((p) => p[1] === d.from_date && p[2] === d.to_date);
  const top = (d.method_rows || [])[0];
  return (
    <Shell d={d} icon="fa-calendar-day" title="Collections" sub={`${d.from_label} – ${d.to_label}`} sub2={reportNav(d)}
      actions={canWrite(d, 'payments_export') && <a href={d.export_url} className="rs-btn" data-native download><i className="fas fa-file-csv" aria-hidden="true" /><span>Export</span></a>}>
      <div className="rs-pick">
        <Chips value={cur ? cur[0] : ''} onChange={(v) => { const p = presets.find((x) => x[0] === v); go({ from: p[1], to: p[2] }); }} label="Period"
          items={presets.map((p) => ({ value: p[0], label: p[0] }))} />
        <div className="rs-pick-row">
          <label className="rs-sel"><span>From</span><input type="date" value={d.from_date} onChange={(e) => go({ from: e.target.value })} /></label>
          <label className="rs-sel"><span>To</span><input type="date" value={d.to_date} onChange={(e) => go({ to: e.target.value })} /></label>
          <label className="rs-sel grow"><span>Term</span>
            <select value={d.term_id || ''} onChange={(e) => go({ term_id: e.target.value })}>
              <option value="">All terms</option>{d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
        </div>
      </div>
      <Tiles items={[
        { label: 'Collected', value: nairaShort(d.total), sub: naira(d.total), tone: 'good' },
        { label: 'Payments', value: d.count, sub: 'receipts issued' },
        { label: 'Average', value: nairaShort(d.count ? d.total / d.count : 0), sub: 'per payment' },
        top && { label: 'Top method', value: top.method, sub: nairaShort(top.amount) },
      ]} />
      <div className="fn-grid2 wide">
        <Card icon="fa-chart-column" title="Day by day"><div className="fn-chart">{(d.day_chart || []).length ? <canvas ref={ref} /> : <Blank icon="fa-chart-column" title="No payments in this period" />}</div></Card>
        <Card icon="fa-wallet" title="By method"><BarList rows={d.method_rows || []} labelKey="method" colorful empty="No payments in this period." /></Card>
      </div>
      <Card flush icon="fa-receipt" title={`Payments (${d.count})`}>
        {(d.payments || []).length ? <div className="fn-list cols">{d.payments.map((p) => <PayRow key={p.id} p={p} d={d} />)}</div>
          : <Blank icon="fa-receipt" title="No collections in this period" />}
      </Card>
    </Shell>
  );
}

// ---- Expenses ---------------------------------------------------------------------
function ExpenseSheet({ d, e, onClose, notify }) {
  const nav = useNav();
  const blank = { description: '', amount: '', category_id: '', expense_date: d.today, payee: '', method: (d.methods || ['Cash'])[0] };
  const [f, setF] = useState(e ? { description: e.description, amount: String(e.amount), category_id: e.category_id || '', expense_date: e.expense_date, payee: e.payee, method: e.method } : blank);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (ev) => {
    ev.preventDefault();
    if (!f.description.trim() || !(num(f.amount) > 0)) { notify('error', 'Enter a description and a positive amount.'); return; }
    setBusy(true);
    const r = await submitJson(e ? e.edit_url : d.urls.add, e ? f : { ...f, term_id: d.term_id || '' });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Saved.'); onClose(); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <Sheet title={e ? 'Edit expense' : 'Record an expense'} onClose={onClose}>
      <form onSubmit={submit} className="fn-sheet">
        <label className="fn-big sm"><span>₦</span><input type="number" inputMode="decimal" min="0" step="50" autoFocus required value={f.amount} onChange={(x) => set('amount', x.target.value)} placeholder="0" aria-label="Amount" /></label>
        <label className="rs-sel"><span>What was it for?</span><input type="text" required value={f.description} onChange={(x) => set('description', x.target.value)} placeholder="e.g. June electricity bill" /></label>
        <div className="fn-lbl">Category</div>
        <Chips value={f.category_id} onChange={(v) => set('category_id', v)} label="Category"
          items={[{ value: '', label: 'None' }, ...d.categories.map((c) => ({ value: c.id, label: c.name }))]} />
        <div className="fn-fields">
          <label className="rs-sel"><span>Date</span><input type="date" value={f.expense_date} onChange={(x) => set('expense_date', x.target.value)} /></label>
          <label className="rs-sel"><span>Paid to</span><input type="text" value={f.payee} onChange={(x) => set('payee', x.target.value)} placeholder="Optional" /></label>
        </div>
        <div className="fn-lbl">Method</div>
        <Seg value={f.method} onChange={(v) => set('method', v)} label="Method" options={(d.methods || []).map((m) => ({ value: m, label: m }))} />
        <button type="submit" className="rs-btn primary wide" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{e ? 'Save changes' : 'Record expense'}</button>
      </form>
    </Sheet>
  );
}

function CategorySheet({ d, onClose, notify }) {
  const nav = useNav();
  const [name, setName] = useState('');
  const act = async (url, fields, msg) => {
    if (msg && !await confirm(msg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); if (fields && fields.name) setName(''); } else notify('error', r.error || 'Failed.');
  };
  return (
    <Sheet title="Expense categories" onClose={onClose}>
      <div className="fn-cats">{d.categories.map((c) => (
        <span key={c.id} className="rs-chip">{c.name}
          {canWrite(d, 'expenses_delete') && <button type="button" className="fn-x" aria-label={`Delete ${c.name}`} onClick={() => act(c.delete_url, {}, `Delete category ${c.name}?`)}><i className="fas fa-xmark" aria-hidden="true" /></button>}</span>))}
      </div>
      {canWrite(d, 'expenses_create') && (
        <form className="fn-tools" onSubmit={(e) => { e.preventDefault(); if (name.trim()) act(d.urls.add_category, { name }); }}>
          <label className="rs-search"><i className="fas fa-folder-plus" aria-hidden="true" /><input value={name} onChange={(e) => setName(e.target.value)} placeholder="New category, e.g. Security" aria-label="New category" /></label>
          <button type="submit" className="rs-btn primary">Add</button>
        </form>)}
    </Sheet>
  );
}

function Expenses({ d, notify }) {
  const nav = useNav();
  const [sheet, setSheet] = useState(null);   // 'new' | expense | 'cats'
  const [q, setQ] = useState('');
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, category_id: d.category_id, ...extra });
  const del = async (e) => {
    if (!await confirm(`Delete this expense (${naira(e.amount)})?`)) return;
    const r = await submitJson(e.delete_url, {});
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const list = d.expenses.filter((e) => !q || (e.description + ' ' + e.payee + ' ' + e.category).toLowerCase().includes(q.toLowerCase()));
  const top = d.cat_summary[0];
  const catTotal = Object.fromEntries(d.cat_summary.map((c) => [c.name, c.amount]));
  return (
    <Shell d={d} icon="fa-money-bill-trend-up" title="Expenses" sub={`${d.expenses.length} expenses · ${naira(d.total)}`}
      actions={<>
        <TermPick d={d} onChange={(v) => go({ term_id: v })} allLabel="All terms" />
        {canWrite(d, 'expenses_create') && <button type="button" className="rs-btn primary" onClick={() => setSheet('new')}><i className="fas fa-plus" aria-hidden="true" /><span>Record expense</span></button>}
        <Menu items={[{ icon: 'fa-folder-tree', label: 'Manage categories', onClick: () => setSheet('cats') },
          { icon: 'fa-chart-column', label: 'Finance reports', href: d.reports_url }]} />
      </>}>
      <Tiles items={[
        { label: 'Total spent', value: nairaShort(d.total), sub: naira(d.total), tone: 'bad' },
        { label: 'Expenses', value: d.expenses.length, sub: 'recorded' },
        top && { label: 'Biggest category', value: top.name, sub: `${nairaShort(top.amount)} · ${pct(top.amount, d.total)}%` },
      ]} />
      <div className="rs-pick">
        <Chips value={d.category_id} onChange={(v) => go({ category_id: v })} label="Category"
          items={[{ value: '', label: 'All', sub: nairaShort(d.total) }, ...d.categories.map((c) => ({ value: c.id, label: c.name, sub: catTotal[c.name] ? nairaShort(catTotal[c.name]) : undefined }))]} />
        <label className="rs-search"><i className="fas fa-search" aria-hidden="true" /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search description or payee" aria-label="Search expenses" /></label>
      </div>
      <Card flush>
        {list.length ? (
          <div className="fn-list">
            {list.map((e) => (
              <div className="fn-row" key={e.id}>
                <span className="fn-eic"><i className="fas fa-money-bill-trend-up" aria-hidden="true" /></span>
                <div className="fn-row-t"><strong>{e.description}</strong>
                  <span>{e.category || 'Uncategorised'} · {e.date}{e.payee ? ' · ' + e.payee : ''}</span></div>
                <MethodPill m={e.method} />
                <b className="fn-amt">{naira(e.amount)}</b>
                {(canWrite(d, 'expenses_edit') || canWrite(d, 'expenses_delete')) && <Menu label="" items={[
                  canWrite(d, 'expenses_edit') && { icon: 'fa-pen', label: 'Edit', onClick: () => setSheet(e) },
                  canWrite(d, 'expenses_delete') && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => del(e) }]} />}
              </div>))}
          </div>
        ) : <Blank icon="fa-money-bill-wave" title="No expenses here">Record school spending to see your true net position.</Blank>}
      </Card>
      {sheet === 'cats' && <CategorySheet d={d} notify={notify} onClose={() => setSheet(null)} />}
      {sheet && sheet !== 'cats' && <ExpenseSheet d={d} e={sheet === 'new' ? null : sheet} notify={notify} onClose={() => setSheet(null)} />}
    </Shell>
  );
}

// ---- Fee setup: structure -------------------------------------------------------
function Structure({ d, notify }) {
  const nav = useNav();
  const init = () => { const m = {}; d.items.forEach((i) => { m[i.id] = i.amount === '' ? '' : String(i.amount); }); return m; };
  const [amounts, setAmounts] = useState(init);
  const [copyOpen, setCopyOpen] = useState(false);
  const [copyFrom, setCopyFrom] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { setAmounts(init()); }, [d.items]); // eslint-disable-line react-hooks/exhaustive-deps
  // Open straight on the first class instead of an empty "pick a class" screen.
  useEffect(() => { if (d.term_id && !d.class_id && d.classes.length) go({ class_id: d.classes[0].id }); }, [d.class_id]); // eslint-disable-line react-hooks/exhaustive-deps
  const total = d.items.reduce((t, i) => t + num(amounts[i.id]), 0);
  const saved = d.items.reduce((t, i) => t + num(i.amount), 0);
  const dirty = d.items.some((i) => String(amounts[i.id] ?? '') !== String(i.amount === '' ? '' : i.amount));
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id, ...extra });
  const save = async (e) => {
    if (e) e.preventDefault();
    const fields = { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id || '' };
    d.items.forEach((i) => { fields['amount_' + i.id] = amounts[i.id]; });
    setBusy(true);
    const r = await submitJson(d.urls.save, fields);
    setBusy(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not save.');
  };
  const clear = async () => {
    if (!await confirm('Remove ALL fee amounts for this class this term?')) return;
    const r = await submitJson(d.urls.clear, { term_id: d.term_id, class_id: d.class_id, arm_id: d.arm_id || '' });
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not clear.');
  };
  const copy = async () => {
    if (!copyFrom) { notify('error', 'Choose the term to copy from.'); return; }
    const r = await submitJson(d.urls.copy, { from_term_id: copyFrom, to_term_id: d.term_id });
    setCopyOpen(false);
    if (r.ok) { notify('success', r.message); nav.refresh(); } else notify('error', r.error || 'Could not copy.');
  };
  const cls = d.classes.find((c) => String(c.id) === String(d.class_id));
  return (
    <Shell d={d} icon="fa-table-list" title="Fee setup" sub="How much each class pays per term" sub2={setupNav(d)}
      actions={<>
        <TermPick d={d} onChange={(v) => go({ term_id: v })} />
        <Menu items={[
          canWrite(d, 'structure_bulk') && { icon: 'fa-copy', label: 'Copy every class from another term', onClick: () => setCopyOpen(true) },
          canWrite(d, 'structure_delete') && d.has_current && { icon: 'fa-trash', label: "Clear this class's fees", danger: true, onClick: clear },
          { icon: 'fa-tags', label: 'Manage fee items', href: d.items_url }]} />
      </>}>
      <div className="rs-pick">
        <div className="fn-lbl">Class</div>
        <Chips value={d.class_id} onChange={(v) => go({ class_id: v, arm_id: '' })} label="Class" items={d.classes.map((c) => ({ value: c.id, label: c.name }))} />
        {d.class_id && d.arms.length > 0 && (<>
          <div className="fn-lbl">Arm <small>— leave on “All arms” unless one arm pays differently</small></div>
          <Chips value={d.arm_id} onChange={(v) => go({ arm_id: v })} label="Arm" items={[{ value: '', label: 'All arms' }, ...d.arms.map((a) => ({ value: a.id, label: a.name }))]} />
        </>)}
      </div>
      {d.term_id && d.class_id ? (d.items.length ? (
        <form id="fnStructForm" className="rs-card fn-struct" onSubmit={save}>
          <div className="rs-card-h"><h3><i className="fas fa-school" aria-hidden="true" />{cls ? cls.name : 'Class'}{d.arm_id && d.arms.find((a) => String(a.id) === String(d.arm_id)) ? ' ' + d.arms.find((a) => String(a.id) === String(d.arm_id)).name : ' · all arms'}</h3>
            <span className="fn-total">Per student <b>{naira(total)}</b></span></div>
          {d.items.map((it) => (
            <label className="fn-fee" key={it.id}>
              <span className="n"><strong>{it.name}</strong>{it.description && <small>{it.description}</small>}</span>
              <span className="fn-money"><i>₦</i><input type="number" inputMode="decimal" min="0" step="100" placeholder="0" value={amounts[it.id] ?? ''}
                disabled={!canWrite(d, 'structure_edit')} onChange={(e) => setAmounts((m) => ({ ...m, [it.id]: e.target.value }))} aria-label={`${it.name} amount`} /></span>
            </label>))}
          {canWrite(d, 'structure_edit') ? (
            <Bar>
              <div className="rs-bar-t"><b>{naira(total)} per student</b><small>{dirty ? `Unsaved · was ${naira(saved)}` : 'All changes saved'}</small></div>
              <button type="submit" form="fnStructForm" className="rs-btn primary" disabled={busy || !dirty}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />Save fees</button>
            </Bar>
          ) : <p className="rs-muted fn-pad">You can view but not edit the fee structure.</p>}
        </form>
      ) : <Blank icon="fa-tags" title="No fee items yet"><p>Create the fees you charge first, then set amounts here.</p><A to={d.items_url} className="rs-btn primary">Add fee items</A></Blank>)
        : <Blank icon="fa-hand-pointer" title="Pick a class">Choose a class above to set what it pays this term.</Blank>}
      {copyOpen && (
        <Sheet title="Copy fees from another term" onClose={() => setCopyOpen(false)}>
          <p className="rs-muted">Copies every class's fee structure into this term. Amounts already set here are kept.</p>
          <label className="rs-sel"><span>Copy from</span>
            <select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">Choose a term…</option>
              {d.terms.filter((t) => String(t.id) !== String(d.term_id)).map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          <button type="button" className="rs-btn primary wide" style={{ marginTop: '.9rem' }} onClick={copy}><i className="fas fa-copy" aria-hidden="true" />Copy into this term</button>
        </Sheet>)}
    </Shell>
  );
}

// ---- Fee setup: items -----------------------------------------------------------
function Items({ d, notify }) {
  const nav = useNav();
  const [f, setF] = useState({ name: '', description: '' });
  const [edit, setEdit] = useState(null);
  const act = async (url, fields, msg) => {
    if (msg && !await confirm(msg)) return false;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); nav.refresh(); return true; }
    notify('error', r.error || 'Action failed.'); return false;
  };
  const add = async (e) => {
    e.preventDefault();
    if (!f.name.trim()) { notify('error', 'Give the fee a name.'); return; }
    if (await act(d.add_url, f)) setF({ name: '', description: '' });
  };
  const active = d.items.filter((i) => i.is_active).length;
  return (
    <Shell d={d} icon="fa-tags" title="Fee setup" sub={`${d.items.length} fee items · ${active} active`} sub2={setupNav(d)}
      actions={<A to={d.structure_url} className="rs-btn"><i className="fas fa-table-list" aria-hidden="true" /><span>Set amounts</span></A>}>
      {canWrite(d, 'structure_create') && (
        <form className="rs-pick fn-additem" onSubmit={add}>
          <div className="rs-pick-row">
            <label className="rs-sel grow"><span>New fee</span><input value={f.name} onChange={(e) => setF((x) => ({ ...x, name: e.target.value }))} placeholder="e.g. Tuition, Development levy, PTA" /></label>
            <label className="rs-sel grow"><span>Note (optional)</span><input value={f.description} onChange={(e) => setF((x) => ({ ...x, description: e.target.value }))} placeholder="Shown under the fee name" /></label>
            <button type="submit" className="rs-btn primary fn-end"><i className="fas fa-plus" aria-hidden="true" />Add</button>
          </div>
        </form>)}
      <Card flush>
        {d.items.length ? (
          <div className="fn-list">
            {d.items.map((it) => (
              <div className={'fn-row' + (it.is_active ? '' : ' off')} key={it.id}>
                <span className="fn-eic tag"><i className="fas fa-tag" aria-hidden="true" /></span>
                <div className="fn-row-t"><strong>{it.name}</strong><span>{it.description || 'No note'}</span></div>
                <span className={'fn-pill ' + (it.is_active ? 'good' : '')}>{it.is_active ? 'Active' : 'Inactive'}</span>
                {(canWrite(d, 'structure_edit') || canWrite(d, 'structure_delete')) && <Menu label="" items={[
                  canWrite(d, 'structure_edit') && { icon: 'fa-pen', label: 'Edit', onClick: () => setEdit(it) },
                  canWrite(d, 'structure_edit') && { icon: it.is_active ? 'fa-eye-slash' : 'fa-eye', label: it.is_active ? 'Make inactive' : 'Make active', onClick: () => act(it.edit_url, { name: it.name, description: it.description || '', is_active: it.is_active ? '' : 'on' }) },
                  canWrite(d, 'structure_delete') && { icon: 'fa-trash', label: 'Delete', danger: true, onClick: () => act(it.delete_url, {}, `Delete fee item ${it.name}?`) }]} />}
              </div>))}
          </div>
        ) : <Blank icon="fa-tags" title="No fee items yet">Add the fees your school charges to get started.</Blank>}
      </Card>
      {edit && <ItemSheet it={edit} notify={notify} onClose={() => setEdit(null)} />}
    </Shell>
  );
}
function ItemSheet({ it, notify, onClose }) {
  const nav = useNav();
  const [f, setF] = useState({ name: it.name, description: it.description || '', is_active: it.is_active });
  const submit = async (e) => {
    e.preventDefault();
    const r = await submitJson(it.edit_url, { ...f, is_active: f.is_active ? 'on' : '' });
    if (r.ok) { notify('success', r.message || 'Updated.'); onClose(); nav.refresh(); } else notify('error', r.error || 'Could not update.');
  };
  return (
    <Sheet title="Edit fee item" onClose={onClose}>
      <form className="fn-sheet" onSubmit={submit}>
        <label className="rs-sel"><span>Name</span><input value={f.name} autoFocus onChange={(e) => setF((x) => ({ ...x, name: e.target.value }))} /></label>
        <label className="rs-sel"><span>Note</span><input value={f.description} onChange={(e) => setF((x) => ({ ...x, description: e.target.value }))} /></label>
        <label className="rs-check"><input type="checkbox" checked={f.is_active} onChange={(e) => setF((x) => ({ ...x, is_active: e.target.checked }))} /> Active (charged and shown on bills)</label>
        <button type="submit" className="rs-btn primary wide"><i className="fas fa-check" aria-hidden="true" />Save</button>
      </form>
    </Sheet>
  );
}

// ---- Statement --------------------------------------------------------------------
function Statement({ d, notify }) {
  const nav = useNav();
  const s = d.student;
  const bill = d.bill;
  const [copied, setCopied] = useState(false);
  const [disc, setDisc] = useState(null);   // 'new' | discount
  const act = async (url, fields, msg, follow) => {
    if (msg && !await confirm(msg)) return;
    const r = await submitJson(url, fields || {});
    if (r.ok) { notify('success', r.message); follow ? nav.go(r.redirect) : nav.refresh(); } else notify('error', r.error || 'Action failed.');
  };
  const paidPct = bill ? pct(bill.paid, bill.payable) : 0;
  return (
    <Shell d={d} icon="fa-file-invoice" title={s.full_name} sub={`${s.student_id}${s.gender ? ' · ' + s.gender : ''} · fee statement`}
      actions={<>
        <TermPick d={d} onChange={(v) => navParams(nav.go, d.self_url, { term_id: v })} />
        {canWrite(d, 'payments_create') && <A to={d.urls.record_payment} className="rs-btn primary"><i className="fas fa-cash-register" aria-hidden="true" /><span>Take payment</span></A>}
        {canWrite(d, 'payments_create') && d.pay_enabled && bill && bill.balance > 0.005 && <Menu items={[
          { icon: 'fa-link', label: 'Create online payment link', onClick: () => act(d.urls.payment_link, { term_id: d.term_id }, null, true) }]} />}
      </>}>
      {d.paylink && (
        <Card icon="fa-link" title="Payment link for the parent">
          <div className="fn-tools">
            <label className="rs-search"><i className="fas fa-link" aria-hidden="true" /><input readOnly value={d.paylink} aria-label="Payment link" onFocus={(e) => e.target.select()} /></label>
            <button type="button" className="rs-btn primary" onClick={() => { navigator.clipboard.writeText(d.paylink); setCopied(true); }}><i className={'fas ' + (copied ? 'fa-check' : 'fa-copy')} aria-hidden="true" />{copied ? 'Copied' : 'Copy'}</button>
            <a className="rs-btn" href={d.paylink} target="_blank" rel="noopener noreferrer"><i className="fas fa-up-right-from-square" aria-hidden="true" />Open</a>
          </div>
          <p className="rs-muted">The payment is recorded automatically once the parent completes it.</p>
        </Card>)}
      {bill ? (<>
        <Tiles items={[
          { label: 'Bill', value: nairaShort(bill.payable), sub: bill.discount > 0 ? `${nairaShort(bill.discount)} discount applied` : 'this term' },
          { label: 'Paid', value: nairaShort(bill.paid), sub: `${paidPct}% of the bill`, tone: 'good' },
          { label: 'Balance', value: nairaShort(bill.balance), sub: bill.balance > 0.005 ? 'still owing' : 'fully paid', tone: bill.balance > 0.005 ? 'bad' : 'good' },
          { label: 'Payments', value: d.payments.length, sub: 'this term' },
        ]} />
        <div className="fn-grid2">
          <Card icon="fa-file-invoice" title="Bill"><BillCard bill={bill} /></Card>
          <Card icon="fa-receipt" title={`Payments (${d.payments.length})`} flush>
            {d.payments.length ? (
              <div className="fn-list">{d.payments.map((p) => (
                <div className="fn-row" key={p.id}>
                  <span className="fn-eic good"><i className="fas fa-check" aria-hidden="true" /></span>
                  <div className="fn-row-t"><strong>{naira(p.amount)}</strong><span><a href={p.receipt_url} data-native>{p.receipt_no}</a> · {p.date}</span></div>
                  <MethodPill m={p.method} />
                  {canWrite(d, 'payments_edit') ? <Menu label="" items={[{ icon: 'fa-receipt', label: 'Receipt', href: p.receipt_url, native: true }, { icon: 'fa-pen', label: 'Edit', href: p.edit_url }]} />
                    : <a className="rs-icon-btn fn-ic" href={p.receipt_url} data-native title="Receipt"><i className="fas fa-receipt" aria-hidden="true" /></a>}
                </div>))}</div>
            ) : <Blank icon="fa-receipt" title="No payments yet" />}
          </Card>
        </div>
        <Card icon="fa-tag" title="Discounts & waivers" right={canWrite(d, 'discounts_create') && <button type="button" className="rs-btn sm" onClick={() => setDisc('new')}><i className="fas fa-plus" aria-hidden="true" />Add</button>}>
          {d.discounts.length ? (
            <div className="fn-list">{d.discounts.map((dc) => (
              <div className="fn-row" key={dc.id}>
                <span className="fn-eic tag"><i className="fas fa-tag" aria-hidden="true" /></span>
                <div className="fn-row-t"><strong>{dc.reason || 'Discount'}</strong></div>
                <b className="fn-amt good">− {naira(dc.amount)}</b>
                {(canWrite(d, 'discounts_edit') || canWrite(d, 'discounts_delete')) && <Menu label="" items={[
                  canWrite(d, 'discounts_edit') && { icon: 'fa-pen', label: 'Edit', onClick: () => setDisc(dc) },
                  canWrite(d, 'discounts_delete') && { icon: 'fa-trash', label: 'Remove', danger: true, onClick: () => act(dc.delete_url, {}, 'Remove this discount?') }]} />}
              </div>))}</div>
          ) : <p className="rs-muted">No discounts — sibling, staff-ward or scholarship reductions go here.</p>}
        </Card>
      </>) : <Blank icon="fa-hand-pointer" title="Pick a term">Choose a term to see this student's bill.</Blank>}
      {disc && <DiscountSheet d={d} dc={disc === 'new' ? null : disc} act={act} onClose={() => setDisc(null)} />}
    </Shell>
  );
}
function DiscountSheet({ d, dc, act, onClose }) {
  const [f, setF] = useState({ amount: dc ? String(dc.amount) : '', reason: dc ? dc.reason : '' });
  const submit = async (e) => {
    e.preventDefault();
    await act(dc ? dc.edit_url : d.urls.add_discount, dc ? f : { ...f, student_id: d.student_id, term_id: d.term_id });
    onClose();
  };
  return (
    <Sheet title={dc ? 'Edit discount' : 'Add a discount or waiver'} onClose={onClose}>
      <form className="fn-sheet" onSubmit={submit}>
        <label className="fn-big sm"><span>₦</span><input type="number" min="0" step="100" required autoFocus value={f.amount} onChange={(e) => setF((x) => ({ ...x, amount: e.target.value }))} aria-label="Amount" placeholder="0" /></label>
        <div className="fn-lbl">Reason</div>
        <Chips value={f.reason} onChange={(v) => setF((x) => ({ ...x, reason: v }))} label="Common reasons"
          items={['Sibling discount', 'Staff ward', 'Scholarship', 'Early payment'].map((r) => ({ value: r, label: r }))} />
        <label className="rs-sel"><span>Or type a reason</span><input value={f.reason} onChange={(e) => setF((x) => ({ ...x, reason: e.target.value }))} /></label>
        <button type="submit" className="rs-btn primary wide"><i className="fas fa-check" aria-hidden="true" />{dc ? 'Save' : 'Add discount'}</button>
      </form>
    </Sheet>
  );
}

// ---- Reports ------------------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const maxV = Math.max(num(d.payable), num(d.collected), num(d.expenses), 1);
  const pl = [
    ['Expected (after discounts)', d.payable, ''], ['Collected', d.collected, 'good'], ['Outstanding', d.outstanding, 'bad'],
    ['Spent (expenses)', d.expenses, 'mid'],
  ];
  return (
    <Shell d={d} icon="fa-chart-column" title="Reports" sub={d.selected_term || 'Term summary'} sub2={reportNav(d)}
      actions={<>
        <TermPick d={d} onChange={(v) => navParams(nav.go, d.self_url, { term_id: v })} />
        {canWrite(d, 'reports_export') && d.export_url && <a href={d.export_url} className="rs-btn" data-native download><i className="fas fa-file-excel" aria-hidden="true" /><span>Excel</span></a>}
      </>}>
      <div className="fn-grid2">
        <Card icon="fa-scale-balanced" title="Income & spending">
          <div className="fn-pl">
            {pl.map(([l, v, t]) => (
              <div className="fn-pl-r" key={l}><span className="n">{l}</span><b className={t}>{naira(v)}</b>
                <span className="t"><i className={t} style={{ width: (num(v) / maxV * 100) + '%' }} /></span></div>))}
            <div className="fn-pl-sum">
              <span>Collection rate <b>{d.rate}%</b></span>
              <span>Discounts <b>{naira(d.discounts)}</b></span>
            </div>
            <div className={'fn-net ' + (d.net >= 0 ? 'good' : 'bad')}><span>Net cash position</span><b>{naira(d.net)}</b></div>
          </div>
        </Card>
        <Card icon="fa-layer-group" title="Expected income by fee"><BarList rows={d.item_breakdown || []} colorful empty="No fee structure for this term." /></Card>
      </div>
      <Card icon="fa-school" title="Collection by class" flush>
        {(d.class_rows || []).length ? (
          <div className="fn-list">{d.class_rows.map((r) => (
            <div className="fn-row" key={r.name}>
              <span className={'fn-rate ' + toneOf(r.rate)}>{Math.round(r.rate)}%</span>
              <div className="fn-row-t"><strong>{r.name}<small> · {r.students} students</small></strong>
                <span>{naira(r.collected)} of {naira(r.expected)}</span><Meter value={r.collected} max={r.expected} /></div>
              <b className={'fn-amt ' + (r.outstanding > 0 ? 'bad' : 'good')}>{r.outstanding > 0 ? naira(r.outstanding) : 'Cleared'}<small>{r.outstanding > 0 ? 'owing' : ''}</small></b>
            </div>))}</div>
        ) : <Blank icon="fa-school" title="No data for this term" />}
      </Card>
      <Card icon="fa-wallet" title="Payments by method"><BarList rows={d.method_rows || []} labelKey="method" colorful empty="No payments yet." extra={(r) => ` · ${r.count} payments`} /></Card>
    </Shell>
  );
}

// ---- Edit payment -------------------------------------------------------------
function EditPayment({ d, notify }) {
  const nav = useNav();
  const p = d.payment;
  const [f, setF] = useState({ amount: String(p.amount), payment_date: p.payment_date, method: p.method, reference: p.reference || '', received_by: p.received_by || '', notes: p.notes || '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!(num(f.amount) > 0)) { notify('error', 'Enter a positive amount.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!await confirm(`Delete receipt ${p.receipt_no} (${naira(p.amount)})?`)) return;
    const r = await submitJson(d.delete_url, {});
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not delete.');
  };
  return (
    <Shell d={d} icon="fa-pen" title="Edit payment" sub={`${p.student} · receipt ${p.receipt_no}`}
      actions={canWrite(d, 'payments_delete') && <button type="button" className="rs-btn danger" onClick={del}><i className="fas fa-trash" aria-hidden="true" /><span>Delete</span></button>}>
      <form id="fnEditPayForm" className="rs-card fn-form fn-narrow" onSubmit={submit}>
        <div className="fn-who-h">
          <Avatar name={p.student} />
          <div><strong>{p.student}</strong><span>{p.student_id_label} · {p.term}</span></div>
          {d.bill && <span className={'fn-pill ' + (d.bill.balance > 0.005 ? 'bad' : 'good')}>Balance {naira(d.bill.balance)}</span>}
        </div>
        <label className="fn-big"><span>₦</span><input type="number" inputMode="decimal" min="0" step="50" required value={f.amount} onChange={(e) => set('amount', e.target.value)} aria-label="Amount" /></label>
        <div className="fn-lbl">Method</div>
        <Seg value={f.method} onChange={(v) => set('method', v)} label="Method" options={(d.methods || []).map((m) => ({ value: m, label: m, icon: METHOD_IC[m] }))} />
        <div className="fn-fields">
          <label className="rs-sel"><span>Date</span><input type="date" value={f.payment_date} onChange={(e) => set('payment_date', e.target.value)} /></label>
          <label className="rs-sel"><span>Reference / teller no.</span><input value={f.reference} onChange={(e) => set('reference', e.target.value)} /></label>
          <label className="rs-sel"><span>Received by</span><input value={f.received_by} onChange={(e) => set('received_by', e.target.value)} /></label>
          <label className="rs-sel"><span>Notes</span><input value={f.notes} onChange={(e) => set('notes', e.target.value)} /></label>
        </div>
        <Bar>
          <div className="rs-bar-t"><b>{naira(num(f.amount))}</b><small>was {naira(p.amount)}</small></div>
          <a href={d.receipt_url} className="rs-btn ghost" data-native>Cancel</a>
          <button type="submit" form="fnEditPayForm" className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />Save changes</button>
        </Bar>
      </form>
    </Shell>
  );
}

const SCREENS = { dashboard: Dashboard, collections: Collections, items: Items, structure: Structure,
  payments: Payments, record_payment: RecordPayment, statement: Statement, defaulters: Defaulters,
  expenses: Expenses, reports: Reports, edit_payment: EditPayment };

export default function FinanceApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = (tone, text) => setToast({ tone, text });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        <Screen d={d} notify={notify} />
        {toast && <Toast tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      </SectionShell>
    </NavCtx.Provider>
  );
}
