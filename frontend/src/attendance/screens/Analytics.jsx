import React, { useState, useRef, useEffect } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired } from '../../components/ui';
import { Tiles, Card, Ring, Person, MoreMenu, Seg, pctTone, fmtPct, fmtNum, UnmarkedNote } from '../kit';

const pctHex = (p) => (p >= 75 ? 'var(--success)' : p >= 50 ? 'var(--warning)' : 'var(--danger)');

// Horizontal % bars (class/branch ranking, trend as a column chart reused below).
function Bars({ rows, labelKey, valueKey }) {
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  return (
    <div className="att-bars">
      {rows.map((r, i) => (
        <div className="att-bar-row" key={i}>
          <div className="att-bar-lbl" title={r[labelKey]}>{r[labelKey]}</div>
          <div className="att-bar-track"><div className="att-bar-fill"
            style={{ width: Math.max(2, r[valueKey]) + '%', background: pctHex(r[valueKey]) }} /></div>
          <div className="att-bar-val">{fmtPct(r[valueKey])}</div>
        </div>))}
    </div>
  );
}

// Weekly trend: fixed to its card's width however many weeks the term has.
// Values sit on the bars only when there's room; otherwise tap / hover a week
// to read it in the header line. 50% and 75% guides + the term average.
function ColumnChart({ rows }) {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  const [sel, setSel] = useState(null);
  useEffect(() => {
    const el = ref.current; if (!el) return undefined;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  if (!rows || !rows.length) return <p className="att-sub">No data.</p>;
  const n = rows.length;
  const roomy = w / n >= 46;
  const everyLbl = w / n >= 26 ? 1 : Math.ceil(26 / Math.max(1, w / n));
  const avg = rows.reduce((a, t) => a + (t.percentage || 0), 0) / n;
  const best = rows.reduce((b, t) => (t.percentage > b.percentage ? t : b), rows[0]);
  const worst = rows.reduce((b, t) => (t.percentage < b.percentage ? t : b), rows[0]);
  const cur = sel != null ? rows[sel] : null;
  return (
    <div className="att-tc" ref={ref}>
      <div className="att-tc-read" aria-live="polite">
        {cur
          ? <><b>{cur.label}</b><span className={'ak-pct ' + pctTone(cur.percentage)}>{fmtPct(cur.percentage)}</span>
              <small>{cur.percentage >= avg ? '+' : ''}{fmtNum(cur.percentage - avg)} vs average</small></>
          : <><span>Average <b>{fmtPct(avg)}</b></span><span className="sep" /><span>Best <b>{best.label}</b> {fmtPct(best.percentage)}</span><span className="sep" /><span>Lowest <b>{worst.label}</b> {fmtPct(worst.percentage)}</span></>}
      </div>
      <div className="att-tc-plot" role="img" aria-label={`Weekly attendance, average ${fmtPct(avg)}`}>
        {[75, 50].map((g) => <span key={g} className="att-tc-guide" style={{ bottom: g + '%' }}><i>{g}%</i></span>)}
        <span className="att-tc-avg" style={{ bottom: avg + '%' }} title={`Average ${fmtPct(avg)}`} />
        {rows.map((t, i) => (
          <button type="button" key={i} className={'att-tc-col' + (sel === i ? ' on' : '')}
                  onClick={() => setSel(sel === i ? null : i)} onMouseEnter={() => setSel(i)} onMouseLeave={() => setSel(null)}
                  aria-label={`${t.label}: ${fmtPct(t.percentage)}`} title={`${t.label}: ${fmtPct(t.percentage)}`}>
            {roomy && <span className="v">{Math.round(t.percentage)}%</span>}
            <span className="b" style={{ height: Math.max(3, Math.min(100, t.percentage)) + '%', background: pctHex(t.percentage) }} />
          </button>))}
      </div>
      <div className="att-tc-x">
        {rows.map((t, i) => <span key={i}>{i % everyLbl === 0 ? t.label : ''}</span>)}
      </div>
    </div>
  );
}

function HeatStrip({ rows }) {
  const vals = rows.filter((r) => r.percentage > 0);
  const low = vals.length ? vals.reduce((a, b) => (b.percentage < a.percentage ? b : a)) : null;
  return (
    <div className="an2-days" role="img" aria-label="Attendance by weekday">
      {rows.map((r, i) => (
        <div key={i} className={'an2-day' + (low && r.label === low.label ? ' low' : '')} title={`${r.label}: ${fmtPct(r.percentage)}`}>
          <span className="d">{r.label}</span>
          <span className="t"><i style={{ height: Math.max(3, Math.min(100, r.percentage)) + '%', background: r.percentage ? pctHex(r.percentage) : 'transparent' }} /></span>
          <b className={pctTone(r.percentage)}>{r.percentage ? Math.round(r.percentage) + '%' : '—'}</b>
        </div>))}
    </div>
  );
}

const Delta = ({ v, unit = ' pts', label }) => (v == null ? null : (
  <span className={'an2-delta ' + (v > 0 ? 'up' : v < 0 ? 'down' : '')}>
    <i className={'fas ' + (v > 0 ? 'fa-arrow-up' : v < 0 ? 'fa-arrow-down' : 'fa-minus')} aria-hidden="true" />
    {v > 0 ? '+' : ''}{fmtNum(v)}{unit}{label ? <small> {label}</small> : null}
  </span>));

// The four attendance bands as one stacked bar + legend.
function Spread({ dist, total, onPick }) {
  const bands = [
    { k: 'excellent', t: 'Excellent', r: '90% +', c: 'var(--success)' },
    { k: 'good', t: 'Good', r: '75–89%', c: 'color-mix(in srgb,var(--success) 55%,#a3e635)' },
    { k: 'fair', t: 'Fair', r: '50–74%', c: 'var(--warning)', pick: 'risk' },
    { k: 'poor', t: 'Poor', r: 'under 50%', c: 'var(--danger)', pick: 'chronic' },
  ];
  return (
    <div className="an2-spread">
      <div className="an2-stack" role="img" aria-label="Students by attendance band">
        {bands.map((b) => dist[b.k] > 0 && (
          <i key={b.k} style={{ flexGrow: dist[b.k], background: b.c }} title={`${b.t}: ${dist[b.k]}`} />))}
      </div>
      <ul className="an2-legend">
        {bands.map((b) => {
          const body = (<><span className="sw" style={{ background: b.c }} /><span className="nm">{b.t}<small>{b.r}</small></span>
            <b>{dist[b.k]}</b><span className="pc">{total ? fmtPct(Math.round(dist[b.k] / total * 1000) / 10) : '—'}</span>
            {b.pick && dist[b.k] > 0 ? <i className="fas fa-chevron-right go" aria-hidden="true" /> : <span className="go" />}</>);
          return (
            <li key={b.k}>{b.pick && dist[b.k] > 0
              ? <button type="button" onClick={() => onPick(b.pick)}>{body}</button>
              : <div>{body}</div>}</li>);
        })}
      </ul>
    </div>
  );
}

function ClassRow({ c, rank }) {
  return (
    <li className="an2-cls">
      <a href={`/attendance/app?tab=termly&assignment_id=${c.caa_id}`}>
        <span className="rk">{rank}</span>
        <span className="nm">{c.class}
          <small>{c.students} student{c.students === 1 ? '' : 's'}
            {c.below ? <> · <span className="w">{c.below} below target</span></> : null}
            {c.chronic ? <> · <span className="b">{c.chronic} chronic</span></> : null}</small></span>
        <span className="tr"><i style={{ width: Math.max(2, Math.min(100, c.percentage)) + '%', background: pctHex(c.percentage) }} /></span>
        <span className={'ak-pct ' + pctTone(c.percentage)}>{fmtPct(c.percentage)}</span>
      </a>
    </li>
  );
}

export default function Analytics() {
  const { term, online } = useCtx();
  const tid = term ? String(term.id) : '';
  const [view, setView] = useState('overview');
  const [who, setWho] = useState('chronic');
  const [sort, setSort] = useState('high');
  const [q, setQ] = useState('');
  const [notifyChannel, setNotifyChannel] = useState('SMS');
  const [notifying, setNotifying] = useState(false);
  const notifyLow = async () => {
    setNotifying(true);
    try {
      const r = await apiPost('/attendance/api/notify/low', { term_id: tid, channel: notifyChannel });
      if (r && r.ok && r.redirect) window.location.href = r.redirect;
      else alert((r && r.error) || 'Could not draft the notice.');
    } catch (e) { alert(e.message || 'Could not draft the notice.'); }
    setNotifying(false);
  };
  const [state] = useAsync(
    () => (online && tid ? apiGet(`/attendance/api/analytics?term_id=${tid}`) : Promise.resolve(null)),
    [tid, online]);
  const d = state.data;
  const goStudents = (w) => { setWho(w); setQ(''); setView('students'); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  if (!online) return <div className="md"><div className="md-card"><OfflineRequired what="Attendance analytics" /></div></div>;
  if (state.loading) return <div className="md"><div className="md-card"><Spinner label="Crunching attendance analytics…" /></div></div>;
  if (state.error) return <div className="md"><div className="md-card"><ErrorState detail={state.error.message} /></div></div>;
  if (!d) return <div className="md"><div className="md-card"><EmptyState icon="fa-chart-line" title="No term selected" hint="Pick a term at the top to see analytics." /></div></div>;

  const k = d.kpis;
  const dist = d.distribution;
  const total = dist.excellent + dist.good + dist.fair + dist.poor;
  const below = d.below_list || d.chronic_list || [];
  const chronic = below.filter((s) => s.percentage < d.critical);
  const risk = below.filter((s) => s.percentage >= d.critical);
  const improved = d.most_improved || [];
  const declined = d.most_declined || [];
  const trend = d.trend || [];
  const wk = trend.length ? trend[trend.length - 1] : null;
  const wkPrev = trend.length > 1 ? trend[trend.length - 2] : null;
  const vsPrev = k.prev_overall != null ? Math.round((k.overall - k.prev_overall) * 100) / 100 : null;
  const days = (d.heatmap || []).filter((h) => h.percentage > 0);
  const lowDay = days.length > 1 ? days.reduce((a, b) => (b.percentage < a.percentage ? b : a)) : null;
  const topDay = days.length > 1 ? days.reduce((a, b) => (b.percentage > a.percentage ? b : a)) : null;
  const ranked = d.class_rank || [];
  const DAYN = { Mon: 'Mondays', Tue: 'Tuesdays', Wed: 'Wednesdays', Thu: 'Thursdays', Fri: 'Fridays' };

  const say = [];
  if (vsPrev != null && d.prev_term) say.push(vsPrev === 0 ? `Level with ${d.prev_term}.` : `${vsPrev > 0 ? 'Up' : 'Down'} ${fmtNum(Math.abs(vsPrev))} points on ${d.prev_term} for the same students.`);
  if (below.length) say.push(`${k.below_threshold || below.length} student${(k.below_threshold || below.length) === 1 ? ' is' : 's are'} below the ${d.threshold}% target${chronic.length ? `, ${chronic.length} of them under ${d.critical}%` : ''}.`);
  else if (k.students) say.push(`Every student is at or above the ${d.threshold}% target.`);
  if (lowDay && topDay && topDay.percentage - lowDay.percentage >= 2) say.push(`${DAYN[lowDay.label] || lowDay.label} are the weakest day.`);

  const lists = {
    chronic: { rows: chronic, label: `Under ${d.critical}%`, empty: `No student is under ${d.critical}% this term.` },
    risk: { rows: risk, label: `${d.critical}–${d.threshold}%`, empty: `No student is between ${d.critical}% and ${d.threshold}%.` },
    improved: { rows: improved, label: 'Improved', empty: d.prev_term ? `Nobody improved on ${d.prev_term}.` : 'No previous term to compare with.' },
    declined: { rows: declined, label: 'Slipping', empty: d.prev_term ? `Nobody slipped since ${d.prev_term}.` : 'No previous term to compare with.' },
  };
  const ql = q.trim().toLowerCase();
  const match = (s) => !ql || (s.name + ' ' + s.class + ' ' + (s.student_id || '')).toLowerCase().includes(ql);
  const cur = lists[who];
  const rows = cur.rows.filter(match);
  const classes = ranked.filter((c) => !ql || c.class.toLowerCase().includes(ql)).slice()
    .sort(sort === 'low' ? (a, b) => a.percentage - b.percentage : sort === 'az' ? (a, b) => a.class.localeCompare(b.class, undefined, { numeric: true }) : (a, b) => b.percentage - a.percentage);
  const rankOf = new Map(ranked.map((c, i) => [c.caa_id, i + 1]));

  return (
    <div className="md an2">
      <div className={'ak-hero an2-hero' + (k.overall < d.threshold ? ' warn' : '')}>
        <Ring pct={k.overall} label="Overall" size={104} />
        <div className="ak-hero-t">
          <span className="ak-kick"><span>{k.school_days} school days</span><span>{k.students} students</span><span>{k.classes} classes</span></span>
          <strong>School attendance</strong>
          {say.length > 0 && <p className="an2-say">{say.join(' ')}</p>}
          <div className="ak-hero-chips">
            {vsPrev != null && <span className="ak-chip"><Delta v={vsPrev} label={`vs ${d.prev_term}`} /></span>}
            {wk && wkPrev && <span className="ak-chip"><Delta v={Math.round((wk.percentage - wkPrev.percentage) * 100) / 100} label="this week" /></span>}
          </div>
        </div>
        <div className="an2-acts no-print">
          <a className="ak-btn" href={`/attendance/analytics/export?term_id=${tid}&format=xlsx`}><i className="fas fa-file-excel" aria-hidden="true" /><span> Excel</span></a>
          <MoreMenu up={false} label="More export options" items={[
            { icon: 'fa-file-csv', label: 'Download CSV', href: `/attendance/analytics/export?term_id=${tid}&format=csv` },
            { icon: 'fa-print', label: 'Print this page', onClick: () => window.print() },
          ]} />
        </div>
      </div>

      <UnmarkedNote classes={d.unmarked_classes} what="the analytics" />

      <div className="an2-tabs no-print">
        <Seg label="Section" value={view} onChange={(v) => { setView(v); setQ(''); }} options={[
          { value: 'overview', label: 'Overview', icon: 'fa-gauge' },
          { value: 'classes', label: 'Classes', icon: 'fa-ranking-star', count: ranked.length },
          { value: 'students', label: 'Students', icon: 'fa-user-group', count: below.length || null },
        ]} />
      </div>

      {view === 'overview' && (
        <>
          <Tiles items={[
            wk && { label: 'This week', value: fmtPct(wk.percentage), sub: wkPrev ? `${wk.percentage >= wkPrev.percentage ? '+' : ''}${fmtNum(wk.percentage - wkPrev.percentage)} pts on last week` : wk.label, tone: pctTone(wk.percentage) },
            { label: `Below ${d.threshold}%`, value: k.below_threshold != null ? k.below_threshold : below.length, sub: 'need watching', tone: below.length ? 'warn' : 'good', onClick: () => goStudents(risk.length ? 'risk' : 'chronic') },
            { label: `Chronic (<${d.critical}%)`, value: k.chronic, sub: 'need follow-up', tone: k.chronic ? 'bad' : 'good', onClick: () => goStudents('chronic') },
            d.prev_term ? { label: 'Improved', value: improved.length, sub: `vs ${d.prev_term}`, tone: improved.length ? 'good' : '', onClick: () => goStudents('improved') }
              : { label: 'Present sessions', value: (k.present_sessions || 0).toLocaleString(), sub: `of ${(k.total_opened || 0).toLocaleString()}` },
          ]} />

          <div className="ak-grid2">
            <Card icon="fa-chart-column" title="Week by week" sub="Attendance rate each week"><ColumnChart rows={trend} /></Card>
            <Card icon="fa-users-viewfinder" title="How students are spread" sub={`${total} students by their term rate`}>
              <Spread dist={dist} total={total} onPick={goStudents} /></Card>
            <Card icon="fa-calendar-week" title="By weekday" sub={lowDay ? `Lowest on ${DAYN[lowDay.label] || lowDay.label}` : 'Which days pupils miss most'}>
              <HeatStrip rows={d.heatmap} /></Card>
            <Card icon="fa-ranking-star" title="Classes" sub={ranked.length > 6 ? 'Top and bottom three' : 'Highest to lowest'} flush>
              {ranked.length === 0 ? <p className="ak-empty">No class has marked attendance yet.</p> : (
                <ul className="an2-clist">
                  {(ranked.length > 6 ? [...ranked.slice(0, 3), null, ...ranked.slice(-3)] : ranked).map((c, i) => (c
                    ? <ClassRow key={c.caa_id} c={c} rank={rankOf.get(c.caa_id)} />
                    : <li key={'gap' + i} className="an2-gap" aria-hidden="true"><span>⋯</span></li>))}
                </ul>)}
              {ranked.length > 0 && <button type="button" className="an2-all" onClick={() => { setView('classes'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
                See all {ranked.length} classes <i className="fas fa-chevron-right" aria-hidden="true" /></button>}
            </Card>
            {d.branch_rank.length > 1 && (
              <Card icon="fa-code-branch" title="Branches" sub="Highest to lowest"><Bars rows={d.branch_rank} labelKey="branch" valueKey="percentage" /></Card>)}
          </div>
        </>
      )}

      {view === 'classes' && (
        <Card icon="fa-ranking-star" title="All classes" sub={`${ranked.length} class${ranked.length === 1 ? '' : 'es'} · tap one for its termly report`} flush
              action={<Seg label="Sort" value={sort} onChange={setSort} options={[
                { value: 'high', label: 'Highest' }, { value: 'low', label: 'Lowest' }, { value: 'az', label: 'A–Z' }]} />}>
          {ranked.length > 8 && (
            <div className="an2-find"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a class…" aria-label="Find a class" /></div>)}
          {classes.length === 0 ? <p className="ak-empty">{ranked.length ? 'No class matches.' : 'No class has marked attendance yet.'}</p> : (
            <ul className="an2-clist">{classes.map((c) => <ClassRow key={c.caa_id} c={c} rank={rankOf.get(c.caa_id)} />)}</ul>)}
        </Card>
      )}

      {view === 'students' && (
        <Card icon="fa-user-group" title="Students to watch" sub={cur.label} flush
              action={(who === 'chronic' || who === 'risk') && below.length > 0 && (
                <span className="ak-notify no-print">
                  <select value={notifyChannel} onChange={(e) => setNotifyChannel(e.target.value)} aria-label="Channel">
                    <option>SMS</option><option>Email</option></select>
                  <button type="button" className="ak-btn primary" disabled={notifying} onClick={notifyLow} title="Drafts a message for review — nothing sends automatically">
                    <i className="fas fa-comment-sms" aria-hidden="true" /><span> Notify parents</span></button>
                </span>)}>
          <div className="an2-who">
            <Seg label="Show" value={who} onChange={setWho} options={[
              { value: 'chronic', label: `Under ${d.critical}%`, count: chronic.length },
              { value: 'risk', label: 'At risk', count: risk.length },
              { value: 'improved', label: 'Improved', count: improved.length },
              { value: 'declined', label: 'Slipping', count: declined.length },
            ]} />
          </div>
          {cur.rows.length > 6 && (
            <div className="an2-find"><i className="fas fa-magnifying-glass" aria-hidden="true" />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a student or class…" aria-label="Find a student" /></div>)}
          {cur.rows.length === 0
            ? <EmptyState icon={who === 'improved' || who === 'declined' ? 'fa-scale-balanced' : 'fa-circle-check'} title="Nobody here" hint={cur.empty} />
            : rows.length === 0 ? <p className="ak-empty">No student matches “{q}”.</p>
            : (
              <ul className="ak-people">
                {rows.map((s) => (who === 'improved' || who === 'declined'
                  ? <Person key={s.id + '|' + s.class} name={s.name} sub={`${s.class} · ${fmtPct(s.from)} → ${fmtPct(s.to)}`}
                            href={`/attendance/app?student_id=${s.id}#/student`}
                            right={<span className={'ak-pct ' + (s.delta > 0 ? 'good' : 'bad')}>{s.delta > 0 ? '+' : ''}{fmtNum(s.delta)}</span>} />
                  : <Person key={s.id + '|' + s.class} name={s.name} gender={s.gender} sub={`${s.class}${s.student_id ? ' · ' + s.student_id : ''}`}
                            tone={s.percentage < d.critical ? 'out' : ''} href={`/attendance/app?student_id=${s.id}#/student`}
                            right={<span className={'ak-pct ' + pctTone(s.percentage)}>{fmtPct(s.percentage)}</span>} />))}
              </ul>)}
          {(who === 'chronic' || who === 'risk') && below.length > 0 && <p className="ak-foot">Notify parents drafts a message for you to review — nothing sends automatically.</p>}
          {(who === 'improved' || who === 'declined') && d.prev_term && cur.rows.length > 0 && <p className="ak-foot">Compared with each student’s {d.prev_term} rate. Classes whose register wasn’t taken that term are left out.</p>}
        </Card>
      )}
    </div>
  );
}
