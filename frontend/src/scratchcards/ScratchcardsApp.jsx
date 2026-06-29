import React, { useState } from 'react';
import { submitJson, useSave } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, SectionShell, Empty } from '../components/ui';

const A = ({ to, className, children, title }) => {
  const nav = useNav();
  return <a href={to} className={className} title={title}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

// ---- Index ------------------------------------------------------------------
function Index({ d, notify }) {
  const nav = useNav();
  const save = useSave(notify);
  const [gen, setGen] = useState({ count: 20, max_uses: 5, term_id: '', batch_label: '' });
  const setG = (k) => (e) => setGen({ ...gen, [k]: e.target.value });

  const generate = (e) => {
    e.preventDefault();
    // On success we leave the SPA to open the printable sheet.
    save(d.generate_url, gen, (r) => { if (r.redirect) nav.go(r.redirect); });
  };
  const publish = (t) => save(t.publish_url, {}, () => nav.refresh());
  const toggle = (c) => save(c.toggle_url, {}, () => nav.refresh());
  const onBatch = (e) => { const v = e.target.value; nav.go(v ? `${d.self_url}?batch=${encodeURIComponent(v)}` : d.self_url); };

  return (
    <>
      <div className="page-header">
        <h1><i aria-hidden="true" className="fas fa-ticket" /> Result Scratch Cards</h1>
        <div className="page-header-actions">
          <A to={d.logs_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-list-check" /> Check Logs</A>
        </div>
      </div>

      <div className="sum-cards" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: '.75rem', marginBottom: '1rem' }}>
        <div className="card"><div className="card-body"><div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{d.stats.total}</div><div className="text-muted text-sm">Cards</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{d.stats.active}</div><div className="text-muted text-sm">Active</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{d.stats.used}</div><div className="text-muted text-sm">Checks used</div></div></div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-unlock" /> Release results to portal</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm">A term's results are only visible on the public checker when released here.</p>
          <table className="data-table table-stack no-mobile-scroll" style={{ width: '100%' }}>
            <thead><tr><th>Term</th><th>Status</th><th /></tr></thead>
            <tbody>
              {d.terms.map((t) => (
                <tr key={t.id}>
                  <td data-label="Term">{t.name}</td>
                  <td data-label="Status">{t.results_published ? <span className="badge badge-success">Released</span> : <span className="badge badge-secondary">Hidden</span>}</td>
                  <td data-label="">
                    <button type="button" onClick={() => publish(t)} className={`btn btn-sm ${t.results_published ? 'btn-danger' : 'btn-success'}`}>{t.results_published ? 'Hide' : 'Release'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Generate cards</h3></div>
        <div className="card-body">
          <form onSubmit={generate} className="filter-form" style={{ flexWrap: 'wrap', gap: '1rem' }}>
            <div className="form-group"><label className="form-label">How many</label><input type="number" className="form-control" value={gen.count} onChange={setG('count')} min="1" max="500" /></div>
            <div className="form-group"><label className="form-label">Checks per card</label><input type="number" className="form-control" value={gen.max_uses} onChange={setG('max_uses')} min="1" max="100" /></div>
            <div className="form-group"><label className="form-label">Lock to term (optional)</label>
              <select className="form-control" value={gen.term_id} onChange={setG('term_id')}>
                <option value="">Any term</option>
                {d.terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select></div>
            <div className="form-group"><label className="form-label">Batch label (optional)</label><input type="text" className="form-control" value={gen.batch_label} onChange={setG('batch_label')} placeholder="e.g., 2025 T1 Sales" /></div>
            <div className="form-group" style={{ alignSelf: 'flex-end' }}><button type="submit" className="btn btn-primary"><i aria-hidden="true" className="fas fa-bolt" /> Generate &amp; Print</button></div>
          </form>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Cards ({d.cards.length})</h3>
          <div style={{ display: 'flex', gap: '.5rem' }}>
            <select className="form-control" value={d.batch || ''} onChange={onBatch}>
              <option value="">All batches</option>
              {d.batches.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
            {d.print_batch_url && <a href={d.print_batch_url} className="btn btn-sm btn-secondary"><i aria-hidden="true" className="fas fa-print" /> Print batch</a>}
          </div>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {d.cards.length ? (
            <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
              <thead><tr><th>Serial</th><th>PIN</th><th>Uses</th><th>Term</th><th>Batch</th><th>Status</th><th /></tr></thead>
              <tbody>
                {d.cards.map((c) => (
                  <tr key={c.id}>
                    <td data-label="Serial">{c.serial}</td>
                    <td data-label="PIN"><code>{c.pin}</code></td>
                    <td data-label="Uses">{c.used_count}/{c.max_uses} <span className="text-muted">({c.uses_left} left)</span></td>
                    <td data-label="Term">{c.term_name}</td>
                    <td data-label="Batch">{c.batch_label}</td>
                    <td data-label="Status">{c.is_active ? <span className="badge badge-success">Active</span> : <span className="badge badge-danger">Disabled</span>}</td>
                    <td data-label="">
                      <button type="button" onClick={() => toggle(c)} className={`btn btn-sm ${c.is_active ? 'btn-danger' : 'btn-success'}`}>{c.is_active ? 'Disable' : 'Enable'}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          ) : (
            <Empty icon="fa-ticket" title="No cards yet">Generate a batch above.</Empty>
          )}
        </div>
      </div>
    </>
  );
}

// ---- Logs -------------------------------------------------------------------
function Logs({ d }) {
  return (
    <>
      <div className="page-header"><h1><i aria-hidden="true" className="fas fa-list-check" /> Result Check Logs</h1>
        <div className="page-header-actions"><A to={d.index_url} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back</A></div>
      </div>
      <div className="card"><div className="card-body" style={{ padding: 0 }}>
        {d.rows.length ? (
          <div className="table-container"><table className="data-table table-stack no-mobile-scroll">
            <thead><tr><th>When</th><th>Student</th><th>Term</th><th>Card</th><th>Result</th><th>Detail</th><th>IP</th></tr></thead>
            <tbody>
              {d.rows.map((r, i) => (
                <tr key={i}>
                  <td data-label="When">{r.when}</td>
                  <td data-label="Student">{r.student}</td>
                  <td data-label="Term">{r.term}</td>
                  <td data-label="Card">{r.card}</td>
                  <td data-label="Result">{r.success ? <span className="badge badge-success">OK</span> : <span className="badge badge-danger">Fail</span>}</td>
                  <td data-label="Detail">{r.detail}</td>
                  <td data-label="IP">{r.ip}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        ) : (
          <Empty icon="fa-list-check" title="No checks yet" />
        )}
      </div></div>
    </>
  );
}

const SCREENS = { index: Index, logs: Logs };

export default function ScratchcardsApp({ data }) {
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
