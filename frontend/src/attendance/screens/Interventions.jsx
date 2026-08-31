import React, { useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { useAsync } from '../../lib/hooks';
import { useCtx } from '../App';
import { Toolbar, Spinner, EmptyState, ErrorState, OfflineRequired, StatCards, SectionTitle, Pill } from '../../components/ui';

const dirIcon = { up: '↑', down: '↓', flat: '→' };
const dirTone = { up: 'green', down: 'red', flat: 'gray' };
const KINDS = ['Note', 'Parent meeting', 'Counselling', 'Call', 'Follow-up'];

function NoteForm({ ivId, onDone, notify }) {
  const [f, setF] = useState({ kind: 'Note', body: '', next_action: '', next_date: '' });
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    const r = await apiPost(`/attendance/api/interventions/${ivId}/note`, f);
    if (r && r.ok) onDone(); else notify(r && r.error);
  };
  return (
    <form onSubmit={submit} className="iv-noteform">
      <select className="form-control" value={f.kind} onChange={(e) => set('kind', e.target.value)} style={{ maxWidth: 150 }}>
        {KINDS.map((k) => <option key={k}>{k}</option>)}</select>
      <input className="form-control" placeholder="What happened?" value={f.body} onChange={(e) => set('body', e.target.value)} />
      <input className="form-control" placeholder="Next action (optional)" value={f.next_action} onChange={(e) => set('next_action', e.target.value)} style={{ maxWidth: 180 }} />
      <input className="form-control" type="date" value={f.next_date} onChange={(e) => set('next_date', e.target.value)} style={{ maxWidth: 150 }} />
      <button className="btn btn-primary btn-sm"><i className="fas fa-plus" aria-hidden="true" /> Log</button>
    </form>
  );
}

function Case({ iv, act, notify }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="iv-case">
      <div className="iv-case-head">
        <div>
          <a href={`/attendance/app?student_id=${iv.student_id}#/student`}><strong>{iv.name}</strong></a>
          <span className="att-sub"> · {iv.class} · opened {iv.opened}{iv.opened_by ? ' by ' + iv.opened_by : ''}</span>
        </div>
        <div className="iv-case-metrics">
          {iv.baseline != null && <span className="att-sub">was {iv.baseline}%</span>}
          {iv.current != null && <Pill tone={iv.current >= iv.threshold ? 'green' : 'red'}>{iv.current}%</Pill>}
          {iv.delta != null && <Pill tone={dirTone[iv.direction]}>{dirIcon[iv.direction]} {iv.delta > 0 ? '+' : ''}{iv.delta}</Pill>}
          <Pill tone={iv.status === 'Escalated' ? 'red' : iv.status === 'Resolved' ? 'green' : 'amber'}>{iv.status}</Pill>
        </div>
      </div>
      {iv.reason && <div className="att-sub" style={{ marginTop: 2 }}>{iv.reason}</div>}
      {iv.notes.length > 0 && (
        <ul className="iv-notes">
          {iv.notes.map((n, i) => (
            <li key={i}><b>{n.kind}</b> · {n.date}{n.author ? ' · ' + n.author : ''}{n.body ? ` — ${n.body}` : ''}
              {n.next_action ? <span className="att-sub"> → next: {n.next_action}{n.next_date ? ` (${n.next_date})` : ''}</span> : null}</li>))}
        </ul>)}
      <div className="iv-case-actions no-print">
        <button className="btn btn-secondary btn-sm" onClick={() => setOpen(!open)}><i className="fas fa-pen" aria-hidden="true" /> Follow-up</button>
        {iv.status !== 'Escalated' && <button className="btn btn-secondary btn-sm" onClick={() => act(iv.id, 'Escalated')}>Escalate</button>}
        <button className="btn btn-success btn-sm" onClick={() => act(iv.id, 'Resolved')}><i className="fas fa-check" aria-hidden="true" /> Resolve</button>
      </div>
      {open && <NoteForm ivId={iv.id} onDone={() => { setOpen(false); act(null); }} notify={notify} />}
    </div>
  );
}

export default function Interventions() {
  const { term, terms = [], online } = useCtx();
  const [termId, setTermId] = useState(term ? String(term.id) : '');
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState(null);
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

  return (
    <div>
      <Toolbar>
        {terms.length > 0 && (
          <label className="att-inline-field">Term{' '}
            <select className="form-control" style={{ maxWidth: 240, display: 'inline-block' }}
                    value={tid} onChange={(e) => setTermId(e.target.value)}>
              {terms.map((t) => <option key={t.id} value={String(t.id)}>{t.name}{t.active ? ' (active)' : ''}</option>)}
            </select></label>)}
      </Toolbar>
      {msg && <div className="att-warn" role="alert">{msg}</div>}

      {!online ? <OfflineRequired what="Interventions" />
        : state.loading ? <Spinner label="Loading interventions…" />
        : state.error ? <ErrorState detail={state.error.message} />
        : !d ? <EmptyState icon="fa-hand-holding-heart" title="No term selected" />
        : (
          <>
            <StatCards items={[
              { value: d.counts.active, label: 'Active cases', primary: true },
              { value: d.counts.improved, label: 'Improving' },
              { value: d.counts.declining, label: 'Declining' },
              { value: d.counts.resolved, label: 'Resolved' },
            ]} />

            {d.recommendations.length > 0 && (
              <>
                <SectionTitle icon="fa-lightbulb">Recommended for intervention (below {d.threshold}%)</SectionTitle>
                <div className="att-grid-wrap">
                  <table className="att-grid" aria-label="Intervention recommendations">
                    <thead><tr><th className="att-grid-name" scope="col">Student</th><th scope="col">Class</th><th scope="col">%</th><th scope="col" /></tr></thead>
                    <tbody>{d.recommendations.map((r) => (
                      <tr key={r.student_id}><td className="att-grid-name"><a href={`/attendance/app?student_id=${r.student_id}#/student`}>{r.name}</a>
                        <div className="att-sub">{r.student_id_str}</div></td>
                        <td>{r.class}</td><td><Pill tone="red">{r.percentage}%</Pill></td>
                        <td className="no-print"><button className="btn btn-primary btn-sm" onClick={() => openFor(r.student_id)}><i className="fas fa-plus" aria-hidden="true" /> Open</button></td></tr>))}
                    </tbody>
                  </table>
                </div>
              </>)}

            <SectionTitle icon="fa-hand-holding-heart">Active interventions</SectionTitle>
            {d.active.length === 0
              ? <EmptyState icon="fa-circle-check" title="No active interventions" hint="Open one from the recommendations above or a student's profile." />
              : d.active.map((iv) => <Case key={iv.id} iv={{ ...iv, threshold: d.threshold }} act={act} notify={notify} />)}

            {d.resolved.length > 0 && (
              <>
                <SectionTitle icon="fa-clipboard-check">Recently resolved</SectionTitle>
                {d.resolved.map((iv) => <Case key={iv.id} iv={{ ...iv, threshold: d.threshold }} act={act} notify={notify} />)}
              </>)}
          </>
        )}
    </div>
  );
}
