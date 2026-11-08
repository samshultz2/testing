import React, { useState, useEffect, useRef } from 'react';
import { chartPalette } from '../lib/hooks';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, PageHeader, Empty, SectionShell, Modal, Button, confirm, promptDialog } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Field } from './forms';
import * as Screens from './screens';

const EmptyState = ({ icon, title, children }) => <Empty icon={icon} title={title}>{children && <p>{children}</p>}</Empty>;

// A compact metric tile; optionally a link and danger-coloured when non-zero.
function Tile({ n, label, danger, href }) {
  const body = (
    <div className="card-body">
      <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: danger ? '#e74a3b' : 'inherit' }}>{n}</div>
      <div className="text-muted text-sm">{label}</div>
    </div>
  );
  return href ? <a className="card" href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{body}</a>
    : <div className="card">{body}</div>;
}

// ---- Fixed assets ----------------------------------------------------------
function Assets({ d, notify }) {
  const nav = useNav();
  const s = d.summary || {};
  const [tab, setTab] = useState('register');
  const [q, setQ] = useState(d.q || '');
  const [cat, setCat] = useState(d.category || '');
  const [status, setStatus] = useState(d.status || '');
  const [section, setSection] = useState(d.section || '');
  const [editing, setEditing] = useState(null);   // asset being edited, or {} for add
  const [disposing, setDisposing] = useState(null);
  const [transferring, setTransferring] = useState(null);
  const [movingStatus, setMovingStatus] = useState(null);
  const [checkingOut, setCheckingOut] = useState(null);
  const [assigning, setAssigning] = useState(null);
  const [managingUnits, setManagingUnits] = useState(null);
  const [viewingMaintenance, setViewingMaintenance] = useState(null);
  const [viewingHistory, setViewingHistory] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [bulkDisposing, setBulkDisposing] = useState(false);
  const [bulkTransferTo, setBulkTransferTo] = useState('');
  const [bulkAssignTo, setBulkAssignTo] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const shown = d.assets.filter((a) => {
    if (q && !(`${a.name} ${a.asset_tag} ${a.serial_number}`.toLowerCase().includes(q.toLowerCase()))) return false;
    if (cat && a.category !== cat) return false;
    if (status && !(a.status_breakdown || []).some((r) => r.status === status && r.quantity > 0)) return false;
    if (section && a.effective_section !== section) return false;
    return true;
  });
  // A filter change can hide rows that were selected — clear the selection
  // rather than leave invisible/stale ids acted on by the bulk bar.
  useEffect(() => { setSelected(new Set()); }, [q, cat, status, section]);
  const badge = (st) => {
    const tone = st === 'In Use' ? 'badge-success' : st === 'Disposed' ? 'badge-secondary'
      : st === 'Under Repair' ? 'badge-warning' : st === 'Lost' ? 'badge-danger' : 'badge-info';
    return <span className={'badge ' + tone}>{st}</span>;
  };
  const doDelete = async (a) => {
    const ok = await confirm({ title: 'Delete asset', tone: 'danger', confirmText: 'Delete',
      message: `Permanently delete "${a.name}"? This removes its full history too — this can't be undone. To just retire it and keep the record, use Dispose instead.` });
    if (!ok) return;
    const r = await submitJson(a.delete_url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not delete.');
  };
  const toggleOne = (id) => setSelected((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const allShownSelected = shown.length > 0 && shown.every((a) => selected.has(a.id));
  const toggleAll = () => setSelected(allShownSelected ? new Set() : new Set(shown.map((a) => a.id)));
  const selectedIds = [...selected];
  const clearSelection = () => setSelected(new Set());
  const runBulk = async (url, payload, fallback) => {
    setBulkBusy(true);
    const r = await submitJson(url, { ...payload, asset_ids: selectedIds });
    setBulkBusy(false);
    if (r.ok) { notify('success', r.message || fallback); clearSelection(); nav.refresh(); }
    else notify('error', r.error || 'Bulk action failed.');
    return r.ok;
  };
  const doBulkTransfer = async () => {
    if (!bulkTransferTo.trim()) { notify('error', 'Enter the destination location.'); return; }
    if (await runBulk(d.bulk_transfer_url, { location: bulkTransferTo.trim() }, 'Transferred.')) setBulkTransferTo('');
  };
  const doBulkAssign = async () => {
    if (await runBulk(d.bulk_assign_url, { custodian: bulkAssignTo.trim() }, 'Assigned.')) setBulkAssignTo('');
  };
  const doBulkDelete = async () => {
    const ok = await confirm({ title: 'Delete selected assets', tone: 'danger', confirmText: 'Delete',
      message: `Permanently delete ${selectedIds.length} selected asset(s)? This removes their full history too — this can't be undone.` });
    if (!ok) return;
    runBulk(d.bulk_delete_url, {}, 'Deleted.');
  };
  return (
    <>
      <PageHeader icon="fa-building-columns" title="Fixed Assets" actions={<>
        {canWrite(d, 'assets_create') && <button type="button" className="btn btn-primary" onClick={() => setEditing({})}><i aria-hidden="true" className="fas fa-plus" /> Register asset</button>}
        {canWrite(d, 'assets_export') && <a className="btn btn-secondary" href={d.export_url}><i aria-hidden="true" className="fas fa-file-excel" /> Export</a>}
        <a href={d.urls.products} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-boxes-stacked" /> Products</a>
      </>} />
      <div className="card mb-3" style={{ padding: '.25rem' }}>
        <div style={{ display: 'flex', gap: '.25rem', flexWrap: 'wrap' }}>
          <button type="button" style={{ whiteSpace: 'nowrap' }} className={'btn btn-sm ' + (tab === 'register' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('register')}><i aria-hidden="true" className="fas fa-list" /> Register</button>
          <button type="button" style={{ whiteSpace: 'nowrap' }} className={'btn btn-sm ' + (tab === 'analytics' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('analytics')}><i aria-hidden="true" className="fas fa-chart-pie" /> Analytics</button>
          <button type="button" style={{ whiteSpace: 'nowrap' }} className={'btn btn-sm ' + (tab === 'history' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('history')}><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Historical</button>
          <button type="button" style={{ whiteSpace: 'nowrap' }} className={'btn btn-sm ' + (tab === 'audits' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('audits')}><i aria-hidden="true" className="fas fa-clipboard-check" /> Audits</button>
          <button type="button" style={{ whiteSpace: 'nowrap' }} className={'btn btn-sm ' + (tab === 'loans' ? 'btn-primary' : 'btn-light')} onClick={() => setTab('loans')}><i aria-hidden="true" className="fas fa-right-left" /> Loans</button>
        </div>
      </div>
      {tab === 'analytics' ? (
        <AssetAnalytics d={d} />
      ) : tab === 'history' ? (
        <AssetSnapshots d={d} />
      ) : tab === 'audits' ? (
        <AssetAudits d={d} notify={notify} />
      ) : tab === 'loans' ? (
        <AssetLoans d={d} notify={notify} />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
            <Tile n={s.count || 0} label="Active assets" />
            <Tile n={s.quantity || 0} label="Total units" />
            <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(s.total_cost || 0)}</div><div className="text-muted text-sm">Acquisition cost</div></div></div>
            <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(s.total_book || 0)}</div><div className="text-muted text-sm">Net book value</div></div></div>
            <Tile n={s.disposed || 0} label="Fully disposed" />
          </div>
          <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <input type="search" className="form-control" placeholder="Search name / tag / serial" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 240 }} />
            <select className="form-control" value={cat} onChange={(e) => setCat(e.target.value)} style={{ maxWidth: 200 }}><option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
            <select className="form-control" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 160 }}><option value="">All statuses</option>{d.statuses.map((st) => <option key={st}>{st}</option>)}</select>
            <select className="form-control" value={section} onChange={(e) => setSection(e.target.value)} style={{ maxWidth: 180 }}><option value="">All sections</option>{d.sections.map((sc) => <option key={sc.key} value={sc.key}>{sc.label}</option>)}</select>
          </div></div>
          {selectedIds.length > 0 && canWrite(d, 'assets_bulk') && (
            <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
              <div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                <strong style={{ marginRight: '.25rem' }}>{selectedIds.length} selected</strong>
                <input className="form-control" style={{ maxWidth: 170 }} placeholder="New location…"
                       value={bulkTransferTo} onChange={(e) => setBulkTransferTo(e.target.value)} disabled={bulkBusy} />
                <button type="button" className="btn btn-sm btn-secondary" disabled={bulkBusy || !bulkTransferTo.trim()}
                        onClick={doBulkTransfer} title="Transfer selected (batch-tracked only)">
                  <i aria-hidden="true" className="fas fa-truck-ramp-box" /> Transfer
                </button>
                <input className="form-control" style={{ maxWidth: 170 }} placeholder="Custodian (blank = unassign)…"
                       value={bulkAssignTo} onChange={(e) => setBulkAssignTo(e.target.value)} disabled={bulkBusy} />
                <button type="button" className="btn btn-sm btn-secondary" disabled={bulkBusy}
                        onClick={doBulkAssign} title="Assign selected (batch-tracked only)">
                  <i aria-hidden="true" className="fas fa-user-tag" /> Assign
                </button>
                <button type="button" className="btn btn-sm btn-warning" disabled={bulkBusy}
                        onClick={() => setBulkDisposing(true)} title="Dispose selected (batch-tracked only)">
                  <i aria-hidden="true" className="fas fa-box-archive" /> Dispose
                </button>
                <button type="button" className="btn btn-sm btn-danger" disabled={bulkBusy}
                        onClick={doBulkDelete} title="Permanently delete selected">
                  <i aria-hidden="true" className="fas fa-trash" /> Delete
                </button>
                <button type="button" className="btn btn-sm btn-light" onClick={clearSelection} style={{ marginLeft: 'auto' }}>Clear</button>
              </div>
            </div>
          )}
          <div className="card"><div className="card-header"><h3>Assets ({shown.length})</h3></div>
            <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
              {shown.length ? (
                <table className="data-table"><thead><tr>
                  <th style={{ width: 30 }}><input type="checkbox" checked={allShownSelected} onChange={toggleAll} aria-label="Select all shown" /></th>
                  <th>Asset</th><th>Category</th><th className="text-right">Qty</th><th>Assigned to</th><th className="text-right">Book value</th><th>Custodian</th><th>Status</th><th /></tr></thead>
                  <tbody>{shown.map((a) => (
                    <tr key={a.id} className={selected.has(a.id) ? 'is-selected' : ''}>
                      <td><input type="checkbox" checked={selected.has(a.id)} onChange={() => toggleOne(a.id)} aria-label={`Select ${a.name}`} /></td>
                      <td><strong>{a.name}</strong>{a.asset_tag && <span className="text-muted text-sm"> · {a.asset_tag}</span>}{a.from_product && <span className="badge badge-light" title="Converted from inventory" style={{ marginLeft: 4 }}>stock</span>}{a.serial_number && <div className="text-muted text-sm">SN {a.serial_number}</div>}</td>
                      <td>{a.category}</td>
                      <td className="text-right"><strong>{a.quantity}</strong></td>
                      <td className="text-muted text-sm">
                        {a.class_name && <div>{a.class_name}{a.arm_name ? ` (${a.arm_name})` : ''}</div>}
                        {a.teacher_name && <div>{a.teacher_name}</div>}
                        {a.effective_section_label && <div>{a.effective_section_label}</div>}
                        {!a.class_name && !a.teacher_name && !a.effective_section_label && '—'}
                      </td>
                      <td className="text-right">{naira(a.book_value)}{a.annual_depreciation > 0 && <div className="text-muted text-sm">−{naira(a.annual_depreciation)}/yr</div>}</td>
                      <td className="text-muted text-sm">{a.custodian || '—'}{a.location && <div>{a.location}</div>}</td>
                      <td>
                        {a.is_split ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            {a.status_breakdown.map((r) => <span key={r.status} style={{ whiteSpace: 'nowrap' }}>{badge(r.status)} <span className="text-muted text-sm">×{r.quantity}</span></span>)}
                          </div>
                        ) : badge(a.status)}
                      </td>
                      <td><div style={{ display: 'flex', gap: '.3rem' }}>
                        <button type="button" className="btn btn-sm btn-light" onClick={() => setViewingHistory(a)} title="History"><i aria-hidden="true" className="fas fa-clock-rotate-left" /></button>
                        {canWrite(d, 'assets_maintenance') && <button type="button" className={'btn btn-sm ' + (a.maintenance_overdue ? 'btn-danger' : a.next_maintenance_due ? 'btn-warning' : 'btn-light')}
                                onClick={() => setViewingMaintenance(a)}
                                title={a.maintenance_overdue ? `Maintenance overdue (due ${a.next_maintenance_due})`
                                     : a.next_maintenance_due ? `Next maintenance due ${a.next_maintenance_due}` : 'Maintenance'}>
                          <i aria-hidden="true" className="fas fa-wrench" />
                        </button>}
                        {a.is_individually_tracked
                          ? <button type="button" className="btn btn-sm btn-primary" onClick={() => setManagingUnits(a)} title="Manage physical units"><i aria-hidden="true" className="fas fa-qrcode" /> Units</button>
                          : !a.is_disposed && <>
                            {canWrite(d, 'assets_edit') && <button type="button" className="btn btn-sm btn-light" onClick={() => setTransferring(a)} title="Transfer location"><i aria-hidden="true" className="fas fa-truck-ramp-box" /></button>}
                            {canWrite(d, 'assets_edit') && <button type="button" className="btn btn-sm btn-light" onClick={() => setAssigning(a)} title="Assign custodian"><i aria-hidden="true" className="fas fa-user-tag" /></button>}
                            {canWrite(d, 'assets_edit') && <button type="button" className="btn btn-sm btn-light" onClick={() => setMovingStatus(a)} title="Move quantity between statuses (e.g. some to Under Repair)"><i aria-hidden="true" className="fas fa-right-left" /></button>}
                            {canWrite(d, 'assets_loans') && <button type="button" className={'btn btn-sm ' + (a.on_loan_quantity > 0 ? 'btn-info' : 'btn-light')} onClick={() => setCheckingOut(a)}
                                    title={a.on_loan_quantity > 0 ? `${a.on_loan_quantity} currently checked out — click to check out more` : 'Check out to someone temporarily'}>
                              <i aria-hidden="true" className="fas fa-right-from-bracket" />{a.on_loan_quantity > 0 ? ` ${a.on_loan_quantity}` : ''}
                            </button>}
                          </>}
                        {canWrite(d, 'assets_edit') && <button type="button" className="btn btn-sm btn-light" onClick={() => setEditing(a)} title="Edit"><i aria-hidden="true" className="fas fa-pen" /></button>}
                        {!a.is_disposed && canWrite(d, 'assets_dispose') && <button type="button" className="btn btn-sm btn-light" onClick={() => setDisposing(a)} title="Dispose / retire"><i aria-hidden="true" className="fas fa-box-archive" /></button>}
                        {canWrite(d, 'assets_delete') && <button type="button" className="btn btn-sm btn-light" onClick={() => doDelete(a)} title="Delete permanently"><i aria-hidden="true" className="fas fa-trash text-danger" /></button>}
                      </div></td>
                    </tr>
                  ))}</tbody></table>
              ) : <EmptyState icon="fa-building-columns" title="No assets registered">Register one, or convert stock from the Products screen.</EmptyState>}
            </div></div>
        </>
      )}
      {editing && <AssetForm d={d} asset={editing.id ? editing : null} notify={notify}
                             onClose={() => setEditing(null)} onSaved={() => { setEditing(null); nav.refresh(); }} />}
      {disposing && <DisposeModal asset={disposing} notify={notify}
                                  onClose={() => setDisposing(null)} onSaved={() => { setDisposing(null); nav.refresh(); }} />}
      {transferring && <TransferModal asset={transferring} notify={notify}
                                      onClose={() => setTransferring(null)} onSaved={() => { setTransferring(null); nav.refresh(); }} />}
      {assigning && <AssignModal asset={assigning} notify={notify}
                                 onClose={() => setAssigning(null)} onSaved={() => { setAssigning(null); nav.refresh(); }} />}
      {movingStatus && <MoveStatusModal asset={movingStatus} d={d} notify={notify}
                                        onClose={() => setMovingStatus(null)} onSaved={() => { setMovingStatus(null); nav.refresh(); }} />}
      {checkingOut && <CheckoutModal asset={checkingOut} notify={notify}
                                     onClose={() => setCheckingOut(null)} onSaved={() => { setCheckingOut(null); nav.refresh(); }} />}
      {managingUnits && <AssetUnitsModal asset={managingUnits} d={d} notify={notify}
                                         onClose={() => setManagingUnits(null)} onSaved={() => { nav.refresh(); }} />}
      {viewingHistory && <AssetHistoryModal asset={viewingHistory} onClose={() => setViewingHistory(null)} />}
      {viewingMaintenance && <AssetMaintenanceModal asset={viewingMaintenance} d={d} notify={notify}
                                                    onClose={() => setViewingMaintenance(null)} onSaved={() => { setViewingMaintenance(null); nav.refresh(); }} />}
      {bulkDisposing && <BulkDisposeModal count={selectedIds.length} url={d.bulk_dispose_url} notify={notify}
                                          onClose={() => setBulkDisposing(false)}
                                          onSaved={(msg) => { setBulkDisposing(false); notify('success', msg); clearSelection(); nav.refresh(); }} />}
    </>
  );
}

