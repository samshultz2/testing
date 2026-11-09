import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Spinner, EmptyState, ErrorState, OfflineRequired, Pill } from '../../components/ui';
import { Tiles, Seg, Person, Sheet, initialsOf, pctTone, fmtPct } from '../kit';

const dirIcon = { up: '↑', down: '↓', flat: '→' };
const dirTone = { up: 'green', down: 'red', flat: 'gray' };
const KINDS = ['Note', 'Parent meeting', 'Counselling', 'Call', 'Follow-up'];

function NoteForm({ ivId, onDone, notify }) {
  const [f, setF] = useState({ kind: 'Note', body: '', next_action: '', next_date: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const r = await apiPost(`/attendance/api/interventions/${ivId}/note`, f);
    setBusy(false);
    if (r && r.ok) onDone(); else notify(r && r.error);
  };
  return (
    <form onSubmit={submit} className="ak-form">
      <span className="form-label">What kind of follow-up?</span>
      <div className="ak-kinds" role="radiogroup" aria-label="Follow-up type">
        {KINDS.map((k) => <button key={k} type="button" role="radio" aria-checked={f.kind === k} className={f.kind === k ? 'on' : ''} onClick={() => set('kind', k)}>{k}</button>)}
      </div>
      <label className="form-label">What happened?</label>
      <textarea className="form-control" rows="3" placeholder="e.g. Spoke to mum — pupil has been unwell" value={f.body} onChange={(e) => set('body', e.target.value)} autoFocus />
      <div className="ak-two">
        <div><label className="form-label">Next step <span className="text-muted">(optional)</span></label>
          <input className="form-control" placeholder="e.g. Check in on Friday" value={f.next_action} onChange={(e) => set('next_action', e.target.value)} /></div>
        <div><label className="form-label">By</label>
          <input className="form-control" type="date" value={f.next_date} onChange={(e) => set('next_date', e.target.value)} /></div>
      </div>
      <button className="btn btn-primary ak-go" disabled={busy}><i className="fas fa-plus" aria-hidden="true" /> Log follow-up</button>
    </form>
  );
}

function Case({ iv, act, onFollow }) {
  const up = iv.direction === 'up', down = iv.direction === 'down';
  return (
    <article className={'iv2 ' + (iv.status === 'Escalated' ? 'esc' : iv.status === 'Resolved' ? 'res' : '')}>
      <header className="iv2-h">
        <span className="att-av" aria-hidden="true">{initialsOf(iv.name)}</span>
        <div className="iv2-t">
          <a href={`/attendance/app?student_id=${iv.student_id}#/student`}><strong>{iv.name}</strong></a>
          <small>{iv.class} · opened {iv.opened}{iv.opened_by ? ' by ' + iv.opened_by : ''}</small>
        </div>
        <Pill tone={iv.status === 'Escalated' ? 'red' : iv.status === 'Resolved' ? 'green' : 'amber'}>{iv.status}</Pill>
      </header>
      <div className="iv2-m">
        <div><span>Was</span><b>{iv.baseline != null ? fmtPct(iv.baseline) : '—'}</b></div>
        <i className="fas fa-arrow-right" aria-hidden="true" />
        <div><span>Now</span><b className={'ak-pct ' + pctTone(iv.current)}>{iv.current != null ? fmtPct(iv.current) : '—'}</b></div>
        {iv.delta != null && <span className={'iv2-d ' + (up ? 'good' : down ? 'bad' : '')}>
          <i className={'fas ' + (up ? 'fa-arrow-trend-up' : down ? 'fa-arrow-trend-down' : 'fa-minus')} aria-hidden="true" /> {iv.delta > 0 ? '+' : ''}{iv.delta}</span>}
      </div>
      {iv.reason && <p className="iv2-r">{iv.reason}</p>}
      {iv.notes.length > 0 && (
        <ol className="iv2-tl">
          {iv.notes.map((n, i) => (
            <li key={i}><b>{n.kind}</b> <span className="ak-dim">· {n.date}{n.author ? ' · ' + n.author : ''}</span>
              {n.body && <div>{n.body}</div>}
              {n.next_action && <div className="ak-dim"><i className="fas fa-arrow-turn-down fa-rotate-270" aria-hidden="true" /> Next: {n.next_action}{n.next_date ? ` (by ${n.next_date})` : ''}</div>}</li>))}
        </ol>)}
      {iv.status !== 'Resolved' && (
        <div className="iv2-a no-print">
          <button type="button" className="ak-btn primary" onClick={() => onFollow(iv)}><i className="fas fa-pen" aria-hidden="true" /> Follow-up</button>
          {iv.status !== 'Escalated' && <button type="button" className="ak-btn" onClick={() => act(iv.id, 'Escalated')}><i className="fas fa-arrow-up" aria-hidden="true" /> Escalate</button>}
          <button type="button" className="ak-btn ok" onClick={() => act(iv.id, 'Resolved')}><i className="fas fa-check" aria-hidden="true" /> Resolve</button>
        </div>)}
    </article>
  );
}

export default function Interventions() {
  const { term, terms = [], online } = useCtx();
  const [termId, setTermId] = useState(term ? String(term.id) : '');
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState(null);
  const [view, setView] = useState('');
  const [follow, setFollow] = useState(null);
  const tid = termId || (term ? String(term.id) : '');
  const [state] = useAsync(
    () => (online && tid ? apiGet(`/attendance/api/interventions?term_id=${tid}`) : Promise.resolve(null)),
    [tid, online, tick]);
  const d = state.data;
  const refresh = () => setTick((t) => t + 1);
  const notify = (e) => setMsg(e || 'Action failed.');

  const act = async (id, status) => {
    if (id && status) {
      const r = await apiPost(`/attendance/api/interventions/${id}/status`, { status });
      if (!(r && r.ok)) { notify(r && r.error); return; }
    }
    refresh();
  };
  const openFor = async (sid) => {
    const r = await apiPost('/attendance/api/interventions/open', { student_id: sid, term_id: tid });
    if (r && r.ok) refresh(); else notify(r && r.error);
  };

  const v = view || (d && d.active.length ? 'active' : (d && d.recommendations.length ? 'recommended' : 'active'));

  return (
    <div className="md">
      <div className="ak-toolbar">
        {terms.length > 0 && (
          <label className="ax-term"><i className="fas fa-calendar" aria-hidden="true" />
            <select value={tid} onChange={(e) => setTermId(e.target.value)} aria-label="Term">
              {terms.map((t) => <option key={t.id} value={String(t.id)}>{t.name}{t.active ? ' (active)' : ''}</option>)}
            </select></label>)}
      </div>
      {msg && <div className="att-warn" role="alert">{msg}</div>}

      {!online ? <div className="md-card"><OfflineRequired what="Interventions" /></div>
        : state.loading ? <div className="md-card"><Spinner label="Loading interventions…" /></div>
        : state.error ? <div className="md-card"><ErrorState detail={state.error.message} /></div>
        : !d ? <div className="md-card"><EmptyState icon="fa-hand-holding-heart" title="No term selected" /></div>
        : (
          <>
            <Tiles items={[
              { label: 'Active cases', value: d.counts.active, tone: d.counts.active ? 'warn' : '', onClick: () => setView('active') },
              { label: 'Improving', value: d.counts.improved, tone: 'good' },
              { label: 'Declining', value: d.counts.declining, tone: d.counts.declining ? 'bad' : '' },
              { label: 'Resolved', value: d.counts.resolved, onClick: () => setView('resolved') },
            ]} />

            <Seg label="Show" value={v} onChange={setView} options={[
              { value: 'recommended', label: 'Needs a case', icon: 'fa-lightbulb', count: d.recommendations.length },
              { value: 'active', label: 'Active', icon: 'fa-hand-holding-heart', count: d.active.length },
              { value: 'resolved', label: 'Resolved', icon: 'fa-clipboard-check', count: d.resolved.length }]} />

            {v === 'recommended' && (
              <div className="md-card">
                <p className="ak-sub-h">Students below {d.threshold}% without an open case</p>
                {d.recommendations.length === 0
                  ? <EmptyState icon="fa-circle-check" title="Nobody needs a new case" hint="Every student under the threshold already has one." />
                  : (
                    <ul className="ak-people">
                      {d.recommendations.map((r) => (
                        <Person key={r.student_id} name={r.name} sub={`${r.class} · ${r.student_id_str}`} tone="out"
                                href={`/attendance/app?student_id=${r.student_id}#/student`}
                                right={<><span className={'ak-pct ' + pctTone(r.percentage)}>{fmtPct(r.percentage)}</span>
                                  <button type="button" className="ak-btn primary no-print" onClick={() => openFor(r.student_id)}><i className="fas fa-plus" aria-hidden="true" /><span> Open case</span></button></>} />))}
                    </ul>)}
              </div>)}

            {v === 'active' && (d.active.length === 0
              ? <div className="md-card"><EmptyState icon="fa-circle-check" title="No active interventions" hint="Open one from “Needs a case” or a student’s profile." /></div>
              : <div className="iv2-list">{d.active.map((iv) => <Case key={iv.id} iv={{ ...iv, threshold: d.threshold }} act={act} onFollow={setFollow} />)}</div>)}

            {v === 'resolved' && (d.resolved.length === 0
              ? <div className="md-card"><EmptyState icon="fa-clipboard-check" title="Nothing resolved yet" /></div>
              : <div className="iv2-list">{d.resolved.map((iv) => <Case key={iv.id} iv={{ ...iv, threshold: d.threshold }} act={act} onFollow={setFollow} />)}</div>)}
          </>
        )}

      {follow && (
        <Sheet title={`Follow-up · ${follow.name}`} onClose={() => setFollow(null)}>
          <NoteForm ivId={follow.id} onDone={() => { setFollow(null); act(null); }} notify={notify} />
        </Sheet>
      )}
    </div>
  );
}
