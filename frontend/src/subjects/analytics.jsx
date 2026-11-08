// Class analytics + institution analytics, rebuilt on the results kit: the
// decision first (key takeaways / recommendations), then tabs so a laptop
// needs little scrolling and a phone gets one focused panel at a time.
import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useNav, navParams } from '../lib/section';
import { canWrite } from '../lib/perms';
import { Head, Picker, Flow, Tiles, Seg, Menu, Ring, Meter, Blank, Avatar, fmtNum, tone, subLine, usePhone } from './results';

const r1 = (v) => (v == null ? null : Math.round(Number(v) * 10) / 10);
const toneOf = (v, pm) => (v == null ? '' : v >= 70 ? 'good' : v >= pm ? 'mid' : 'bad');

// ── small charts (plain DOM so text never stretches) ───────────────────────
function HBars({ rows, max = 100, pct, pm = 50, label = (r) => r.label, value = (r) => r.value, sub, onRow }) {
  const m = Math.max(1, max === 'auto' ? Math.max(...rows.map(value)) : max);
  return (
    <div className="an-hbars">
      {rows.map((r, i) => {
        const v = value(r);
        const Tag = onRow ? 'button' : 'div';
        return (
          <Tag key={i} type={onRow ? 'button' : undefined} className={'an-hbar' + (onRow ? ' click' : '')} onClick={onRow ? () => onRow(r) : undefined}>
            <span className="l" title={label(r)}>{label(r)}{sub && <small>{sub(r)}</small>}</span>
            <span className="t"><i className={max === 'auto' ? 'n' : toneOf(v, pm)} style={{ width: `${Math.max(0, Math.min(100, (v / m) * 100))}%` }} /></span>
            <b>{v == null ? '–' : fmtNum(r1(v))}{pct ? '%' : ''}</b>
          </Tag>
        );
      })}
    </div>
  );
}

function Cols({ bars, pm = 50 }) {
  const m = Math.max(1, ...bars.map((b) => b.value));
  return (
    <div className="an-cols">
      {bars.map((b, i) => {
        const lo = parseInt(b.label, 10);
        const t = Number.isFinite(lo) ? (lo >= 70 ? 'good' : lo >= pm ? 'mid' : 'bad') : 'n';
        return (
          <div key={i} className="an-col" title={`${b.label}: ${b.value}`}>
            <em>{b.value || ''}</em>
            <span><i className={b.tone || t} style={{ height: `${(b.value / m) * 100}%` }} /></span>
            <small>{b.label}</small>
          </div>
        );
      })}
    </div>
  );
}

