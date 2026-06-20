import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, TableWrap } from '../components/ui';

function useSave(notify) {
  return async (url, fields, after, okMsg) => {
    const r = await submitJson(url, fields);
    if (r.ok) { notify('success', okMsg || r.message); after && after(r); }
    else notify('error', r.error || 'Something went wrong.');
    return r;
  };
}

const A = ({ to, className, children, title, target }) => {
  const nav = useNav();
  if (target === '_blank') return <a href={to} target="_blank" rel="noopener" className={className} title={title}>{children}</a>;
  return <a href={to} className={className} title={title}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

// ---- Index: term/class picker + read-only grid ------------------------------
function Index({ d }) {
  const nav = useNav();
  const go = (term, assignment) => {
    const p = new URLSearchParams();
    if (term) p.set('term_id', term);
    if (assignment) p.set('assignment_id', assignment);
    const qs = p.toString();
    nav.go(qs ? `${d.urls.self}?${qs}` : d.urls.self);
  };
  const sel = d.selected_assignment;
  return (
    <>
      <div className="page-header">
        <h1>Class Timetable</h1>
        <div className="page-header-actions">
          <A to={d.urls.backups} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Backups &amp; Restore</A>
          <A to={d.urls.designer} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-drafting-compass" /> Timetable Designer</A>
        </div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Term</label>
            <select className="form-control" value={d.term_id || ''} onChange={(e) => go(e.target.value, '')}>
              <option value="">Select Term</option>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            </select></div>
          <div className="form-group"><label className="form-label">Class</label>
            <select className="form-control" value={d.assignment_id || ''} onChange={(e) => go(d.term_id, e.target.value)}>
              <option value="">Select Class</option>
              {d.assignments.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
            </select></div>
        </div>
      </div></div>

      {sel ? (
        <>
          <div className="card mb-3">
            <div className="card-header">
              <h3>{sel.display_name}</h3>
              <div className="page-header-actions">
                <A to={d.urls.edit} className="btn btn-primary btn-sm"><i aria-hidden="true" className="fas fa-edit" /> Edit</A>
                <A to={d.urls.pdf} target="_blank" className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-file-pdf" /> PDF</A>
                <A to={d.urls.pdf_teachers} target="_blank" className="btn btn-secondary btn-sm"><i aria-hidden="true" className="fas fa-file-pdf" /> PDF + teachers</A>
              </div>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <TableWrap label="Class timetable">
              <table className="data-table" style={{ minWidth: '100%' }}>
                <thead><tr><th style={{ width: 100 }}>Time</th>
                  {d.days.map(([n, name]) => <th key={n} style={{ textAlign: 'center' }}>{name}</th>)}</tr></thead>
                <tbody>
                  {d.slots.map((s) => (
                    <tr key={s.id} className={s.is_break ? 'table-info' : ''}>
                      <td style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}><strong>{s.name}</strong><br />{s.start} - {s.end}</td>
                      {d.days.map(([n]) => {
                        if (s.is_break) return <td key={n} style={{ textAlign: 'center' }}><em className="text-muted">Break</em></td>;
                        const e = d.grid[`${n}_${s.id}`];
                        return (
                          <td key={n} style={{ textAlign: 'center' }}>
                            {e ? <><strong>{e.subject}</strong>{e.teacher && <><br /><small className="text-muted">{e.teacher}</small></>}</> : <span className="text-muted">-</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              </TableWrap>
            </div>
          </div>
          {d.legend.length > 0 && (
            <div className="card">
              <div className="card-header"><h3>Legend</h3></div>
              <div className="card-body"><div className="filter-form" style={{ flexWrap: 'wrap' }}>
                {d.legend.map((l, i) => <div key={i} style={{ margin: '0.25rem 0.5rem' }}><strong>{l.short}</strong> = {l.name}</div>)}
              </div></div>
            </div>
          )}
        </>
      ) : (
        <div className="card"><div className="card-body">
          {d.has_term
            ? <Empty icon="fa-hand-pointer" title="Select a Class">Choose a class to view or edit timetable</Empty>
            : <Empty icon="fa-calendar-alt" title="Select Term & Class">Choose a term and class to manage timetable</Empty>}
        </div></div>
      )}
    </>
  );
}

// ---- Edit grid --------------------------------------------------------------
function Edit({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [cells, setCells] = useState(() => {
    const m = {};
    Object.entries(d.entries).forEach(([k, v]) => { m[k] = { subject_id: String(v.subject_id || ''), teacher: v.teacher || '' }; });
    return m;
  });
  const get = (k) => cells[k] || { subject_id: '', teacher: '' };
  const set = (k, field, val) => setCells((c) => ({ ...c, [k]: { ...get(k), [field]: val } }));
  const submit = (e) => {
    e.preventDefault();
    const fields = {};
    d.days.forEach(([day]) => d.slots.forEach((s) => {
      if (s.is_break) return;
      const k = `${day}_${s.id}`;
      const c = get(k);
      fields[`entry_${day}_${s.id}`] = c.subject_id || '';
      fields[`teacher_${day}_${s.id}`] = c.teacher || '';
    }));
    save(d.save_url, fields, (r) => nav.go(r.redirect || d.cancel_url));
  };
  return (
    <>
      <div className="page-header"><h1>Edit: {d.assignment.display_name}</h1></div>
      <div className="card"><div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
        <form onSubmit={submit}>
          <table className="data-table" style={{ minWidth: '100%' }}>
            <thead><tr><th style={{ width: 100 }}>Time</th>
              {d.days.map(([n, name]) => <th key={n} style={{ textAlign: 'center', minWidth: 150 }}>{name}</th>)}</tr></thead>
            <tbody>
              {d.slots.map((s) => (
                <tr key={s.id} className={s.is_break ? 'table-info' : ''}>
                  <td style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}><strong>{s.name}</strong><br />{s.start} - {s.end}</td>
                  {d.days.map(([day]) => {
                    if (s.is_break) return <td key={day} style={{ textAlign: 'center', padding: '0.5rem' }}><em className="text-muted">Break</em></td>;
                    const k = `${day}_${s.id}`;
                    const c = get(k);
                    return (
                      <td key={day} style={{ textAlign: 'center', padding: '0.5rem' }}>
                        <select className="form-control" style={{ fontSize: '0.8rem', padding: '0.25rem' }}
                          value={c.subject_id} onChange={(e) => set(k, 'subject_id', e.target.value)}>
                          <option value="">-</option>
                          {d.subjects.map((su) => <option key={su.subject_id} value={su.subject_id}>{su.label}</option>)}
                        </select>
                        <input type="text" className="form-control mt-1" placeholder="Teacher"
                          style={{ fontSize: '0.75rem', padding: '0.25rem' }}
                          value={c.teacher} onChange={(e) => set(k, 'teacher', e.target.value)} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="card-body"><div className="page-header-actions">
            <button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-save" /> Save Timetable</button>
            <A to={d.cancel_url} className="btn btn-secondary">Cancel</A>
          </div></div>
        </form>
      </div></div>
    </>
  );
}

// ---- Backups ----------------------------------------------------------------
function Backups({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [label, setLabel] = useState('');
  const create = (e) => {
    e.preventDefault();
    save(d.create_url, { term_id: d.term_id || '', label }, () => { setLabel(''); nav.refresh(); });
  };
  const restore = async (b) => {
    if (await confirm('Restore this backup? Your current timetable for this term will be backed up first, then replaced with this one.')) save(b.restore_url, {}, () => nav.refresh());
  };
  const del = async (b) => {
    if (await confirm('Delete this backup permanently?')) save(b.delete_url, {}, () => nav.refresh());
  };
  const onTerm = (e) => nav.go(`${d.self_url}?term_id=${e.target.value}`);
  return (
    <>
      <div className="page-header">
        <div>
          <h1><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Timetable Backups &amp; Restore</h1>
          <p className="text-muted text-sm">A snapshot is saved automatically each time a generated timetable is applied. Restore one to bring back a previous timetable.</p>
        </div>
        {d.terms.length > 0 && (
          <div className="filter-form">
            <select className="form-control" value={d.term_id || ''} onChange={onTerm}>
              {d.terms.map((t) => <option key={t.id} value={t.id}>{t.full_name}</option>)}
            </select>
          </div>
        )}
      </div>
      <div className="card mb-3"><div className="card-body">
        <form onSubmit={create} className="filter-form" style={{ gap: '.5rem', alignItems: 'end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: 220, margin: 0 }}>
            <label className="form-label">Back up the current timetable now</label>
            <input className="form-control" placeholder="Label (e.g. 'Working timetable — Term 1')" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <button type="submit" className="btn btn-secondary"><i aria-hidden="true" className="fas fa-floppy-disk" /> Back up now</button>
        </form>
      </div></div>
      <div className="card"><div className="card-body">
        {d.backups.length ? (
          <div className="table-responsive"><table className="table">
            <thead><tr><th>When</th><th>Label</th><th>Entries</th><th className="text-right">Actions</th></tr></thead>
            <tbody>
              {d.backups.map((b) => (
                <tr key={b.id}>
                  <td>{b.when}</td><td>{b.label}</td><td>{b.entry_count}</td>
                  <td className="text-right">
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => restore(b)}><i aria-hidden="true" className="fas fa-rotate-left" /> Restore</button>{' '}
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => del(b)}><i aria-hidden="true" className="fas fa-trash" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : (
          <p className="text-muted text-center" style={{ padding: '1.5rem' }}><i aria-hidden="true" className="fas fa-info-circle" /> No backups yet for this term. One is created automatically when you apply a generated timetable, or use “Back up now” above.</p>
        )}
      </div></div>
    </>
  );
}

const SCREENS = { index: Index, edit: Edit, backups: Backups };

export default function TimetableApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