function AssetForm({ d, asset, onClose, onSaved, notify }) {
  const [f, setF] = useState(() => ({
    name: asset?.name || '', asset_tag: asset?.asset_tag || '',
    category: asset?.category || (d.categories[0] || 'Other'),
    serial_number: asset?.serial_number || '', acquisition_cost: asset?.acquisition_cost ?? '',
    acquisition_date: asset?.acquisition_date || '', supplier: asset?.supplier || '',
    location: asset?.location || '', custodian: asset?.custodian || '',
    status: asset?.status || 'In Use', useful_life_years: asset?.useful_life_years ?? '',
    salvage_value: asset?.salvage_value ?? '', quantity: asset?.quantity ?? 1,
    class_id: asset?.class_id || '', arm_id: asset?.arm_id || '',
    teacher_id: asset?.teacher_id || '', section: asset?.section || '',
    change_note: '',
  }));
  const [individual, setIndividual] = useState(!!asset?.is_individually_tracked);
  const [useSplit, setUseSplit] = useState(!!asset?.is_split);
  const [splitRows, setSplitRows] = useState(() => (asset?.is_split
    ? asset.status_breakdown.map((r) => ({ status: r.status, quantity: String(r.quantity) }))
    : [{ status: f.status, quantity: String(f.quantity) }]));
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const setSplitRow = (i, k, v) => setSplitRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const addSplitRow = () => setSplitRows((rows) => [...rows, { status: d.statuses.find((s) => !rows.some((r) => r.status === s)) || d.statuses[0], quantity: '' }]);
  const removeSplitRow = (i) => setSplitRows((rows) => rows.filter((_, idx) => idx !== i));
  const splitTotal = splitRows.reduce((sum, r) => sum + (parseInt(r.quantity, 10) || 0), 0);
  const save = async () => {
    if (!f.name.trim()) { notify('error', 'Asset name is required.'); return; }
    if (!individual && !useSplit && !asset && (parseInt(f.quantity, 10) || 0) <= 0) {
      notify('error', 'Enter a quantity of at least 1.'); return;
    }
    const payload = { ...f, is_individually_tracked: individual ? 'on' : '' };
    if (individual) {
      delete payload.quantity; delete payload.status;
    } else if (useSplit) {
      const rows = splitRows.filter((r) => (parseInt(r.quantity, 10) || 0) > 0);
      if (!rows.length) { notify('error', 'Enter at least one status with a quantity.'); return; }
      payload.status_breakdown = JSON.stringify(rows.map((r) => ({ status: r.status, quantity: parseInt(r.quantity, 10) || 0 })));
    }
    const r = await submitJson(asset ? asset.edit_url : d.add_url, payload);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not save.');
  };
  return (
    <Modal title={asset ? 'Edit asset' : 'Register asset'} icon="fa-building-columns" size="lg" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Save</Button></>}>
      {!asset && (
        <div className="card" style={{ padding: '.7rem .9rem', marginBottom: '1rem', background: 'var(--surface-2, #f8f9fa)' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', fontWeight: 600, cursor: 'pointer', margin: 0 }}>
            <input type="checkbox" checked={individual} onChange={(e) => setIndividual(e.target.checked)} />
            Track each unit individually (serial numbers, QR codes, per-unit location)
          </label>
          <span className="text-muted text-sm">For expensive, long-lived items like laptops, projectors, or vehicles. Use batch quantity below for cheap, high-volume items like chairs or textbooks. Can't be changed after saving.</span>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Name *"><input className="form-control" value={f.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label="Asset tag"><input className="form-control" value={f.asset_tag} onChange={(e) => set('asset_tag', e.target.value)} /></Field>
        <Field label="Category"><select className="form-control" value={f.category} onChange={(e) => set('category', e.target.value)}>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
        {!individual && !useSplit && <Field label="Quantity *"><input type="number" min="1" className="form-control" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} placeholder="e.g. 30 laptops" /></Field>}
        <Field label="Serial number"><input className="form-control" value={f.serial_number} onChange={(e) => set('serial_number', e.target.value)} /></Field>
        <Field label="Acquisition cost (₦)"><input type="number" className="form-control" value={f.acquisition_cost} onChange={(e) => set('acquisition_cost', e.target.value)} /></Field>
        <Field label="Acquired on"><input type="date" className="form-control" value={f.acquisition_date} onChange={(e) => set('acquisition_date', e.target.value)} /></Field>
        <Field label="Supplier"><input className="form-control" value={f.supplier} onChange={(e) => set('supplier', e.target.value)} /></Field>
        <Field label="Location"><input className="form-control" value={f.location} onChange={(e) => set('location', e.target.value)} /></Field>
        <Field label="Custodian"><input className="form-control" value={f.custodian} onChange={(e) => set('custodian', e.target.value)} /></Field>
        {!individual && !useSplit && <Field label="Status"><select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{d.statuses.filter((x) => x !== 'Disposed').map((st) => <option key={st}>{st}</option>)}</select></Field>}
        <Field label="Useful life (yrs)"><input type="number" className="form-control" value={f.useful_life_years} onChange={(e) => set('useful_life_years', e.target.value)} placeholder="for depreciation" /></Field>
        <Field label="Salvage value (₦)"><input type="number" className="form-control" value={f.salvage_value} onChange={(e) => set('salvage_value', e.target.value)} /></Field>
      </div>

      {individual && (
        <p className="text-muted text-sm" style={{ marginTop: '1rem' }}>Quantity and status come from the individual units you'll register next, on the assets list — not from fields here.</p>
      )}
      {!individual && (
      <>
      <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '.5rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '.4rem', fontWeight: 600, cursor: 'pointer' }}>
          <input type="checkbox" checked={useSplit} onChange={(e) => setUseSplit(e.target.checked)} />
          Track quantity by status
        </label>
        <span className="text-muted text-sm">e.g. of 30 laptops: 25 In Use, 3 Under Repair, 2 Lost</span>
      </div>
      {useSplit && (
        <div style={{ marginTop: '.5rem', display: 'flex', flexDirection: 'column', gap: '.4rem' }}>
          {splitRows.map((r, i) => (
            <div key={i} style={{ display: 'flex', gap: '.4rem', alignItems: 'center' }}>
              <select className="form-control" style={{ maxWidth: 180 }} value={r.status} onChange={(e) => setSplitRow(i, 'status', e.target.value)}>
                {d.statuses.map((st) => <option key={st}>{st}</option>)}
              </select>
              <input type="number" min="0" className="form-control" style={{ maxWidth: 120 }} value={r.quantity}
                     onChange={(e) => setSplitRow(i, 'quantity', e.target.value)} placeholder="Qty" />
              {splitRows.length > 1 && <button type="button" className="btn btn-sm btn-light" onClick={() => removeSplitRow(i)}><i aria-hidden="true" className="fas fa-xmark" /></button>}
            </div>
          ))}
          <div>
            <button type="button" className="btn btn-sm btn-light" onClick={addSplitRow}><i aria-hidden="true" className="fas fa-plus" /> Add status</button>
            <span className="text-muted text-sm" style={{ marginLeft: '.75rem' }}>Total: <strong>{splitTotal}</strong></span>
          </div>
        </div>
      )}
      </>
      )}

      <h4 style={{ margin: '1rem 0 .4rem' }}>Optional placement</h4>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Leave any of these blank — an asset can belong to none, one, or several.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Class"><select className="form-control" value={f.class_id} onChange={(e) => set('class_id', e.target.value)}>
          <option value="">— None —</option>{(d.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Arm"><select className="form-control" value={f.arm_id} onChange={(e) => set('arm_id', e.target.value)}>
          <option value="">— None —</option>{(d.arms || []).map((ar) => <option key={ar.id} value={ar.id}>{ar.name}</option>)}</select></Field>
        <Field label="Teacher"><select className="form-control" value={f.teacher_id} onChange={(e) => set('teacher_id', e.target.value)}>
          <option value="">— None —</option>{(d.teachers || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="Section"><select className="form-control" value={f.section} onChange={(e) => set('section', e.target.value)}>
          <option value="">— None / inherit from class —</option>{(d.sections || []).map((sc) => <option key={sc.key} value={sc.key}>{sc.label}</option>)}</select></Field>
      </div>
      <Field label="What changed? (optional)" wide><input className="form-control" value={f.change_note} onChange={(e) => set('change_note', e.target.value)}
             placeholder="e.g. 10 more units donated, 5 sent for repair…" /></Field>
      <p className="text-muted text-sm" style={{ marginTop: '.25rem' }}>Recorded in this asset's history so quantity/status changes can be compared term-to-term.</p>
    </Modal>
  );
}

function DisposeModal({ asset, onClose, onSaved, notify }) {
  const [f, setF] = useState({ disposed_on: '', disposal_amount: '', method: 'Cash', disposal_note: '', quantity: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    const r = await submitJson(asset.dispose_url, f);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not dispose.');
  };
  return (
    <Modal title={`Dispose "${asset.name}"`} icon="fa-box-archive" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="danger" onClick={save}>Dispose</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Currently active: <strong>{asset.active_quantity}</strong> of {asset.quantity}. Book value: <strong>{naira(asset.book_value)}</strong>. Any proceeds are posted to Finance as disposal income.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label={`Units to dispose (blank = all ${asset.active_quantity})`}><input type="number" min="1" max={asset.active_quantity} className="form-control" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} /></Field>
        <Field label="Disposed on"><input type="date" className="form-control" value={f.disposed_on} onChange={(e) => set('disposed_on', e.target.value)} /></Field>
        <Field label="Proceeds (₦)"><input type="number" className="form-control" value={f.disposal_amount} onChange={(e) => set('disposal_amount', e.target.value)} /></Field>
        <Field label="Method"><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}><option>Cash</option><option>Transfer</option><option>POS</option></select></Field>
        <Field label="Note" wide><input className="form-control" value={f.disposal_note} onChange={(e) => set('disposal_note', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function BulkDisposeModal({ count, url, onClose, onSaved, notify }) {
  const [f, setF] = useState({ disposed_on: '', disposal_amount: '', method: 'Cash', disposal_note: '' });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    setBusy(true);
    const r = await submitJson(url, f);
    setBusy(false);
    if (r.ok) onSaved(r.message); else notify('error', r.error || 'Could not dispose.');
  };
  return (
    <Modal title={`Dispose ${count} selected asset(s)`} icon="fa-box-archive" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="danger" onClick={save} disabled={busy}>Dispose all</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>
        Each selected asset is retired IN FULL (individually-tracked types and already-disposed assets are skipped).
        The same proceeds/note apply to every one — dispose individually instead for a different amount per asset.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Disposed on"><input type="date" className="form-control" value={f.disposed_on} onChange={(e) => set('disposed_on', e.target.value)} /></Field>
        <Field label="Proceeds per asset (₦)"><input type="number" className="form-control" value={f.disposal_amount} onChange={(e) => set('disposal_amount', e.target.value)} /></Field>
        <Field label="Method"><select className="form-control" value={f.method} onChange={(e) => set('method', e.target.value)}><option>Cash</option><option>Transfer</option><option>POS</option></select></Field>
        <Field label="Note" wide><input className="form-control" value={f.disposal_note} onChange={(e) => set('disposal_note', e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function AssetUnitsModal({ asset, d, onClose, onSaved, notify }) {
  const [units, setUnits] = useState(null);
  const [addUrl, setAddUrl] = useState('');
  const [addMode, setAddMode] = useState(false);
  const [addF, setAddF] = useState({ count: '1', prefix: '', unit_tag: '', serial_number: '', location: '', condition: 'Good', status: 'In Use' });
  const setAdd = (k, v) => setAddF((s) => ({ ...s, [k]: v }));
  const [busy, setBusy] = useState(false);
  const [viewingUnitHistory, setViewingUnitHistory] = useState(null);
  const reload = async () => {
    try {
      const r = await apiGet(asset.units_url);
      setUnits(r.units || []); setAddUrl(r.add_url || '');
    } catch { setUnits([]); }
  };
  useEffect(() => { reload(); }, [asset.units_url]);
  const bulkMode = parseInt(addF.count, 10) > 1;
  const doAdd = async () => {
    if (!addUrl) return;
    setBusy(true);
    const r = await submitJson(addUrl, addF);
    setBusy(false);
    if (r.ok) { notify('success', r.message); setAddMode(false); reload(); onSaved(); }
    else notify('error', r.error || 'Could not add units.');
  };
  const doAct = async (url, payload) => {
    const r = await submitJson(url, payload);
    if (r.ok) { notify('success', r.message); reload(); onSaved(); }
    else notify('error', r.error || 'Failed.');
  };
  const doReturn = async (u) => {
    const note = await promptDialog({ title: `Return "${u.unit_tag}"`,
      label: 'Return note (optional)', placeholder: 'e.g. condition on return', required: false });
    if (note === null) return;
    doAct(u.return_url, { return_note: note });
  };
  const COND_COLOR = { Good: 'b-ok', Fair: 'b-warn', Poor: 'b-bad' };
  const STAT_COLOR = { 'In Use': 'b-ok', 'Under Repair': 'b-warn', 'Lost': 'b-bad', 'Disposed': 'b-bad' };
  return (
    <>
    <Modal title={`Units — ${asset.name}`} icon="fa-qrcode" size="xl" onClose={onClose}
           footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <span className="text-muted text-sm">{units ? `${units.filter((u) => !u.is_disposed).length} active, ${units.filter((u) => u.is_disposed).length} disposed` : 'Loading…'}</span>
        {canWrite(d, 'assets_create') && <Button variant="primary" onClick={() => setAddMode((s) => !s)}><i aria-hidden="true" className="fas fa-plus" /> Add unit(s)</Button>}
      </div>
      {addMode && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-header"><h3>Register unit(s)</h3></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.6rem' }}>
              <Field label="Count"><input type="number" min="1" max="200" className="form-control" value={addF.count} onChange={(e) => setAdd('count', e.target.value)} /></Field>
              {bulkMode
                ? <Field label="Tag prefix (e.g. HPL)"><input className="form-control" value={addF.prefix} onChange={(e) => setAdd('prefix', e.target.value)} placeholder="HPL → HPL-00001…" /></Field>
                : <>
                    <Field label="Unit tag"><input className="form-control" value={addF.unit_tag} onChange={(e) => setAdd('unit_tag', e.target.value)} placeholder="auto if blank" /></Field>
                    <Field label="Serial number"><input className="form-control" value={addF.serial_number} onChange={(e) => setAdd('serial_number', e.target.value)} /></Field>
                  </>}
              <Field label="Location"><input className="form-control" value={addF.location} onChange={(e) => setAdd('location', e.target.value)} /></Field>
              <Field label="Condition"><select className="form-control" value={addF.condition} onChange={(e) => setAdd('condition', e.target.value)}>{(d.unit_conditions || ['Good', 'Fair', 'Poor']).map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Status"><select className="form-control" value={addF.status} onChange={(e) => setAdd('status', e.target.value)}>{(d.statuses || []).filter((s) => s !== 'Disposed').map((s) => <option key={s}>{s}</option>)}</select></Field>
            </div>
            <div style={{ display: 'flex', gap: '.5rem', marginTop: '.8rem' }}>
              <Button variant="primary" onClick={doAdd} disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save {addF.count || 1} unit(s)</Button>
              <Button variant="secondary" onClick={() => setAddMode(false)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
      {!units && <p className="text-muted text-sm">Loading…</p>}
      {units && units.length === 0 && <Empty icon="fa-qrcode" title="No units registered yet"><p>Use "Add unit(s)" to register each physical item.</p></Empty>}
      {units && units.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
          {units.map((u) => (
            <div key={u.id} className="card" style={{ padding: '.6rem .8rem', opacity: u.is_disposed ? .6 : 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
                <strong style={{ fontSize: '.95rem' }}>{u.unit_tag}</strong>
                <div style={{ display: 'flex', gap: '.25rem', flexWrap: 'wrap' }}>
                  <span className={`badge ${STAT_COLOR[u.is_disposed ? 'Disposed' : u.status] || 'b-ok'}`}>{u.is_disposed ? 'Disposed' : u.status}</span>
                  <span className={`badge ${COND_COLOR[u.condition] || 'b-ok'}`}>{u.condition}</span>
                </div>
              </div>
              <div className="text-sm" style={{ color: 'var(--text-muted)', marginTop: '.25rem' }}>
                {u.location && <span><i aria-hidden="true" className="fas fa-location-dot" /> {u.location}  </span>}
                {u.custodian && <span><i aria-hidden="true" className="fas fa-user" /> {u.custodian}</span>}
              </div>
              {u.on_loan && (
                <div className="text-sm" style={{ marginTop: '.25rem' }}>
                  <span className={`badge ${u.loan_overdue ? 'b-bad' : 'b-warn'}`}>
                    <i aria-hidden="true" className="fas fa-right-from-bracket" /> Checked out to {u.loan_borrower}
                    {u.loan_due_back ? ` (due ${u.loan_due_back})` : ''}{u.loan_overdue ? ' — overdue' : ''}
                  </span>
                </div>
              )}
              {!u.is_disposed && (
                <div style={{ display: 'flex', gap: '.25rem', flexWrap: 'wrap', marginTop: '.4rem' }}>
                  {canWrite(d, 'assets_edit') && <UnitInlineAction label="Transfer" icon="fa-truck-ramp-box"
                    fields={[{ name: 'location', placeholder: 'New location', required: true }]}
                    onSubmit={(p) => doAct(u.transfer_url, p)} />}
                  {canWrite(d, 'assets_edit') && <UnitInlineAction label="Assign" icon="fa-user-tag"
                    fields={[{ name: 'custodian', placeholder: 'Custodian (blank = unassign)' }]}
                    onSubmit={(p) => doAct(u.assign_url, p)} />}
                  {canWrite(d, 'assets_edit') && <UnitInlineAction label="Status" icon="fa-circle-half-stroke"
                    fields={[
                      { name: 'status', type: 'select', options: (d.statuses || []).filter((s) => s !== 'Disposed') },
                      { name: 'condition', type: 'select', options: d.unit_conditions || ['Good', 'Fair', 'Poor'] },
                      { name: 'note', placeholder: 'Note (optional)' },
                    ]}
                    onSubmit={(p) => doAct(u.status_url, p)} />}
                  {canWrite(d, 'assets_loans') && (u.on_loan
                    ? <button type="button" className="btn btn-sm btn-info" onClick={() => doReturn(u)} title="Mark returned"><i aria-hidden="true" className="fas fa-right-to-bracket" /> Return</button>
                    : <UnitInlineAction label="Checkout" icon="fa-right-from-bracket"
                        fields={[
                          { name: 'borrower', placeholder: 'Borrower', required: true },
                          { name: 'purpose', placeholder: 'Purpose (optional)' },
                          { name: 'due_back', placeholder: 'Due back YYYY-MM-DD (optional)' },
                        ]}
                        onSubmit={(p) => doAct(u.checkout_url, p)} />)}
                  <button type="button" className="btn btn-sm btn-light" title="History"
                    onClick={() => setViewingUnitHistory(u)}><i aria-hidden="true" className="fas fa-clock-rotate-left" /></button>
                  {canWrite(d, 'assets_delete') && <button type="button" className="btn btn-sm btn-light text-danger" title="Delete unit"
                    onClick={async () => { if (await confirm(`Delete ${u.unit_tag}?`)) doAct(u.delete_url, {}); }}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
    {viewingUnitHistory && <AssetHistoryModal
      asset={{ name: viewingUnitHistory.unit_tag, history_url: viewingUnitHistory.history_url }}
      onClose={() => setViewingUnitHistory(null)} />}
    </>
  );
}

function UnitInlineAction({ label, icon, fields, onSubmit }) {
  const [open, setOpen] = useState(false);
  const [vals, setVals] = useState({});
  const setV = (k, v) => setVals((s) => ({ ...s, [k]: v }));
  const submit = () => { onSubmit(vals); setOpen(false); setVals({}); };
  return open ? (
    <div style={{ display: 'flex', gap: '.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
      {fields.map((f) => f.type === 'select'
        ? <select key={f.name} className="form-control" style={{ maxWidth: 140 }} value={vals[f.name] || ''} onChange={(e) => setV(f.name, e.target.value)}><option value="">— {f.name} —</option>{(f.options || []).map((o) => <option key={o}>{o}</option>)}</select>
        : <input key={f.name} className="form-control" style={{ maxWidth: 160 }} placeholder={f.placeholder} required={f.required} value={vals[f.name] || ''} onChange={(e) => setV(f.name, e.target.value)} />)}
      <button type="button" className="btn btn-sm btn-primary" onClick={submit}><i aria-hidden="true" className="fas fa-check" /></button>
      <button type="button" className="btn btn-sm btn-light" onClick={() => { setOpen(false); setVals({}); }}><i aria-hidden="true" className="fas fa-xmark" /></button>
    </div>
  ) : (
    <button type="button" className="btn btn-sm btn-light" onClick={() => setOpen(true)}><i aria-hidden="true" className={`fas ${icon}`} /> {label}</button>
  );
}

function AssetMaintenanceModal({ asset, d, onClose, onSaved, notify }) {
  const [records, setRecords] = useState(null);
  const [summary, setSummary] = useState(null);
  const [addMode, setAddMode] = useState(false);
  const [editingRec, setEditingRec] = useState(null);
  const [f, setF] = useState({ status: 'Completed', problem: '', diagnosis: '', action_taken: '',
    technician: '', started_on: '', completed_on: '', next_maintenance_on: '',
    cost: '', parts_used: '', warranty_covered: '', reference: '', notes: '', unit_id: '' });
  const setFk = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const [busy, setBusy] = useState(false);
  const reload = async () => {
    try {
      const r = await apiGet(asset.maintenance_url);
      setRecords(r.records || []); setSummary(r.asset || null);
    } catch { setRecords([]); }
  };
  useEffect(() => { reload(); }, [asset.maintenance_url]);
  const startAdd = () => { setF({ status: 'Completed', problem: '', diagnosis: '', action_taken: '', technician: '', started_on: '', completed_on: '', next_maintenance_on: '', cost: '', parts_used: '', warranty_covered: '', reference: '', notes: '', unit_id: '' }); setAddMode(true); setEditingRec(null); };
  const startEdit = (rec) => { setF({ ...rec, cost: rec.cost ? String(rec.cost) : '', warranty_covered: rec.warranty_covered ? 'on' : '' }); setEditingRec(rec); setAddMode(true); };
  const save = async () => {
    if (!f.problem.trim()) { notify('error', 'Describe the problem.'); return; }
    setBusy(true);
    const url = editingRec ? editingRec.edit_url : asset.add_maintenance_url;
    const r = await submitJson(url, { ...f, warranty_covered: f.warranty_covered ? 'on' : '' });
    setBusy(false);
    if (r.ok) { notify('success', r.message); setAddMode(false); setEditingRec(null); reload(); onSaved(); }
    else notify('error', r.error || 'Could not save.');
  };
  const del = async (rec) => {
    if (!await confirm(`Delete this maintenance record?`)) return;
    const r = await submitJson(rec.delete_url, {});
    if (r.ok) { notify('success', r.message); reload(); onSaved(); }
    else notify('error', r.error || 'Could not delete.');
  };
  const STATUS_COLOR = { Completed: 'b-ok', 'In Progress': 'b-warn', Scheduled: 'b-secondary', Cancelled: 'b-bad' };
  return (
    <Modal title={`Maintenance — ${asset.name}`} icon="fa-wrench" size="xl" onClose={onClose}
           footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.6rem', marginBottom: '1rem' }}>
          <Tile n={`₦${(summary.total_maintenance_cost || 0).toLocaleString()}`} label="Total maintenance cost" />
          <Tile n={`₦${(summary.acquisition_cost || 0).toLocaleString()}`} label="Acquisition cost" />
          <Tile n={records ? records.filter((r) => r.status !== 'Cancelled').length : 0} label="Service events" />
          {summary.possibly_uneconomical && (
            <div className="card" style={{ borderColor: 'var(--danger)', padding: '.7rem', background: 'rgba(185,28,28,.06)' }}>
              <strong className="text-danger text-sm">⚠ Possibly uneconomical</strong>
              <div className="text-muted text-sm" style={{ marginTop: '.2rem' }}>Maintenance cost exceeds 50% of acquisition cost — consider replacing.</div>
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '.75rem' }}>
        <Button variant="primary" onClick={startAdd}><i aria-hidden="true" className="fas fa-plus" /> Log maintenance</Button>
      </div>
      {addMode && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-header"><h3>{editingRec ? 'Edit maintenance record' : 'Log maintenance event'}</h3></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.6rem' }}>
              <Field label="Status"><select className="form-control" value={f.status} onChange={(e) => setFk('status', e.target.value)}>{(d.maintenance_statuses || ['Completed', 'In Progress', 'Scheduled']).map((s) => <option key={s}>{s}</option>)}</select></Field>
              <Field label="Problem / symptom *"><input className="form-control" value={f.problem} onChange={(e) => setFk('problem', e.target.value)} placeholder="e.g. Screen backlight failure" /></Field>
              <Field label="Diagnosis"><input className="form-control" value={f.diagnosis} onChange={(e) => setFk('diagnosis', e.target.value)} /></Field>
              <Field label="Action taken"><input className="form-control" value={f.action_taken} onChange={(e) => setFk('action_taken', e.target.value)} /></Field>
              <Field label="Technician / vendor"><input className="form-control" value={f.technician} onChange={(e) => setFk('technician', e.target.value)} /></Field>
              <Field label="Started"><input type="date" className="form-control" value={f.started_on} onChange={(e) => setFk('started_on', e.target.value)} /></Field>
              <Field label="Completed"><input type="date" className="form-control" value={f.completed_on} onChange={(e) => setFk('completed_on', e.target.value)} /></Field>
              <Field label="Next maintenance"><input type="date" className="form-control" value={f.next_maintenance_on} onChange={(e) => setFk('next_maintenance_on', e.target.value)} /></Field>
              <Field label="Cost (₦)"><input type="number" min="0" className="form-control" value={f.cost} onChange={(e) => setFk('cost', e.target.value)} /></Field>
              <Field label="Parts used"><input className="form-control" value={f.parts_used} onChange={(e) => setFk('parts_used', e.target.value)} placeholder="e.g. LCD backlight unit" /></Field>
              <Field label="Reference (invoice/WO#)"><input className="form-control" value={f.reference} onChange={(e) => setFk('reference', e.target.value)} /></Field>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', margin: '.6rem 0' }}>
              <input type="checkbox" id="wc" checked={!!f.warranty_covered} onChange={(e) => setFk('warranty_covered', e.target.checked ? 'on' : '')} />
              <label htmlFor="wc" className="text-sm" style={{ fontWeight: 600, cursor: 'pointer' }}>Covered under warranty</label>
            </div>
            <Field label="Notes" wide><input className="form-control" value={f.notes} onChange={(e) => setFk('notes', e.target.value)} /></Field>
            <div style={{ display: 'flex', gap: '.5rem', marginTop: '.8rem' }}>
              <Button variant="primary" onClick={save} disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</Button>
              <Button variant="secondary" onClick={() => { setAddMode(false); setEditingRec(null); }}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
      {!records && <p className="text-muted text-sm">Loading…</p>}
      {records && records.length === 0 && !addMode && <Empty icon="fa-wrench" title="No maintenance records"><p>Log the first one when this asset is serviced.</p></Empty>}
      {records && records.map((rec) => (
        <div key={rec.id} className="card mb-2" style={{ padding: '.65rem .9rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
            <div><strong>{rec.problem || 'Maintenance'}</strong>{rec.technician && <span className="text-muted text-sm"> · {rec.technician}</span>}</div>
            <div style={{ display: 'flex', gap: '.25rem', alignItems: 'center' }}>
              <span className={`badge ${STATUS_COLOR[rec.status] || 'b-ok'}`}>{rec.status}</span>
              {rec.warranty_covered && <span className="badge b-ok">Warranty</span>}
            </div>
          </div>
          <div className="text-sm" style={{ color: 'var(--text-muted)', marginTop: '.25rem', display: 'flex', flexWrap: 'wrap', gap: '.6rem' }}>
            {rec.started_on && <span><i aria-hidden="true" className="fas fa-calendar" /> {rec.started_on}{rec.completed_on ? ` → ${rec.completed_on}` : ''}</span>}
            {rec.downtime_days !== null && rec.downtime_days !== undefined && <span><i aria-hidden="true" className="fas fa-hourglass" /> {rec.downtime_days} day(s) downtime</span>}
            {rec.cost > 0 && <span><i aria-hidden="true" className="fas fa-naira-sign" /> ₦{(rec.cost).toLocaleString()}</span>}
            {rec.next_maintenance_on && <span><i aria-hidden="true" className="fas fa-calendar-check" /> Next: {rec.next_maintenance_on}</span>}
          </div>
          {rec.action_taken && <div className="text-sm" style={{ marginTop: '.2rem' }}>{rec.action_taken}</div>}
          <div style={{ display: 'flex', gap: '.25rem', marginTop: '.4rem' }}>
            <button type="button" className="btn btn-sm btn-light" onClick={() => startEdit(rec)}><i aria-hidden="true" className="fas fa-pen" /></button>
            <button type="button" className="btn btn-sm btn-light text-danger" onClick={() => del(rec)}><i aria-hidden="true" className="fas fa-trash" /></button>
          </div>
        </div>
      ))}
    </Modal>
  );
}

function TransferModal({ asset, onClose, onSaved, notify }) {
  const [f, setF] = useState({ location: '', reference: '', note: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    if (!f.location.trim()) { notify('error', 'Enter the destination location.'); return; }
    const r = await submitJson(asset.transfer_url, f);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not transfer.');
  };
  return (
    <Modal title={`Transfer "${asset.name}"`} icon="fa-truck-ramp-box" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Transfer</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Current location: <strong>{asset.location || 'Unspecified'}</strong>. The previous location stays in this asset's history.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="New location *"><input className="form-control" value={f.location} onChange={(e) => set('location', e.target.value)} placeholder="e.g. Mathematics Department" /></Field>
        <Field label="Reference (optional)"><input className="form-control" value={f.reference} onChange={(e) => set('reference', e.target.value)} placeholder="e.g. transfer slip #" /></Field>
      </div>
      <Field label="Note (optional)" wide><input className="form-control" value={f.note} onChange={(e) => set('note', e.target.value)} placeholder="e.g. Lab A being renovated" /></Field>
    </Modal>
  );
}

function AssignModal({ asset, onClose, onSaved, notify }) {
  const [f, setF] = useState({ custodian: asset.custodian || '', reference: '', note: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    const r = await submitJson(asset.assign_url, f);
    if (r.ok) onSaved(); else notify('error', r.error || 'Could not assign.');
  };
  return (
    <Modal title={`Assign "${asset.name}"`} icon="fa-user-tag" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Save</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Current custodian: <strong>{asset.custodian || 'Unassigned'}</strong>. Leave blank to unassign.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="New custodian"><input className="form-control" value={f.custodian} onChange={(e) => set('custodian', e.target.value)} placeholder="e.g. Mrs. Chukwu, or blank to unassign" /></Field>
        <Field label="Reference (optional)"><input className="form-control" value={f.reference} onChange={(e) => set('reference', e.target.value)} placeholder="e.g. handover slip #" /></Field>
      </div>
      <Field label="Note (optional)" wide><input className="form-control" value={f.note} onChange={(e) => set('note', e.target.value)} /></Field>
    </Modal>
  );
}

function MoveStatusModal({ asset, d, onClose, onSaved, notify }) {
  const buckets = (asset.status_breakdown || []).filter((r) => r.quantity > 0);
  const otherStatuses = (d.statuses || []).filter((s) => s !== 'Disposed');
  const [f, setF] = useState({
    from_status: buckets[0]?.status || '',
    to_status: otherStatuses.find((s) => s !== buckets[0]?.status) || '',
    quantity: '1', note: '',
  });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const have = buckets.find((r) => r.status === f.from_status)?.quantity || 0;
  const save = async () => {
    const qty = parseInt(f.quantity, 10) || 0;
    if (!f.from_status || !f.to_status) { notify('error', 'Choose a status to move from and to.'); return; }
    if (f.from_status === f.to_status) { notify('error', 'Choose two different statuses.'); return; }
    if (qty <= 0 || qty > have) { notify('error', `Enter 1–${have} unit(s).`); return; }
    const r = await submitJson(asset.move_status_url, f);
    if (r.ok) { notify('success', r.message); onSaved(); } else notify('error', r.error || 'Could not move.');
  };
  return (
    <Modal title={`Move quantity — "${asset.name}"`} icon="fa-right-left" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Move</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>Shift some of this asset's quantity from one status to another — e.g. move 3 of 30 laptops from "In Use" to "Under Repair" — without retyping the whole split.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.6rem' }}>
        <Field label="From *">
          <select className="form-control" value={f.from_status} onChange={(e) => set('from_status', e.target.value)}>
            {buckets.map((r) => <option key={r.status} value={r.status}>{r.status} ({r.quantity})</option>)}
          </select>
        </Field>
        <Field label="To *">
          <select className="form-control" value={f.to_status} onChange={(e) => set('to_status', e.target.value)}>
            {otherStatuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>
        <Field label={`Quantity (max ${have}) *`}>
          <input type="number" min="1" max={have} className="form-control" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} />
        </Field>
      </div>
      <Field label="Note (optional)" wide><input className="form-control" value={f.note} onChange={(e) => set('note', e.target.value)} placeholder="e.g. reported faulty screen" /></Field>
    </Modal>
  );
}

function CheckoutModal({ asset, onClose, onSaved, notify }) {
  const [f, setF] = useState({ borrower: '', purpose: '', quantity: '1', due_back: '', note: '' });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => {
    if (!f.borrower.trim()) { notify('error', 'Enter who this is going to.'); return; }
    const qty = parseInt(f.quantity, 10) || 0;
    if (qty <= 0 || qty > asset.available_quantity) { notify('error', `Enter 1–${asset.available_quantity} unit(s) (that's how many are available).`); return; }
    const r = await submitJson(asset.checkout_url, f);
    if (r.ok) { notify('success', r.message); onSaved(); } else notify('error', r.error || 'Could not check out.');
  };
  return (
    <Modal title={`Check out — "${asset.name}"`} icon="fa-right-from-bracket" size="md" onClose={onClose}
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={save}>Check out</Button></>}>
      <p className="text-muted text-sm" style={{ marginTop: 0 }}>
        Hand some of this asset to someone temporarily — e.g. laptops given to teachers to enter exam results — without changing its custodian or location. It shows up under Loans until marked returned.
        {' '}<strong>{asset.available_quantity}</strong> available{asset.on_loan_quantity > 0 ? ` (${asset.on_loan_quantity} already out)` : ''}.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: '.6rem' }}>
        <Field label="Borrower *"><input className="form-control" value={f.borrower} onChange={(e) => set('borrower', e.target.value)} placeholder="e.g. Mr. Adeyemi" /></Field>
        <Field label="Purpose"><input className="form-control" value={f.purpose} onChange={(e) => set('purpose', e.target.value)} placeholder="e.g. Entering exam results" /></Field>
        <Field label={`Quantity (max ${asset.available_quantity}) *`}><input type="number" min="1" max={asset.available_quantity} className="form-control" value={f.quantity} onChange={(e) => set('quantity', e.target.value)} /></Field>
        <Field label="Due back (optional)"><input type="date" className="form-control" value={f.due_back} onChange={(e) => set('due_back', e.target.value)} /></Field>
      </div>
      <Field label="Note (optional)" wide><input className="form-control" value={f.note} onChange={(e) => set('note', e.target.value)} /></Field>
    </Modal>
  );
}

function AssetLoans({ d, notify }) {
  const [loans, setLoans] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const load = async () => {
    try {
      const r = await apiGet(d.loans_url + (showAll ? '?status=all' : ''));
      setLoans(r.loans || []);
    } catch { setLoans([]); }
  };
  useEffect(() => { load(); }, [d.loans_url, showAll]);
  const doReturn = async (loan) => {
    const note = await promptDialog({ title: `Return from ${loan.borrower}`,
      label: 'Return note (optional)', placeholder: 'e.g. condition on return', required: false });
    if (note === null) return;
    const r = await submitJson(loan.return_url, { return_note: note });
    if (r.ok) { notify('success', r.message); load(); } else notify('error', r.error || 'Could not mark returned.');
  };
  const openCount = loans ? loans.filter((l) => l.is_out).length : 0;
  const overdueCount = loans ? loans.filter((l) => l.is_out && l.is_overdue).length : 0;
  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        <Tile n={openCount} label="Currently out" />
        <Tile n={overdueCount} label="Overdue" danger={overdueCount > 0} />
      </div>
      <div className="card">
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>{showAll ? 'All loans' : 'Currently out'}</h3>
          <button type="button" className="btn btn-sm btn-light" onClick={() => setShowAll((s) => !s)}>
            {showAll ? 'Show only open' : 'Show returned too'}
          </button>
        </div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          {!loans && <p className="text-muted text-sm" style={{ padding: '1rem' }}>Loading…</p>}
          {loans && loans.length === 0 && <EmptyState icon="fa-right-from-bracket" title="Nothing checked out">Use the checkout button on an asset or unit to hand it to someone temporarily.</EmptyState>}
          {loans && loans.length > 0 && (
            <table className="data-table"><thead><tr>
              <th>Asset</th><th>Borrower</th><th>Purpose</th><th className="text-right">Qty</th>
              <th>Checked out</th><th>Due back</th><th>Status</th><th /></tr></thead>
              <tbody>{loans.map((l) => (
                <tr key={l.id}>
                  <td><strong>{l.asset_name}</strong>{l.unit_tag && <span className="text-muted text-sm"> · {l.unit_tag}</span>}</td>
                  <td>{l.borrower}</td>
                  <td className="text-muted text-sm">{l.purpose || '—'}</td>
                  <td className="text-right">{l.quantity}</td>
                  <td className="text-muted text-sm">{l.checked_out_at}</td>
                  <td className="text-muted text-sm">{l.due_back || '—'}</td>
                  <td>{l.is_out
                    ? <span className={`badge ${l.is_overdue ? 'b-bad' : 'b-warn'}`}>{l.is_overdue ? 'Overdue' : 'Out'}</span>
                    : <span className="badge b-ok">Returned {l.returned_at}</span>}</td>
                  <td>{l.is_out && canWrite(d, 'assets_loans') && <button type="button" className="btn btn-sm btn-primary" onClick={() => doReturn(l)}><i aria-hidden="true" className="fas fa-check" /> Return</button>}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

function AssetHistoryModal({ asset, onClose }) {
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    apiGet(asset.history_url).then((r) => { if (alive) setLogs(r.logs || []); })
      .catch(() => { if (alive) setError('Could not load history.'); });
    return () => { alive = false; };
  }, [asset.history_url]);
  const EVENT_LABEL = { created: 'Registered', quantity_changed: 'Quantity changed',
    status_changed: 'Status changed', updated: 'Updated', disposed: 'Disposed', restored: 'Restored',
    transferred: 'Transferred', assigned: 'Assigned', unassigned: 'Unassigned',
    opening_balance: 'Opening balance', loaned: 'Checked out', returned: 'Returned' };
  return (
    <Modal title={`History — ${asset.name}`} icon="fa-clock-rotate-left" size="lg" onClose={onClose}
           footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {error && <p className="text-danger">{error}</p>}
      {!logs && !error && <p className="text-muted text-sm">Loading…</p>}
      {logs && (logs.length ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.6rem' }}>
          {logs.map((l) => (
            <div key={l.id} className="card" style={{ padding: '.6rem .8rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.3rem' }}>
                <strong>{EVENT_LABEL[l.event_type] || l.event_type}</strong>
                <span className="text-muted text-sm">{l.created_at}{l.created_by ? ` · ${l.created_by}` : ''}</span>
              </div>
              {l.quantity_after !== null && l.quantity_after !== undefined && (
                <div className="text-sm" style={{ marginTop: 2 }}>
                  Quantity: {l.quantity_before ?? '—'} → <strong>{l.quantity_after}</strong>
                  {l.quantity_delta ? <span className={l.quantity_delta > 0 ? 'text-success' : 'text-danger'}> ({l.quantity_delta > 0 ? '+' : ''}{l.quantity_delta})</span> : null}
                </div>
              )}
              {l.status_after && (
                <div className="text-sm" style={{ marginTop: 2 }}>Status: {l.status_before || '—'} → <strong>{l.status_after}</strong></div>
              )}
              {l.event_type === 'transferred' && (
                <div className="text-sm" style={{ marginTop: 2 }}>Location: {l.location_before || 'Unspecified'} → <strong>{l.location_after || 'Unspecified'}</strong></div>
              )}
              {(l.event_type === 'assigned' || l.event_type === 'unassigned') && (
                <div className="text-sm" style={{ marginTop: 2 }}>Custodian: {l.custodian_before || 'Unassigned'} → <strong>{l.custodian_after || 'Unassigned'}</strong></div>
              )}
              {l.reference && <div className="text-muted text-sm" style={{ marginTop: 2 }}>Ref: {l.reference}</div>}
              {(l.session || l.term) && <div className="text-muted text-sm" style={{ marginTop: 2 }}>{l.term}{l.term && l.session ? ' · ' : ''}{l.session}</div>}
              {l.note && <div className="text-sm" style={{ marginTop: 2 }}>{l.note}</div>}
            </div>
          ))}
        </div>
      ) : <EmptyState icon="fa-clock-rotate-left" title="No history yet" />)}
    </Modal>
  );
}

// ---- Fixed asset analytics --------------------------------------------------
// ---- Fixed asset physical audits -----------------------------------------
function AssetAudits({ d, notify }) {
  const nav = useNav();
  const [audits, setAudits] = useState(null);
  const [creating, setCreating] = useState(false);
  const [cf, setCf] = useState({ name: '', description: '', category_filter: '' });
  const setCfk = (k, v) => setCf((s) => ({ ...s, [k]: v }));
  const [activeAudit, setActiveAudit] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadAudits = async () => {
    try { const r = await apiGet(d.audits_url); setAudits(r.audits || []); }
    catch { setAudits([]); }
  };

  useEffect(() => { loadAudits(); }, [d.audits_url]);

  const loadDetail = async (audit) => {
    setActiveAudit(audit); setDetailLoading(true); setDetail(null);
    try { const r = await apiGet(audit.detail_url); setDetail(r.audit); }
    catch { setDetail(null); }
    finally { setDetailLoading(false); }
  };

  const doCreate = async () => {
    if (!cf.name.trim()) { notify('error', 'Enter a name for this audit.'); return; }
    const r = await submitJson(d.create_audit_url, cf);
    if (r.ok) { notify('success', r.message); setCreating(false); setCf({ name: '', description: '', category_filter: '' }); loadAudits(); }
    else notify('error', r.error || 'Could not create audit.');
  };

  const doAct = async (url, successMsg) => {
    const r = await submitJson(url, {});
    if (r.ok) { notify('success', r.message || successMsg); loadAudits(); if (activeAudit) loadDetail(activeAudit); }
    else notify('error', r.error || 'Failed.');
  };

  const markItem = async (item, state, extra = {}) => {
    const r = await submitJson(item.mark_url, { state, ...extra });
    if (r.ok) { notify('success', r.message); if (activeAudit) loadDetail(activeAudit); loadAudits(); }
    else notify('error', r.error || 'Failed.');
  };

  const STATE_COLOR = { Verified: 'b-ok', Missing: 'b-bad', Damaged: 'b-warn', 'Wrong Location': 'b-warn', Unexpected: 'b-secondary', Pending: 'b-secondary' };
  const STATUS_COLOR = { Draft: 'b-secondary', 'In Progress': 'b-warn', Completed: 'b-ok' };

  if (activeAudit) {
    const counts = detail ? detail.counts || {} : activeAudit.counts || {};
    const total = detail ? detail.total_items : activeAudit.total_items;
    const items = detail?.items || [];
    return (
      <>
        <div className="page-header">
          <h1>{activeAudit.name}</h1>
          <div className="page-header-actions">
            {detail?.status === 'Draft' && canWrite(d, 'assets_audit') && <Button variant="primary" onClick={() => doAct(activeAudit.start_url, 'Audit started.')}><i aria-hidden="true" className="fas fa-play" /> Start audit</Button>}
            {detail?.status === 'In Progress' && canWrite(d, 'assets_audit') && <Button variant="warning" onClick={async () => { if (await confirm('Mark all remaining Pending items as Missing and complete the audit?')) doAct(activeAudit.complete_url, 'Audit completed.'); }}><i aria-hidden="true" className="fas fa-flag-checkered" /> Complete</Button>}
            <Button variant="secondary" onClick={() => { setActiveAudit(null); setDetail(null); }}><i aria-hidden="true" className="fas fa-arrow-left" /> Back</Button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(110px,1fr))', gap: '.6rem', marginBottom: '1rem' }}>
          <Tile n={total || 0} label="Expected" />
          {Object.entries(counts).map(([st, n]) => <Tile key={st} n={n} label={st} />)}
        </div>
        {detailLoading && <p className="text-muted text-sm">Loading items…</p>}
        {!detailLoading && items.map((item) => (
          <div key={item.id} className="card mb-2" style={{ padding: '.6rem .9rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
              <div>
                <strong>{item.asset_name}</strong>
                {item.unit_tag && <span className="badge b-secondary" style={{ marginLeft: '.35rem' }}>{item.unit_tag}</span>}
              </div>
              <span className={`badge ${STATE_COLOR[item.state] || 'b-secondary'}`}>{item.state}</span>
            </div>
            {item.expected_location && <div className="text-muted text-sm"><i aria-hidden="true" className="fas fa-location-dot" /> Expected: {item.expected_location}</div>}
            {item.found_location && item.found_location !== item.expected_location && <div className="text-muted text-sm" style={{ color: 'var(--warn)' }}><i aria-hidden="true" className="fas fa-location-dot" /> Found: {item.found_location}</div>}
            {item.note && <div className="text-sm" style={{ marginTop: '.15rem' }}>{item.note}</div>}
            {detail?.status !== 'Completed' && item.state === 'Pending' && canWrite(d, 'assets_audit') && (
              <div style={{ display: 'flex', gap: '.25rem', flexWrap: 'wrap', marginTop: '.4rem' }}>
                <button type="button" className="btn btn-sm btn-primary" onClick={() => markItem(item, 'Verified')}><i aria-hidden="true" className="fas fa-check" /> Verified</button>
                <button type="button" className="btn btn-sm btn-warning" onClick={() => markItem(item, 'Damaged', { note: 'Reported damaged during audit' })}><i aria-hidden="true" className="fas fa-triangle-exclamation" /> Damaged</button>
                <button type="button" className="btn btn-sm btn-danger" onClick={() => markItem(item, 'Missing')}><i aria-hidden="true" className="fas fa-question" /> Missing</button>
                <UnitInlineAction label="Wrong Location" icon="fa-location-dot"
                  fields={[{ name: 'found_location', placeholder: 'Actual location found', required: true }]}
                  onSubmit={(p) => markItem(item, 'Wrong Location', p)} />
              </div>
            )}
            {detail?.status !== 'Completed' && item.state !== 'Pending' && canWrite(d, 'assets_audit') && (
              <button type="button" className="btn btn-sm btn-light" style={{ marginTop: '.4rem' }} onClick={() => markItem(item, 'Pending')}>Reset to Pending</button>
            )}
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      <div className="page-header"><h1>Asset Audits</h1>
        <div className="page-header-actions">
          {canWrite(d, 'assets_audit') && <Button variant="primary" onClick={() => setCreating((s) => !s)}><i aria-hidden="true" className="fas fa-plus" /> New audit</Button>}
        </div>
      </div>
      {creating && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-header"><h3>Create verification audit</h3></div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: '.6rem' }}>
              <Field label="Audit name *"><input className="form-control" value={cf.name} onChange={(e) => setCfk('name', e.target.value)} placeholder="e.g. Q3 2026 ICT Audit" /></Field>
              <Field label="Category filter (optional)"><select className="form-control" value={cf.category_filter} onChange={(e) => setCfk('category_filter', e.target.value)}>
                <option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Description (optional)" wide><input className="form-control" value={cf.description} onChange={(e) => setCfk('description', e.target.value)} /></Field>
            </div>
            <div style={{ display: 'flex', gap: '.5rem', marginTop: '.8rem' }}>
              <Button variant="primary" onClick={doCreate}><i aria-hidden="true" className="fas fa-clipboard-list" /> Create &amp; populate</Button>
              <Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
      {!audits && <p className="text-muted text-sm">Loading…</p>}
      {audits && audits.length === 0 && !creating && <Empty icon="fa-clipboard-check" title="No audits yet"><p>Create a verification audit to track a physical inspection of your assets.</p></Empty>}
      {audits && audits.map((audit) => (
        <div key={audit.id} className="card mb-2" style={{ padding: '.7rem .9rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
            <div>
              <strong>{audit.name}</strong>
              {audit.category_filter && <span className="badge b-secondary" style={{ marginLeft: '.35rem' }}>{audit.category_filter}</span>}
            </div>
            <span className={`badge ${STATUS_COLOR[audit.status] || 'b-secondary'}`}>{audit.status}</span>
          </div>
          <div className="text-muted text-sm" style={{ margin: '.2rem 0' }}>
            {audit.total_items} expected items
            {Object.entries(audit.counts || {}).map(([st, n]) => (
              <span key={st}> · <span className={`badge ${STATE_COLOR[st] || 'b-secondary'}`} style={{ fontSize: '.7rem' }}>{n} {st}</span></span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '.3rem', marginTop: '.4rem' }}>
            <Button variant="secondary" onClick={() => loadDetail(audit)}><i aria-hidden="true" className="fas fa-eye" /> View</Button>
            {audit.status === 'Draft' && canWrite(d, 'assets_audit') && <Button variant="primary" onClick={() => doAct(audit.start_url, 'Started.')}><i aria-hidden="true" className="fas fa-play" /> Start</Button>}
            {audit.status === 'In Progress' && canWrite(d, 'assets_audit') && <Button variant="warning" onClick={async () => { if (await confirm('Complete and mark all Pending as Missing?')) doAct(audit.complete_url, 'Completed.'); }}>Complete</Button>}
            {canWrite(d, 'assets_audit') && <button type="button" className="btn btn-sm btn-light text-danger" onClick={async () => { if (await confirm(`Delete audit "${audit.name}"?`)) doAct(audit.delete_url, 'Deleted.'); }}><i aria-hidden="true" className="fas fa-trash" /></button>}
          </div>
        </div>
      ))}
    </>
  );
}

// ---- Fixed asset historical snapshots -------------------------------------
function AssetSnapshots({ d }) {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [snap, setSnap] = useState(null);
  const [snapError, setSnapError] = useState(null);
  const [terms, setTerms] = useState(null);
  const [termsError, setTermsError] = useState(null);

  useEffect(() => {
    let alive = true;
    setSnap(null); setSnapError(null);
    apiGet(`${d.snapshot_url}?date=${date}`).then((r) => { if (alive) setSnap(r); })
      .catch(() => { if (alive) setSnapError('Could not load the snapshot.'); });
    return () => { alive = false; };
  }, [date, d.snapshot_url]);

  useEffect(() => {
    let alive = true;
    apiGet(d.snapshot_terms_url).then((r) => { if (alive) setTerms(r); })
      .catch(() => { if (alive) setTermsError('Could not load the term comparison.'); });
    return () => { alive = false; };
  }, [d.snapshot_terms_url]);

  return (
    <>
      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-calendar-day" /> Assets as of a date</h3></div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>Reconstructed from each asset's event history — not a stored snapshot, so it reflects exactly what was known to be true that day.</p>
          <input type="date" className="form-control" style={{ maxWidth: 220 }} max={today} value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
      </div>

      {snapError && <p className="text-danger">{snapError}</p>}
      {!snap && !snapError && <p className="text-muted text-sm" style={{ padding: '1rem 0' }}>Loading…</p>}
      {snap && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
            <Tile n={snap.overview.asset_records || 0} label="Asset records" />
            <Tile n={snap.overview.total_units || 0} label="Total units" />
            {Object.entries(snap.overview.by_status || {}).map(([st, qty]) => (
              <Tile key={st} n={qty} label={st} />
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
            <div className="card"><div className="card-header"><h3>By category</h3></div><div className="card-body">
              <BarList rows={snap.by_category || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().green} /></div></div>
            <div className="card"><div className="card-header"><h3>By section</h3></div><div className="card-body">
              <BarList rows={snap.by_section || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().indigo} /></div></div>
          </div>
        </>
      )}

      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-table-columns" /> Term comparison</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          {termsError && <p className="text-danger" style={{ padding: '1rem' }}>{termsError}</p>}
          {!terms && !termsError && <p className="text-muted text-sm" style={{ padding: '1rem' }}>Loading…</p>}
          {terms && !terms.ok && <p className="text-muted" style={{ padding: '1rem' }}>{terms.error}</p>}
          {terms && terms.ok && (
            <table className="data-table">
              <thead><tr><th>Status</th>{terms.columns.map((c) => <th key={c.term} className="text-right">{c.term}</th>)}</tr></thead>
              <tbody>
                {terms.statuses.map((st) => (
                  <tr key={st}>
                    <td>{st}</td>
                    {terms.columns.map((c) => <td key={c.term} className="text-right">{c.totals[st] || 0}</td>)}
                  </tr>
                ))}
                <tr style={{ fontWeight: 700 }}>
                  <td>Total</td>
                  {terms.columns.map((c) => <td key={c.term} className="text-right">{c.total_units}</td>)}
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

function AssetAnalytics({ d }) {
  const [filters, setFilters] = useState({ category: '', section: '', class_id: '', status: '' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    const p = new URLSearchParams();
    if (filters.category) p.set('category', filters.category);
    if (filters.section) p.set('section', filters.section);
    if (filters.class_id) p.set('class_id', filters.class_id);
    if (filters.status) p.set('status', filters.status);
    const url = d.analytics_url + (p.toString() ? `?${p}` : '');
    apiGet(url).then((r) => { if (alive) setData(r); })
      .catch(() => { if (alive) setError('Could not load analytics.'); });
    return () => { alive = false; };
  }, [filters, d.analytics_url]);
  const setFilter = (k, v) => setFilters((s) => ({ ...s, [k]: v }));

  if (error) return <p className="text-danger">{error}</p>;
  if (!data) return <p className="text-muted text-sm" style={{ padding: '1rem 0' }}>Loading analytics…</p>;
  const o = data.overview || {};

  const deltaCell = (now, then, label) => {
    if (then === null || then === undefined) return <td className="text-right text-muted">—</td>;
    const delta = now - then;
    return (
      <td className="text-right">
        {then}
        {delta !== 0 && <span className={delta > 0 ? 'text-success' : 'text-danger'} style={{ marginLeft: 4 }}>({delta > 0 ? '+' : ''}{delta})</span>}
      </td>
    );
  };

  return (
    <>
      <div className="card mb-3"><div className="card-body" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <select className="form-control" value={filters.category} onChange={(e) => setFilter('category', e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="form-control" value={filters.status} onChange={(e) => setFilter('status', e.target.value)} style={{ maxWidth: 180 }}>
          <option value="">All statuses</option>{d.statuses.map((st) => <option key={st}>{st}</option>)}</select>
        <select className="form-control" value={filters.section} onChange={(e) => setFilter('section', e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All sections</option>{d.sections.map((sc) => <option key={sc.key} value={sc.key}>{sc.label}</option>)}</select>
        <select className="form-control" value={filters.class_id} onChange={(e) => setFilter('class_id', e.target.value)} style={{ maxWidth: 200 }}>
          <option value="">All classes</option>{(d.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      </div></div>
      {filters.status && <p className="text-muted text-sm" style={{ marginTop: '-.5rem', marginBottom: '1rem' }}>Showing only units currently marked "{filters.status}".</p>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '.75rem', marginBottom: '1rem' }}>
        <Tile n={o.count || 0} label="Active assets" />
        <Tile n={o.quantity || 0} label="Total units" />
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(o.total_cost || 0)}</div><div className="text-muted text-sm">Acquisition cost</div></div></div>
        <div className="card"><div className="card-body"><div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{naira(o.total_book || 0)}</div><div className="text-muted text-sm">Net book value</div></div></div>
        <Tile n={o.disposed_units || 0} label="Disposed units" />
        <Tile n={o.unassigned_placement || 0} label="No class/teacher/section" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: '1rem', marginBottom: '1rem' }}>
        <div className="card"><div className="card-header"><h3>By category</h3></div><div className="card-body">
          <BarList rows={data.by_category || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().green} sub={(r) => `${r.count} record(s)`} /></div></div>
        <div className="card"><div className="card-header"><h3>By status</h3></div><div className="card-body">
          <BarList rows={data.by_status || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().amber} sub={(r) => `${r.count} record(s)`} /></div></div>
        <div className="card"><div className="card-header"><h3>By section</h3></div><div className="card-body">
          <BarList rows={data.by_section || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().indigo} sub={(r) => `${r.count} record(s)`} /></div></div>
        <div className="card"><div className="card-header"><h3>By class</h3></div><div className="card-body">
          <BarList rows={data.by_class || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().cyan} sub={(r) => `${r.count} record(s)`} /></div></div>
        <div className="card"><div className="card-header"><h3>By teacher</h3></div><div className="card-body">
          <BarList rows={data.by_teacher || []} labelKey="label" valueKey="quantity" fmt={(v) => v} color={chartPalette().violet} sub={(r) => `${r.count} record(s)`} /></div></div>
      </div>

      <div className="card">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-scale-balanced" /> Quantity over time, by category</h3></div>
        <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="data-table">
            <thead><tr>
              <th>Category</th><th className="text-right">Now</th>
              <th className="text-right">7 days ago</th>
              <th className="text-right">{(data.comparison[0] && data.comparison[0].last_term_label) || 'Last term'}</th>
              <th className="text-right">{(data.comparison[0] && data.comparison[0].last_session_label) || 'Last session'}</th>
            </tr></thead>
            <tbody>{(data.comparison || []).map((r) => (
              <tr key={r.category} style={r.category === 'Total' ? { fontWeight: 700 } : undefined}>
                <td>{r.category}</td>
                <td className="text-right">{r.now}</td>
                {deltaCell(r.now, r.last_week)}
                {deltaCell(r.now, r.last_term)}
                {deltaCell(r.now, r.last_session)}
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </>
  );
}



const SCREENS = { dashboard: Screens.Dashboard, products: Screens.Products, new_sale: Screens.NewSale,
  history: Screens.History, analytics: Screens.Analytics, movements: Screens.Movements,
  suppliers: Screens.Suppliers, supplier_detail: Screens.SupplierDetail, purchases: Screens.Purchases,
  purchase_detail: Screens.PurchaseDetail, reports: Screens.Reports, promos: Screens.Promos,
  audits: Screens.Audits, audit_detail: Screens.AuditDetail, assets: Assets, batches: Screens.Batches };

export default function SalesApp({ data }) {
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