function Card({ icon, title, sub, action, children, className = '' }) {
  return (
    <section className={'rs-card an-card ' + className}>
      {(title || action) && (
        <header className="rs-card-h">
          <h3>{icon && <i className={'fas ' + icon} aria-hidden="true" />} {title}</h3>
          {sub && <small>{sub}</small>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

function PassRing({ rate, assessed }) {
  const passed = Math.round(((rate || 0) / 100) * (assessed || 0));
  return (
    <div className="an-pass">
      <Ring value={rate} size={120} label="pass" />
      <div className="an-pass-l">
        <span><i className="good" /> <b>{passed}</b> passed</span>
        <span><i className="bad" /> <b>{(assessed || 0) - passed}</b> below pass</span>
      </div>
    </div>
  );
}

function Insights({ items, limit }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = limit && !all ? items.slice(0, limit) : items;
  return (
    <>
    <section className="an-insights">
      {shown.map((it, i) => (
        <div key={i} className={'an-ins ' + (it.tone || 'insight')}>
          <i className={'fas ' + ({ positive: 'fa-circle-check', negative: 'fa-triangle-exclamation', watch: 'fa-eye' }[it.tone] || 'fa-lightbulb')} aria-hidden="true" />
          <div><strong>{it.title}</strong><span>{it.text}</span></div>
        </div>
      ))}
    </section>
    {limit && items.length > limit && <button type="button" className="rs-link" onClick={() => setAll((v) => !v)}>{all ? 'Show fewer' : `Show all ${items.length} recommendations`}</button>}
    </>
  );
}

function Trend({ trends, pm, showPass }) {
  const names = trends.term_names;
  return (
    <div className="an-trend">
      <Card icon="fa-chart-line" title="Average score by term">
        <HBars pm={pm} rows={names.map((n, i) => ({ label: n, value: trends.averages[i] }))} value={(r) => r.value ?? 0} />
      </Card>
      {showPass && trends.pass_rates && (
        <Card icon="fa-percent" title="Pass rate by term">
          <HBars pm={50} pct rows={names.map((n, i) => ({ label: n, value: trends.pass_rates[i] }))} value={(r) => r.value ?? 0} />
        </Card>
      )}
      {trends.subjects && trends.subjects.length > 0 && (
        <Card icon="fa-book" title="Subjects across terms" className="wide">
          <div className="an-tbl-wrap"><table className="an-tbl">
            <thead><tr><th>Subject</th>{names.map((n) => <th key={n} className="r">{n}</th>)}</tr></thead>
            <tbody>{trends.subjects.map((s) => (
              <tr key={s.name}><td>{s.name}</td>
                {s.values.map((v, i) => {
                  const p = i > 0 ? s.values[i - 1] : null;
                  const d = v != null && p != null ? v - p : null;
                  return <td key={i} className={'r ' + toneOf(v, pm)}>{v == null ? '–' : fmtNum(r1(v))}
                    {d != null && Math.abs(d) >= 0.5 && <span className={'an-delta ' + (d > 0 ? 'up' : 'down')}>{d > 0 ? '▲' : '▼'}{fmtNum(r1(Math.abs(d)))}</span>}</td>;
                })}</tr>))}</tbody>
          </table></div>
        </Card>
      )}
    </div>
  );
}

function StudentList({ rows, pm, link, empty, showClass, good }) {
  if (!rows.length) return <p className="rs-muted rs-pad">{empty}</p>;
  return (
    <div className="an-people">
      {rows.map((st, i) => (
        <div key={st.id || i} className="an-person">
          <span className="an-rank">{i + 1}</span>
          <Avatar name={st.name} />
          <span className="n"><b>{st.name}</b><small>{[showClass && st.class, st.failed != null && `${st.failed} subject${st.failed === 1 ? '' : 's'} failing`].filter(Boolean).join(' · ')}</small></span>
          <b className={'v ' + (good ? 'good' : tone(st.average, pm))}>{fmtNum(r1(st.average))}</b>
          {link && st.id && <a className="rs-icon-btn an-card-btn" href={link(st.id)} data-native title="Report card" aria-label={`Report card for ${st.name}`}><i className="fas fa-id-card" aria-hidden="true" /></a>}
        </div>
      ))}
    </div>
  );
}

// Class-level takeaways worked out from the payload (no extra request).
function classTakeaways(a, s) {
  const out = [];
  const subs = (a.subjects || []).filter((x) => x.assessed);
  if (subs.length > 1) {
    const sorted = subs.slice().sort((x, y) => x.average - y.average);
    const lo = sorted[0]; const hi = sorted[sorted.length - 1];
    out.push({ tone: lo.pass_rate < 50 ? 'negative' : 'watch', title: `${lo.name} is the hardest subject`, text: `Average ${fmtNum(r1(lo.average))}, ${fmtNum(r1(lo.pass_rate))}% passing. ${hi.name} is the strongest at ${fmtNum(r1(hi.average))}.` });
  }
  if (a.intervention && a.intervention.length) out.push({ tone: 'negative', title: `${a.intervention.length} student${a.intervention.length === 1 ? '' : 's'} need attention`, text: `Averaging below the pass mark of ${s.pass_mark}. See the Students tab.` });
  else out.push({ tone: 'positive', title: 'Everyone is above the pass mark', text: `All ${s.assessed} assessed students average ${s.pass_mark} or more.` });
  const g = a.gender || [];
  if (g.length === 2 && Math.abs(g[0].average - g[1].average) >= 5) {
    const [hi, lo] = g[0].average > g[1].average ? [g[0], g[1]] : [g[1], g[0]];
    out.push({ tone: 'watch', title: `${hi.group} are ahead`, text: `Average ${fmtNum(r1(hi.average))} vs ${fmtNum(r1(lo.average))} for ${lo.group.toLowerCase()}.` });
  }
  if (s.completion != null && s.completion < 90) out.push({ tone: 'watch', title: `${fmtNum(r1(100 - s.completion))}% of scores missing`, text: 'Figures will shift as the remaining scores are entered.' });
  if (s.trend != null && Math.abs(s.trend) >= 1) out.push({ tone: s.trend > 0 ? 'positive' : 'negative', title: `${s.trend > 0 ? 'Up' : 'Down'} ${fmtNum(r1(Math.abs(s.trend)))} on last term`, text: `Class average moved from ${fmtNum(r1(s.class_average - s.trend))} to ${fmtNum(r1(s.class_average))}.` });
  return out.slice(0, 4);
}

function SubjectRows({ subjects, pm, open, setOpen }) {
  return (
    <div className="an-subjects">
      {subjects.map((sub) => {
        const isOpen = open === sub.id;
        return (
          <div key={sub.id} className={'an-subj' + (isOpen ? ' open' : '')}>
            <button type="button" className="an-subj-top" onClick={() => sub.assessed && setOpen(isOpen ? null : sub.id)} aria-expanded={isOpen} disabled={!sub.assessed}>
              <span className="n"><b>{sub.name}</b><small>{sub.assessed ? `${sub.assessed} assessed · high ${fmtNum(r1(sub.highest))} · low ${fmtNum(r1(sub.lowest))}` : 'No scores yet'}</small></span>
              <Meter value={sub.average || 0} max={100} tone={toneOf(sub.average, pm)} />
              <b className={'v ' + toneOf(sub.average, pm)}>{sub.assessed ? fmtNum(r1(sub.average)) : '–'}</b>
              <span className={'an-pill ' + (sub.pass_rate >= 50 ? 'good' : 'bad')}>{sub.assessed ? `${fmtNum(r1(sub.pass_rate))}%` : '–'}</span>
              <i className="fas fa-chevron-down" aria-hidden="true" />
            </button>
            {isOpen && (
              <div className="an-subj-more">
                <div><small>Grades</small><Cols pm={pm} bars={(sub.grades || []).map((g) => ({ label: g.grade, value: g.count, tone: 'n' }))} /></div>
                <div><small>Score bands</small><Cols pm={pm} bars={(sub.bands || []).map((b) => ({ label: b.band, value: b.count }))} /></div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Class analytics ────────────────────────────────────────────────────────
export function Analytics({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, assignment_id: d.assignment_id, ...extra });
  const a = d.analytics;
  const s = (a && a.summary) || {};
  const pm = s.pass_mark || 50;
  const [tab, setTab] = useState('overview');
  const [open, setOpen] = useState(null);
  const cardLink = canWrite(d, 'reportcard_view') && canWrite(d, 'cards') ? (id) => `${d.report_card_base}${id}?term_id=${d.term_id}` : null;
  const ready = d.has_selection && a && s.assessed;
  const hasTrend = ready && a.trends && a.trends.term_names.length > 1;
  const menu = [
    ready && d.urls.report_pdf && { icon: 'fa-file-pdf', label: 'Download report (PDF)', href: d.urls.report_pdf, native: true, download: true },
    d.has_selection && { icon: 'fa-rotate', label: 'Recalculate now', onClick: () => { nav.go(d.refresh_url); notify('success', 'Recalculating…'); } },
    d.urls.institution && { icon: 'fa-building-columns', label: 'Whole-school analytics', href: d.urls.institution },
    d.assignment_id && { icon: 'fa-table', label: 'Broadsheet', href: d.urls.broadsheet },
    d.assignment_id && { icon: 'fa-pen', label: 'Enter scores', href: d.urls.scores },
  ];
  const tabs = [
    { value: 'overview', label: 'Overview', icon: 'fa-chart-pie' },
    { value: 'subjects', label: 'Subjects', icon: 'fa-book', count: ready ? a.subjects.length : null },
    { value: 'students', label: 'Students', icon: 'fa-users', count: ready ? a.intervention.length || null : null },
    hasTrend && { value: 'trend', label: 'Trend', icon: 'fa-chart-line' },
  ].filter(Boolean);
  return (
    <div className="rs">
      <Head icon="fa-chart-column" title="Class analytics" sub={subLine(d) || 'How a class performed this term'}><Menu items={menu} label="Actions" /></Head>
      <Picker d={d} go={go} />
      <Flow d={d} current="" />
      {!d.has_selection ? (
        <Blank icon="fa-chart-column" title="Choose a class"><p>Pick a term and class to see its grades, hardest subjects and the students who need help.</p></Blank>
      ) : !ready ? (
        <Blank icon="fa-chart-column" title="No scores yet"><p>Enter some scores for this class to unlock analytics.</p>
          {d.urls.scores && <a className="rs-btn primary" href={d.urls.scores}><i className="fas fa-pen" aria-hidden="true" /> Enter scores</a>}</Blank>
      ) : (<>
        <Tiles items={[
          { label: 'Class average', value: fmtNum(r1(s.class_average)), tone: toneOf(s.class_average, pm),
            sub: s.trend != null ? `${s.trend >= 0 ? '▲' : '▼'} ${fmtNum(r1(Math.abs(s.trend)))} vs last term` : `pass mark ${pm}` },
          { label: 'Pass rate', value: fmtNum(r1(s.pass_rate)), unit: '%', tone: s.pass_rate >= 50 ? 'good' : 'bad', sub: `${s.assessed} of ${s.students} assessed` },
          { label: 'Highest average', value: fmtNum(r1(s.highest)), sub: s.top_student || '', tone: 'good' },
          { label: 'Lowest average', value: fmtNum(r1(s.lowest)), tone: toneOf(s.lowest, pm) },
          { label: 'Scores entered', value: fmtNum(r1(s.completion)), unit: '%', tone: s.completion >= 90 ? '' : 'mid' },
        ]} />
        <Insights items={classTakeaways(a, s)} />
        <Seg label="Section" value={tab} onChange={setTab} options={tabs.map((t) => (phone ? { ...t, label: t.label } : t))} />
        {tab === 'overview' && (
          <div className="an-grid">
            <Card icon="fa-circle-half-stroke" title="Pass vs below pass"><PassRing rate={s.pass_rate} assessed={s.assessed} /></Card>
            {a.score_bands && a.score_bands.length > 0 && <Card icon="fa-chart-simple" title="Spread of student averages"><Cols pm={pm} bars={a.score_bands.map((b) => ({ label: b.band, value: b.count }))} /></Card>}
            <Card icon="fa-award" title="Grade distribution"><HBars max="auto" rows={a.grade_distribution.map((g) => ({ label: `Grade ${g.grade}`, value: g.count }))} /></Card>
            {a.gender && a.gender.length > 0 && (
              <Card icon="fa-venus-mars" title="Boys and girls">
                <HBars pm={50} pct rows={a.gender} label={(g) => g.group} sub={(g) => `${g.count} · avg ${fmtNum(r1(g.average))}`} value={(g) => g.pass_rate} />
              </Card>
            )}
          </div>
        )}
        {tab === 'subjects' && (
          <Card icon="fa-book" title="Subjects, hardest first" sub="Tap a subject for its grade spread">
            <SubjectRows subjects={a.subjects} pm={pm} open={open} setOpen={setOpen} />
          </Card>
        )}
        {tab === 'students' && (
          <div className="an-grid two">
            <Card icon="fa-triangle-exclamation" title={`Needs attention (${a.intervention.length})`} sub={`Average below ${pm}`} className="warn">
              <StudentList rows={a.intervention} pm={pm} link={cardLink} empty="No students below the pass mark. 🎉" />
            </Card>
            <Card icon="fa-trophy" title="Top students">
              <StudentList rows={a.top_students} pm={pm} good empty="No results yet." />
            </Card>
          </div>
        )}
        {tab === 'trend' && hasTrend && <Trend trends={a.trends} pm={pm} />}
      </>)}
    </div>
  );
}

// ── Institution analytics ──────────────────────────────────────────────────
const FLAG = { strong: 'good', good: '', watch: 'mid', review: 'bad', compliance: 'bad', insufficient: 'muted' };

export function Institution({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const a = d.analytics;
  const s = (a && a.summary) || {};
  const pm = s.pass_mark || 50;
  const [auto, setAuto] = useState(!!d.auto_board_pack);
  const [tab, setTab] = useState('overview');
  const go = (extra) => navParams(nav.go, d.self_url, { term_id: d.term_id, scope: d.scope, scope_id: d.scope_id, ...extra });
  const sel = (a && a.selectors) || { sections: [], classes: [], arms: [] };
  const ready = a && s.assessed;
  const needsPick = d.scope !== 'school' && !d.scope_id;
  const cardLink = canWrite(d, 'reportcard_view') && canWrite(d, 'cards') ? (id) => `${d.report_card_base}${id}?term_id=${d.term_id}` : null;
  const emailOwners = async () => {
    const r = await submitJson(d.urls.email_report, { term_id: d.term_id, scope: d.scope, scope_id: d.scope_id });
    if (r.ok) notify('success', r.message); else notify('error', r.error || 'Could not send.');
  };
  const toggleAuto = async () => {
    const on = !auto; setAuto(on);
    const r = await submitJson(d.urls.toggle_auto, { enabled: on ? '1' : '0' });
    if (r.ok) notify('success', r.message); else { setAuto(!on); notify('error', r.error || 'Could not change.'); }
  };
  const exp = (fmt) => { const b = d.urls.report_base; return `${b}${b.includes('?') ? '&' : '?'}format=${fmt}`; };
  const term = (d.terms.find((t) => String(t.id) === String(d.term_id)) || {}).full_name || '';
  const menu = [
    { icon: 'fa-rotate', label: 'Recalculate now', onClick: () => { go({ refresh: 1 }); notify('success', 'Recalculating…'); } },
    ready && { heading: 'Board pack' },
    ready && { icon: 'fa-file-pdf', label: 'Download PDF', href: exp('pdf'), native: true, download: true },
    ready && { icon: 'fa-file-excel', label: 'Download Excel', href: exp('excel'), native: true, download: true },
    ready && { icon: 'fa-file-image', label: 'Download image', href: exp('image'), native: true, download: true },
    ready && d.is_admin && { icon: 'fa-envelope', label: 'Email to owners now', onClick: emailOwners },
    d.is_admin && { icon: auto ? 'fa-toggle-on' : 'fa-toggle-off', label: `Auto-email each term: ${auto ? 'On' : 'Off'}`, onClick: toggleAuto },
  ];
  const drillable = a && a.unit_kind !== 'Subject';
  const openTeacher = (r) => { if (r.name && r.name !== 'Unassigned') { const b = d.urls.teacher_base; nav.go(`${b}${b.includes('?') ? '&' : '?'}name=${encodeURIComponent(r.name)}`); } };
  const openSubject = (r) => { if (r.id && d.urls.subject_base) { const b = d.urls.subject_base; nav.go(`${b}${b.includes('?') ? '&' : '?'}subject_id=${r.id}`); } };
  const hasTrend = ready && a.trends && a.trends.term_names.length > 1 && a.trends.averages.some((v) => v != null);
  const msgUrl = ready && a.intervention.length && d.urls.compose
    ? `${d.urls.compose}?students=${a.intervention.map((x) => x.id).join(',')}&body=${encodeURIComponent('Dear Parent, this is to notify you that your ward is performing below expectations this term and would benefit from extra support at home. Please arrange to meet the class teacher. Thank you.')}` : null;
  const tabs = ready ? [
    { value: 'overview', label: 'Overview', icon: 'fa-chart-pie' },
    a.units && a.units.length > 0 && { value: 'league', label: phone ? 'League' : `${a.unit_kind} league`, icon: 'fa-ranking-star' },
    { value: 'subjects', label: 'Subjects', icon: 'fa-book' },
    { value: 'teachers', label: 'Teachers', icon: 'fa-chalkboard-user', count: a.teachers.length || null },
    { value: 'students', label: 'Students', icon: 'fa-users', count: a.intervention.length || null },
    hasTrend && { value: 'trend', label: 'Trend', icon: 'fa-chart-line' },
  ].filter(Boolean) : [];
  const levelOpts = [{ value: 'school', label: 'Whole school' }, { value: 'section', label: 'Section' }, { value: 'class', label: 'Class' }, { value: 'arm', label: 'Class arm' }];
  return (
    <div className="rs">
      <Head icon="fa-building-columns" title="Institution analytics" sub={a ? `${a.scope_label} · ${term}` : term}><Menu items={menu} label="Actions" /></Head>
      <section className="rs-pick">
        <div className="rs-pick-row">
          <label className="rs-sel"><span>Term</span>
            <select value={d.term_id} onChange={(e) => go({ term_id: e.target.value, scope: 'school', scope_id: '' })}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
          {d.scope !== 'school' && (
            <label className="rs-sel grow"><span>{levelOpts.find((l) => l.value === d.scope).label}</span>
              <select value={d.scope_id} onChange={(e) => go({ scope_id: e.target.value })}>
                <option value="">Choose…</option>
                {d.scope === 'section' && sel.sections.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                {d.scope === 'class' && sel.classes.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                {d.scope === 'arm' && sel.arms.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
              </select></label>
          )}
        </div>
        <div className="rs-pick-l"><span>Look at</span>
          <Seg label="Level" value={d.scope} onChange={(v) => go({ scope: v, scope_id: '' })} options={levelOpts} /></div>
      </section>
      {needsPick ? (
        <Blank icon="fa-layer-group" title={`Choose a ${d.scope === 'arm' ? 'class arm' : d.scope}`}><p>Pick one above to roll up its results.</p></Blank>
      ) : !ready ? (
        <Blank icon="fa-chart-column" title="No scores yet"><p>No scores have been entered for <b>{a ? a.scope_label : 'this selection'}</b> yet.</p></Blank>
      ) : (<>
        <Tiles items={[
          { label: 'Average score', value: fmtNum(r1(s.class_average)), tone: toneOf(s.class_average, pm), sub: `${s.assessed} of ${s.students} students` },
          { label: 'Pass rate', value: fmtNum(r1(s.pass_rate)), unit: '%', tone: s.pass_rate >= 50 ? 'good' : 'bad', sub: `pass mark ${pm}` },
          { label: 'Distinctions', value: fmtNum(r1(s.distinction_rate)), unit: '%', tone: 'good', sub: `average ${s.distinction_mark}+` },
          { label: 'Highest / lowest', value: `${fmtNum(r1(s.highest))}`, sub: `lowest ${fmtNum(r1(s.lowest))}` },
          { label: 'Scores entered', value: fmtNum(r1(s.completion)), unit: '%', tone: s.completion >= 85 ? '' : 'mid', sub: `${s.units} ${String(a.unit_kind || 'unit').toLowerCase()}${s.units === 1 ? '' : 's'}` },
        ]} />
        {a.recommendations && a.recommendations.length > 0 && (
          <div><h2 className="an-h2"><i className="fas fa-briefcase" aria-hidden="true" /> What to do next</h2><Insights items={a.recommendations} limit={3} /></div>
        )}
        <Seg label="Section" value={tab} onChange={setTab} options={tabs} />
        {tab === 'overview' && (
          <div className="an-grid">
            <Card icon="fa-circle-half-stroke" title="Pass vs below pass"><PassRing rate={s.pass_rate} assessed={s.assessed} /></Card>
            {a.score_bands && a.score_bands.length > 0 && <Card icon="fa-chart-simple" title="Spread of student averages"><Cols pm={pm} bars={a.score_bands.map((b) => ({ label: b.band, value: b.count }))} /></Card>}
            <Card icon="fa-award" title="Grade distribution"><HBars max="auto" rows={a.grade_distribution.map((g) => ({ label: `Grade ${g.grade}`, value: g.count }))} /></Card>
            {a.gender && a.gender.length > 0 && (
              <Card icon="fa-venus-mars" title="Boys and girls (pass rate)">
                <HBars pm={50} pct rows={a.gender} label={(g) => g.group} sub={(g) => `${g.count} · avg ${fmtNum(r1(g.average))}`} value={(g) => g.pass_rate} />
              </Card>
            )}
            {a.attendance && a.attendance.bands && a.attendance.bands.length > 0 && (
              <Card icon="fa-user-check" title="Attendance vs results" sub={a.attendance.correlation != null ? `link strength r = ${fmtNum(r1(a.attendance.correlation))}` : ''}>
                {a.attendance.correlation != null && <p className="an-note">{a.attendance.correlation >= 0.3 ? 'Attendance and scores move together — chasing absences should lift results.'
                  : a.attendance.correlation <= -0.1 ? 'Weak link — poor results here come more from teaching than absence.' : 'A mild link between attendance and scores.'} ({a.attendance.coverage} students)</p>}
                <HBars pm={pm} rows={a.attendance.bands} label={(b) => b.band} sub={(b) => `${b.count} students`} value={(b) => b.average} />
              </Card>
            )}
            {a.branches && a.branches.length > 0 && (
              <Card icon="fa-code-branch" title="Campus league">
                <HBars pm={pm} rows={a.branches} label={(b) => b.label} sub={(b) => `${b.students} students · ${fmtNum(r1(b.pass_rate))}% pass`} value={(b) => b.average} />
              </Card>
            )}
          </div>
        )}
        {tab === 'league' && (
          <Card icon="fa-ranking-star" title={`${a.unit_kind} league, best first`} sub={drillable ? 'Tap one to look inside it' : ''}>
            <div className="an-league">
              {a.units.map((u, i) => (
                <button type="button" key={i} className="an-league-row" disabled={!drillable} onClick={() => drillable && go({ scope: u.scope, scope_id: u.scope_id })}>
                  <span className={'rs-pos ' + (i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '')}>{i + 1}</span>
                  <span className="n"><b>{u.label}</b><small>{u.students} students · {fmtNum(r1(u.pass_rate))}% pass</small></span>
                  <Meter value={u.average || 0} max={100} tone={toneOf(u.average, pm)} />
                  <b className={'v ' + toneOf(u.average, pm)}>{fmtNum(r1(u.average))}</b>
                  {drillable && <i className="fas fa-chevron-right" aria-hidden="true" />}
                </button>
              ))}
            </div>
          </Card>
        )}
        {tab === 'subjects' && (
          <Card icon="fa-book" title="Subjects, hardest first" sub="Tap a subject for its scorecard">
            <div className="an-league">
              {a.subjects.map((x, i) => (
                <button type="button" key={i} className="an-league-row subj" onClick={() => openSubject(x)}>
                  <span className="n"><b>{x.name}</b><small>{x.assessed} assessed · {fmtNum(r1(x.pass_rate))}% pass</small></span>
                  <Meter value={x.average || 0} max={100} tone={toneOf(x.average, pm)} />
                  <b className={'v ' + toneOf(x.average, pm)}>{fmtNum(r1(x.average))}</b>
                  <i className="fas fa-chevron-right" aria-hidden="true" />
                </button>
              ))}
            </div>
          </Card>
        )}
        {tab === 'teachers' && (
          <Card icon="fa-chalkboard-user" title="Teacher effectiveness" sub="Tap a teacher for their scorecard">
            {a.teachers.length ? (
              <div className="an-league">
                {a.teachers.map((x, i) => (
                  <button type="button" key={i} className="an-league-row teacher" onClick={() => openTeacher(x)} disabled={x.name === 'Unassigned'}>
                    <Avatar name={x.name} />
                    <span className="n"><b>{x.name}</b><small>{x.subject_count} subject{x.subject_count === 1 ? '' : 's'} · {x.class_count} class{x.class_count === 1 ? '' : 'es'} · {fmtNum(r1(x.pass_rate))}% pass</small></span>
                    <span className={'an-pill ' + (FLAG[x.flag] || '')}>{x.verdict}</span>
                    <b className={'v ' + toneOf(x.average, pm)}>{fmtNum(r1(x.average))}</b>
                  </button>
                ))}
              </div>
            ) : <p className="rs-muted rs-pad">No teachers are linked to these subjects yet — set the teacher on each class subject.</p>}
          </Card>
        )}
        {tab === 'students' && (
          <div className="an-grid two">
            <Card icon="fa-triangle-exclamation" title={`Needs intervention (${a.intervention.length})`} className="warn"
                  action={msgUrl && <a href={msgUrl} data-native className="rs-btn sm primary"><i className="fas fa-paper-plane" aria-hidden="true" /> Message parents</a>}>
              <StudentList rows={a.intervention} pm={pm} link={cardLink} showClass empty="No students below the pass mark. 🎉" />
            </Card>
            <Card icon="fa-medal" title={`Honour roll (${a.honour_roll.length})`} sub={`Average ${s.distinction_mark}+`}>
              <StudentList rows={a.honour_roll} pm={pm} showClass good empty="No distinctions yet." />
            </Card>
          </div>
        )}
        {tab === 'trend' && hasTrend && <Trend trends={a.trends} pm={pm} showPass />}
      </>)}
    </div>
  );
}

// ── Scorecards (subject + teacher) ─────────────────────────────────────────
function ScoreHead({ d, icon, title, sub, children }) {
  const exp = (fmt) => { const b = d.urls.report_base; return `${b}${b.includes('?') ? '&' : '?'}format=${fmt}`; };
  return (
    <Head icon={icon} title={title} sub={sub}>
      {children}
      <Menu label="More" items={[
        d.back_url && { icon: 'fa-arrow-left', label: 'Back to institution analytics', href: d.back_url },
        d.urls.report_base && { heading: 'Download' },
        d.urls.report_base && { icon: 'fa-file-pdf', label: 'PDF', href: exp('pdf'), native: true, download: true },
        d.urls.report_base && { icon: 'fa-file-excel', label: 'Excel', href: exp('excel'), native: true, download: true },
        d.urls.report_base && { icon: 'fa-file-image', label: 'Image', href: exp('image'), native: true, download: true },
      ]} />
    </Head>
  );
}

function TermPick({ d, onChange }) {
  return (
    <section className="rs-pick"><div className="rs-pick-row">
      <label className="rs-sel"><span>Term</span>
        <select value={d.term_id} onChange={(e) => onChange(e.target.value)}>
          {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select></label>
      {d.back_url && <a href={d.back_url} className="rs-btn ghost an-back"><i className="fas fa-building-columns" aria-hidden="true" /><span className="rs-hide-sm">Institution analytics</span></a>}
    </div></section>
  );
}

function ClassRows({ rows, pm, title, sub }) {
  return (
    <div className="an-league">
      {rows.map((r, i) => (
        <div key={i} className="an-league-row subj static">
          <span className="n"><b>{title(r)}</b><small>{sub(r)}</small></span>
          <Meter value={r.average || 0} max={100} tone={toneOf(r.average, pm)} />
          <b className={'v ' + toneOf(r.average, pm)}>{fmtNum(r1(r.average))}</b>
          <span className={'an-pill ' + (r.pass_rate >= 50 ? 'good' : 'bad')}>{fmtNum(r1(r.pass_rate))}%</span>
        </div>
      ))}
    </div>
  );
}

export function SubjectScorecard({ d }) {
  const nav = useNav();
  const sc = d.scorecard;
  const s = (sc && sc.summary) || {};
  const pm = s.pass_mark || 50;
  const [tab, setTab] = useState('classes');
  const goTerm = (tid) => navParams(nav.go, d.self_url, { term_id: tid, subject_id: d.subject_id });
  const ready = sc && s.entries;
  const ins = [];
  if (ready) {
    const rows = sc.rows || [];
    if (rows.length > 1) {
      const lo = rows[0]; const hi = rows[rows.length - 1]; const gap = (hi.average || 0) - (lo.average || 0);
      ins.push({ tone: gap >= 10 ? 'watch' : 'positive', title: gap >= 10 ? `A ${fmtNum(r1(gap))}-point gap between arms` : 'Arms are performing evenly',
        text: `${hi.class} averages ${fmtNum(r1(hi.average))}; ${lo.class} averages ${fmtNum(r1(lo.average))}${gap >= 10 ? ' — compare how they are taught.' : '.'}` });
    }
    const t = (sc.by_teacher || []).filter((x) => x.name && x.name !== 'Unassigned');
    if (t.length > 1) { const best = t.slice().sort((a, b) => b.average - a.average)[0]; ins.push({ tone: 'insight', title: `${best.name} gets the best results`, text: `Average ${fmtNum(r1(best.average))} with ${fmtNum(r1(best.pass_rate))}% passing — worth sharing their approach.` }); }
    ins.push(s.pass_rate < 50 ? { tone: 'negative', title: `Only ${fmtNum(r1(s.pass_rate))}% are passing`, text: 'Consider remedial lessons and a review of the scheme of work for this subject.' }
      : { tone: 'positive', title: `${fmtNum(r1(s.pass_rate))}% are passing`, text: `${fmtNum(r1(s.distinction_rate))}% earned a distinction.` });
    if (s.completion != null && s.completion < 90) ins.push({ tone: 'watch', title: `${fmtNum(r1(100 - s.completion))}% of scores missing`, text: 'Chase the outstanding entries before drawing conclusions.' });
  }
  const hasTrend = ready && sc.trend && sc.trend.term_names.length > 1 && sc.trend.averages.some((v) => v != null);
  return (
    <div className="rs">
      <ScoreHead d={d} icon="fa-book" title={sc ? sc.subject : 'Subject scorecard'} sub="Subject scorecard" />
      <TermPick d={d} onChange={goTerm} />
      {!d.subject_id ? <Blank icon="fa-book" title="No subject chosen"><p>Open a subject from institution analytics.</p></Blank>
        : !ready ? <Blank icon="fa-chart-column" title="No scores yet"><p>No scores for {sc ? sc.subject : 'this subject'} this term.</p></Blank> : (<>
        <Tiles items={[
          { label: 'Average', value: fmtNum(r1(s.average)), tone: toneOf(s.average, pm), sub: `pass mark ${pm}` },
          { label: 'Pass rate', value: fmtNum(r1(s.pass_rate)), unit: '%', tone: s.pass_rate >= 50 ? 'good' : 'bad' },
          { label: 'Distinctions', value: fmtNum(r1(s.distinction_rate)), unit: '%', tone: 'good' },
          { label: 'Taught in', value: `${s.classes} arm${s.classes === 1 ? '' : 's'}`, sub: `by ${s.teachers} teacher${s.teachers === 1 ? '' : 's'}` },
          { label: 'Scores entered', value: fmtNum(r1(s.completion)), unit: '%', tone: s.completion >= 85 ? '' : 'mid' },
        ]} />
        <Insights items={ins} />
        <Seg label="Section" value={tab} onChange={setTab} options={[
          { value: 'classes', label: 'Class arms', icon: 'fa-users', count: sc.rows.length },
          { value: 'teachers', label: 'Teachers', icon: 'fa-chalkboard-user' },
          { value: 'grades', label: 'Grades', icon: 'fa-award' },
          hasTrend && { value: 'trend', label: 'Trend', icon: 'fa-chart-line' }].filter(Boolean)} />
        {tab === 'classes' && (
          <Card icon="fa-users" title="Class arms, weakest first">
            <ClassRows rows={sc.rows} pm={pm} title={(r) => r.class} sub={(r) => `${r.teacher || 'No teacher'} · ${r.assessed}/${r.students} assessed · ${fmtNum(r1(r.lowest))}–${fmtNum(r1(r.highest))}`} />
          </Card>
        )}
        {tab === 'teachers' && (
          <Card icon="fa-chalkboard-user" title="Results by teacher">
            <HBars pm={pm} rows={sc.by_teacher} label={(x) => x.name} sub={(x) => `${x.assessed} students · ${fmtNum(r1(x.pass_rate))}% pass`} value={(x) => x.average} />
          </Card>
        )}
        {tab === 'grades' && (
          <div className="an-grid two">
            <Card icon="fa-award" title="Grade distribution"><HBars max="auto" rows={(sc.grade_distribution || []).map((g) => ({ label: `Grade ${g.grade}`, value: g.count }))} /></Card>
            {sc.score_bands && sc.score_bands.length > 0 && <Card icon="fa-chart-simple" title="Score spread"><Cols pm={pm} bars={sc.score_bands.map((b) => ({ label: b.band, value: b.count }))} /></Card>}
          </div>
        )}
        {tab === 'trend' && hasTrend && <Trend trends={sc.trend} pm={pm} />}
      </>)}
    </div>
  );
}

export function Teacher({ d }) {
  const nav = useNav();
  const sc = d.scorecard;
  const s = (sc && sc.summary) || {};
  const pm = s.pass_mark || 50;
  const [tab, setTab] = useState('classes');
  const goTerm = (tid) => navParams(nav.go, d.self_url, { term_id: tid, name: d.teacher_name });
  const ready = sc && s.entries;
  const msgUrl = ready && d.is_admin && d.staff_id && d.urls.compose
    ? `${d.urls.compose}?to=staff&staff_ids=${d.staff_id}&body=${encodeURIComponent(`Dear ${d.teacher_name}, I would like to discuss your class results for this term and how we can support stronger outcomes. Please see me at your earliest convenience. Thank you.`)}` : null;
  const ins = [];
  if (ready) {
    const rows = sc.rows || [];
    if (rows.length) { const lo = rows[0]; ins.push({ tone: lo.average < pm ? 'negative' : 'watch', title: `Weakest: ${lo.subject}, ${lo.class}`, text: `Average ${fmtNum(r1(lo.average))}, ${fmtNum(r1(lo.pass_rate))}% passing.` }); }
    if (rows.length > 1) { const hi = rows[rows.length - 1]; ins.push({ tone: 'positive', title: `Strongest: ${hi.subject}, ${hi.class}`, text: `Average ${fmtNum(r1(hi.average))}, ${fmtNum(r1(hi.pass_rate))}% passing.` }); }
    const missing = rows.filter((r) => r.completion < 90);
    if (missing.length) ins.push({ tone: 'watch', title: `${missing.length} class subject${missing.length === 1 ? '' : 's'} with missing scores`, text: missing.slice(0, 3).map((r) => `${r.subject} (${r.class})`).join(', ') + (missing.length > 3 ? '…' : '') });
  }
  const FT = { strong: 'good', good: '', watch: 'mid', review: 'bad', compliance: 'bad', insufficient: 'muted' };
  const hasTrend = ready && sc.trend && sc.trend.term_names.length > 1 && sc.trend.averages.some((v) => v != null);
  return (
    <div className="rs">
      <ScoreHead d={d} icon="fa-chalkboard-user" title={d.teacher_name || 'Teacher scorecard'} sub={ready ? s.verdict : 'Teacher scorecard'}>
        {msgUrl && <a href={msgUrl} data-native className="rs-btn primary"><i className="fas fa-paper-plane" aria-hidden="true" /><span className="rs-hide-sm">Message teacher</span></a>}
      </ScoreHead>
      <TermPick d={d} onChange={goTerm} />
      {!d.teacher_name ? <Blank icon="fa-chalkboard-user" title="No teacher chosen"><p>Open a teacher from institution analytics.</p></Blank>
        : !ready ? <Blank icon="fa-chart-column" title="No scores yet"><p>No scored subjects for {d.teacher_name} this term.</p></Blank> : (<>
        {s.verdict && <div className={'an-verdict ' + (FT[s.flag] || '')}><i className="fas fa-clipboard-check" aria-hidden="true" /> <b>{s.verdict}</b></div>}
        <Tiles items={[
          { label: 'Average', value: fmtNum(r1(s.average)), tone: toneOf(s.average, pm), sub: `pass mark ${pm}` },
          { label: 'Pass rate', value: fmtNum(r1(s.pass_rate)), unit: '%', tone: s.pass_rate >= 50 ? 'good' : 'bad' },
          { label: 'Teaches', value: `${s.subjects} subj.`, sub: `${s.classes} class${s.classes === 1 ? '' : 'es'} · ${s.students} students` },
          { label: 'Scores entered', value: fmtNum(r1(s.completion)), unit: '%', tone: s.completion >= 85 ? '' : 'mid' },
        ]} />
        <Insights items={ins} />
        <Seg label="Section" value={tab} onChange={setTab} options={[
          { value: 'classes', label: 'Classes', icon: 'fa-users', count: sc.rows.length },
          { value: 'split', label: 'By subject & class', icon: 'fa-layer-group' },
          hasTrend && { value: 'trend', label: 'Trend', icon: 'fa-chart-line' }].filter(Boolean)} />
        {tab === 'classes' && (
          <Card icon="fa-users" title="Class subjects, weakest first">
            <ClassRows rows={sc.rows} pm={pm} title={(r) => `${r.subject} · ${r.class}`} sub={(r) => `${r.assessed}/${r.students} assessed · ${fmtNum(r1(r.completion))}% entered · ${fmtNum(r1(r.lowest))}–${fmtNum(r1(r.highest))}`} />
          </Card>
        )}
        {tab === 'split' && (
          <div className="an-grid two">
            <Card icon="fa-book" title="By subject"><HBars pm={pm} rows={sc.by_subject} label={(x) => x.name} sub={(x) => `${x.assessed} · ${fmtNum(r1(x.pass_rate))}% pass`} value={(x) => x.average} /></Card>
            <Card icon="fa-users" title="By class"><HBars pm={pm} rows={sc.by_class} label={(x) => x.name} sub={(x) => `${x.assessed} · ${fmtNum(r1(x.pass_rate))}% pass`} value={(x) => x.average} /></Card>
          </div>
        )}
        {tab === 'trend' && hasTrend && <Trend trends={sc.trend} pm={pm} />}
      </>)}
    </div>
  );
}
