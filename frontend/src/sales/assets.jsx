// Fixed asset register: the register itself plus its Analytics, History,
// Audits and Loans tabs, rebuilt on the results/sales kit. The add/edit and
// action dialogs below the screens are unchanged from the old SalesApp.jsx.
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { submitJson } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira, nairaShort } from '../lib/format';
import { useNav } from '../lib/section';
import { Empty, Modal, Button, confirm, promptDialog } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Field } from './forms';
import { Head, Tiles, Seg, Menu, Sheet, Blank, Bar, Meter, usePhone } from '../subjects/results';
import { SalesNav, Pill, Bars } from './kit';

const short = (v) => nairaShort(v);
const ST_TONE = { 'In Use': 'good', 'In Store': 'info', Available: 'info', 'Under Repair': 'mid', Lost: 'bad', Damaged: 'mid', Disposed: '' };
const fmtDate = (iso) => { try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); } catch (e) { return iso; } };
const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;

// ═══════════════════════════════════════════════════════════════════════════
export function Assets({ d, notify }) {
  const [tab, setTab] = useState(() => { try { return sessionStorage.getItem('assets:tab') || 'register'; } catch (e) { return 'register'; } });
  const pick = (t) => { setTab(t); try { sessionStorage.setItem('assets:tab', t); } catch (e) { /* ignore */ } };
  const s = d.summary || {};
  return (
    <div className="rs sl">
      <Head icon="fa-building-columns" title="Fixed assets" sub={`${plural(s.count || 0, 'asset')} · ${plural(s.quantity || 0, 'unit')} · ${naira(s.total_book || 0)} book value`}>
        {tab === 'register' && canWrite(d, 'assets_create') && <button type="button" className="rs-btn primary" onClick={() => window.dispatchEvent(new CustomEvent('assets:add'))}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Register asset</span></button>}
        <Menu label="More" items={[
          canWrite(d, 'assets_export') && { icon: 'fa-file-excel', label: 'Export register (Excel)', href: d.export_url, native: true },
          d.urls && d.urls.products && { icon: 'fa-boxes-stacked', label: 'Convert stock from Products', href: d.urls.products },
        ]} />
      </Head>
      <SalesNav d={d} />
      <Seg label="Asset views" value={tab} onChange={pick} options={[
        { value: 'register', label: 'Register', icon: 'fa-list' }, { value: 'loans', label: 'Loans', icon: 'fa-right-from-bracket' },
        { value: 'audits', label: 'Audits', icon: 'fa-clipboard-check' }, { value: 'analytics', label: 'Analytics', icon: 'fa-chart-pie' },
        { value: 'history', label: 'History', icon: 'fa-clock-rotate-left' }]} />
      {tab === 'register' && <Register d={d} notify={notify} />}
      {tab === 'loans' && <Loans d={d} notify={notify} />}
      {tab === 'audits' && <Audits d={d} notify={notify} />}
      {tab === 'analytics' && <Analytics d={d} />}
      {tab === 'history' && <Snapshots d={d} />}
    </div>
  );
}

// ── Register: master list + asset card ───────────────────────────────────────
// Laptop: list on the left, the chosen asset's card on the right (stays in view).
// Phone: tap an asset to slide in its full-screen page with a bottom action bar.
const CAT = {
  'ICT Equipment': ['fa-laptop', '#2563eb'], 'Furniture & Fittings': ['fa-chair', '#b45309'],
  'Laboratory Equipment': ['fa-flask', '#7c3aed'], Vehicles: ['fa-bus', '#0891b2'],
  Machinery: ['fa-gears', '#475569'], Buildings: ['fa-building', '#64748b'],
  'Sports Equipment': ['fa-futbol', '#16a34a'], 'Kitchen Equipment': ['fa-kitchen-set', '#ea580c'],
  'Musical Instruments': ['fa-music', '#db2777'], 'Books & Library': ['fa-book', '#0d9488'], Other: ['fa-box', '#6b7280'],
};
const catOf = (c) => CAT[c] || CAT.Other;
const ST_COLOR = { 'In Use': '#16a34a', 'In Store': '#2563eb', 'Under Repair': '#d97706', Lost: '#dc2626', Disposed: '#94a3b8' };
const placeOf = (a) => a.location || (a.class_name ? `${a.class_name}${a.arm_name ? ' ' + a.arm_name : ''}` : '') || '';
const EV = { created: 'Registered', quantity_changed: 'Quantity changed', status_changed: 'Status changed', updated: 'Details updated',
  disposed: 'Disposed', restored: 'Restored', transferred: 'Moved', assigned: 'Given to', unassigned: 'Custodian removed',
  opening_balance: 'Opening balance', loaned: 'Checked out', returned: 'Returned' };
const EV_IC = { created: 'fa-plus', transferred: 'fa-truck-ramp-box', assigned: 'fa-user-tag', unassigned: 'fa-user-xmark',
  disposed: 'fa-box-archive', status_changed: 'fa-right-left', quantity_changed: 'fa-hashtag', updated: 'fa-pen', restored: 'fa-rotate-left' };

function CatIcon({ category, size }) {
  const [ic, c] = catOf(category);
  return <span className={'ax-cat' + (size ? ' ' + size : '')} style={{ '--c': c }}><i className={'fas ' + ic} aria-hidden="true" /></span>;
}

// Units on loan are part of the active count (a loaned chair is still "In Use",
// just not on site), so they're carved out of the In Use bucket — never added.
function stripParts(a) {
  const rows = (a.status_breakdown || []).filter((r) => r.quantity > 0).map((r) => ({ ...r }));
  let loan = a.is_disposed ? 0 : (a.on_loan_quantity || 0);
  const out = [];
  rows.forEach((r) => {
    const take = (r.status === 'In Use' || r.status === 'In Store') ? Math.min(loan, r.quantity) : 0;
    loan -= take;
    if (r.quantity - take > 0) out.push({ key: r.status, label: r.status === 'In Use' && take ? 'In use here' : r.status, n: r.quantity - take, color: ST_COLOR[r.status] || '#94a3b8' });
    if (take) out.push({ key: r.status + '-loan', label: 'On loan', n: take, color: '#2563eb', loan: true });
  });
  return out;
}

function StatusStrip({ a, legend }) {
  const parts = stripParts(a);
  const total = parts.reduce((t, r) => t + r.n, 0) || 1;
  return (
    <div className="ax-strip-w">
      <div className="ax-strip" role="img" aria-label={parts.map((r) => `${r.n} ${r.label}`).join(', ')}>
        {parts.map((r) => <i key={r.key} className={r.loan ? 'loan' : ''} style={{ width: (r.n / total * 100) + '%', background: r.color }} />)}
      </div>
      {legend && (
        <div className="ax-legend">
          {parts.map((r) => <span key={r.key}><i className={r.loan ? 'loan' : ''} style={{ background: r.color }} /><b>{r.n}</b> {r.label}</span>)}
        </div>)}
    </div>
  );
}

function Register({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const s = d.summary || {};
  const [q, setQ] = useState(d.q || '');
  const [cat, setCat] = useState(d.category || '');
  const [status, setStatus] = useState(d.status || '');
  const [section, setSection] = useState(d.section || '');
  const [quick, setQuick] = useState('');
  const [group, setGroup] = useState(() => { try { return localStorage.getItem('assets:group') || 'none'; } catch (e) { return 'none'; } });
  const [filters, setFilters] = useState(false);
  const [modal, setModal] = useState(null);           // { kind, asset }
  const [picking, setPicking] = useState(false);      // select mode for bulk actions
  const [selected, setSelected] = useState(() => new Set());
  const [bulk, setBulk] = useState(null);
  const [bulkVal, setBulkVal] = useState('');
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState(null);
  useEffect(() => { const h = () => setModal({ kind: 'edit', asset: {} }); window.addEventListener('assets:add', h); return () => window.removeEventListener('assets:add', h); }, []);
  const pickGroup = (g) => { setGroup(g); try { localStorage.setItem('assets:group', g); } catch (e) { /* ignore */ } };
  const open = (kind, asset) => setModal({ kind, asset });
  const close = () => setModal(null);
  const saved = () => { setModal(null); nav.refresh(); };

  const qty = (a, st) => ((a.status_breakdown || []).find((r) => r.status === st) || {}).quantity || 0;
  const assets = d.assets;
  const overdue = assets.filter((a) => a.maintenance_overdue);
  const repair = assets.reduce((t, a) => t + qty(a, 'Under Repair'), 0);
  const lost = assets.reduce((t, a) => t + qty(a, 'Lost'), 0);
  const onLoan = assets.reduce((t, a) => t + (a.on_loan_quantity || 0), 0);
  const isUnplaced = (a) => !a.is_disposed && !a.class_name && !a.teacher_name && !a.effective_section_label && !a.custodian && !a.location;
  const unplaced = assets.filter(isUnplaced).length;
  const depYear = assets.reduce((t, a) => t + (a.annual_depreciation || 0), 0);
  const catCount = {};
  assets.forEach((a) => { catCount[a.category] = (catCount[a.category] || 0) + 1; });

  const t = q.trim().toLowerCase();
  const shown = assets.filter((a) => {
    if (t && !(`${a.name} ${a.asset_tag || ''} ${a.serial_number || ''} ${a.custodian || ''} ${a.location || ''} ${a.class_name || ''}`.toLowerCase().includes(t))) return false;
    if (cat && a.category !== cat) return false;
    if (status && !(a.status_breakdown || []).some((r) => r.status === status && r.quantity > 0)) return false;
    if (section && a.effective_section !== section) return false;
    if (quick === 'maint' && !a.maintenance_overdue) return false;
    if (quick === 'repair' && !qty(a, 'Under Repair') && !qty(a, 'Lost')) return false;
    if (quick === 'loan' && !a.on_loan_quantity) return false;
    if (quick === 'unplaced' && !isUnplaced(a)) return false;
    return true;
  });
  // Laptop: keep an asset open in the card (first one by default).
  const current = assets.find((a) => a.id === openId) || (!phone ? shown[0] : null);
  useEffect(() => { setSelected(new Set()); }, [q, cat, status, section, quick]);
  const ids = [...selected];
  const toggle = (id) => setSelected((x) => { const n = new Set(x); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const allSel = shown.length > 0 && shown.every((a) => selected.has(a.id));
  const runBulk = async (url, payload, msg) => {
    setBusy(true);
    const r = await submitJson(url, { ...payload, asset_ids: ids });
    setBusy(false);
    if (r.ok) { notify('success', r.message || msg); setSelected(new Set()); setBulk(null); setBulkVal(''); setPicking(false); nav.refresh(); } else notify('error', r.error || 'Bulk action failed.');
  };
  const bulkDelete = async () => {
    if (!await confirm({ title: 'Delete selected assets', tone: 'danger', confirmText: 'Delete', message: `Permanently delete ${ids.length} selected asset(s)? Their full history goes too — this can't be undone. Use Dispose to retire them and keep the record.` })) return;
    runBulk(d.bulk_delete_url, {}, 'Deleted.');
  };
  const doDelete = async (a) => {
    if (!await confirm({ title: 'Delete asset', tone: 'danger', confirmText: 'Delete', message: `Permanently delete "${a.name}"? This removes its full history too — this can't be undone. To retire it and keep the record, use Dispose instead.` })) return;
    const r = await submitJson(a.delete_url, {}); if (r.ok) { setOpenId(null); nav.refresh(); } else notify('error', r.error || 'Could not delete.');
  };
  const nFilters = [status, section].filter(Boolean).length;
  const quicks = [
    overdue.length > 0 && { value: 'maint', icon: 'fa-wrench', label: 'Maintenance overdue', n: overdue.length, tone: 'bad' },
    (repair + lost) > 0 && { value: 'repair', icon: 'fa-screwdriver-wrench', label: 'Repair or lost', n: repair + lost, tone: 'mid' },
    onLoan > 0 && { value: 'loan', icon: 'fa-right-from-bracket', label: 'On loan', n: onLoan, tone: 'info' },
    unplaced > 0 && { value: 'unplaced', icon: 'fa-location-crosshairs', label: 'No place or person', n: unplaced, tone: 'mid' },
  ].filter(Boolean);

  // grouping
  const groups = (() => {
    if (group === 'none') return [['', shown]];
    const m = new Map();
    shown.forEach((a) => {
      const k = group === 'place' ? (placeOf(a) || 'No location') : (a.category || 'Other');
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(a);
    });
    return [...m.entries()].sort((x, y) => (x[0] === 'No location') - (y[0] === 'No location') || x[0].localeCompare(y[0]));
  })();

  const row = (a) => {
    const on = current && current.id === a.id && !phone;
    const sel = selected.has(a.id);
    return (
      <button type="button" key={a.id} className={'ax-row' + (on ? ' on' : '') + (sel ? ' sel' : '') + (a.is_disposed ? ' off' : '')}
        onClick={() => (picking ? toggle(a.id) : setOpenId(a.id))} aria-pressed={picking ? sel : on}>
        {picking ? <span className={'ax-tick' + (sel ? ' on' : '')}><i className="fas fa-check" aria-hidden="true" /></span> : <CatIcon category={a.category} />}
        <span className="ax-row-t">
          <b>{a.name}{a.maintenance_overdue && <i className="fas fa-wrench ax-warn" title={`Maintenance overdue since ${a.next_maintenance_due}`} aria-label="Maintenance overdue" />}</b>
          <small><i className="fas fa-location-dot" aria-hidden="true" />{placeOf(a) || 'No location'}{a.custodian ? ` · ${a.custodian}` : ''}</small>
          <StatusStrip a={a} />
        </span>
        <span className="ax-row-v">
          <b>{a.is_disposed ? 'Disposed' : plural(a.active_quantity ?? a.quantity, 'unit')}</b>
          <small>{short(a.book_value)}</small>
        </span>
        {!picking && <i className="fas fa-chevron-right ax-chev" aria-hidden="true" />}
      </button>
    );
  };

  const list = (
    <section className="rs-card flush ax-list">
      <div className="ax-tools">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Find an asset, tag, room or person" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search assets" /></label>
        <button type="button" className={'rs-icon-btn' + (nFilters ? ' ax-on' : '')} onClick={() => setFilters(true)} aria-label={`Filters${nFilters ? ` (${nFilters} on)` : ''}`} title="Filters"><i className="fas fa-sliders" aria-hidden="true" />{nFilters > 0 && <em>{nFilters}</em>}</button>
        {canWrite(d, 'assets_bulk') && <button type="button" className={'rs-btn sm' + (picking ? ' primary' : ' ghost')} onClick={() => { setPicking((p) => !p); setSelected(new Set()); }}>{picking ? 'Done' : 'Select'}</button>}
      </div>
      <div className="ax-cats" role="radiogroup" aria-label="Category">
        <button type="button" role="radio" aria-checked={!cat} className={'rs-chip' + (!cat ? ' on' : '')} onClick={() => setCat('')}>All <small>{assets.length}</small></button>
        {d.categories.filter((c) => catCount[c]).map((c) => (
          <button type="button" role="radio" aria-checked={cat === c} key={c} className={'rs-chip' + (cat === c ? ' on' : '')} onClick={() => setCat(cat === c ? '' : c)}>
            <i className={'fas ' + catOf(c)[0]} aria-hidden="true" />{c.replace(' & Fittings', '').replace(' Equipment', '')} <small>{catCount[c]}</small></button>))}
      </div>
      <div className="ax-sub">
        <span>{plural(shown.length, 'asset')}{shown.length !== assets.length ? ` of ${assets.length}` : ''}</span>
        <Seg label="Group by" value={group} onChange={pickGroup} options={[{ value: 'none', label: 'List' }, { value: 'place', label: 'By place' }, { value: 'cat', label: 'By type' }]} />
      </div>
      {picking && <div className="ax-pickbar"><label className="rs-check"><input type="checkbox" checked={allSel} onChange={() => setSelected(allSel ? new Set() : new Set(shown.map((a) => a.id)))} /> Select all {shown.length}</label></div>}
      {shown.length ? (
        <div className="ax-rows">
          {groups.map(([g, rows]) => (
            <React.Fragment key={g || 'all'}>
              {g && <div className="ax-group"><span>{g}</span><small>{plural(rows.length, 'asset')} · {short(rows.reduce((x, a) => x + (a.book_value || 0), 0))}</small></div>}
              {rows.map(row)}
            </React.Fragment>))}
        </div>
      ) : <Blank icon="fa-building-columns" title={assets.length ? 'Nothing matches' : 'No assets yet'}>
          <p>{assets.length ? 'Try a different search or filter.' : 'Register desks, laptops, lab kit, vehicles — everything the school owns.'}</p>
          {!assets.length && canWrite(d, 'assets_create') && <button type="button" className="rs-btn primary" onClick={() => open('edit', {})}><i className="fas fa-plus" aria-hidden="true" />Register your first asset</button>}
        </Blank>}
    </section>
  );

  const card = current && <AssetCard key={current.id} a={current} d={d} open={open} doDelete={doDelete} phone={phone} onBack={() => setOpenId(null)} />;

  return (
    <>
      <div className="ax-stats">
        <div><span>Book value</span><b>{short(s.total_book || 0)}</b><small>cost {short(s.total_cost || 0)}</small></div>
        <div><span>Assets</span><b>{s.count || 0}</b><small>{plural(s.quantity || 0, 'unit')}</small></div>
        <div><span>Depreciation</span><b>{short(depYear)}</b><small>per year</small></div>
        <div className={lost ? 'bad' : repair ? 'mid' : ''}><span>Repair · lost</span><b>{repair} · {lost}</b><small>units</small></div>
        <div className={overdue.length ? 'bad' : ''}><span>Maintenance</span><b>{overdue.length}</b><small>{overdue.length ? 'overdue' : 'all up to date'}</small></div>
      </div>
      {quicks.length > 0 && (
        <div className="ax-attn" role="group" aria-label="Needs attention">
          {quicks.map((x) => (
            <button type="button" key={x.value} className={'ax-attn-b ' + x.tone + (quick === x.value ? ' on' : '')} onClick={() => setQuick(quick === x.value ? '' : x.value)} aria-pressed={quick === x.value}>
              <i className={'fas ' + x.icon} aria-hidden="true" /><b>{x.n}</b><span>{x.label}</span>{quick === x.value && <i className="fas fa-xmark ax-x" aria-hidden="true" />}
            </button>))}
        </div>)}

      {phone ? list : <div className="ax-split">{list}<div className="ax-pane">{card || <Blank icon="fa-hand-pointer" title="Pick an asset">Its details, value and history show here.</Blank>}</div></div>}
      {phone && current && createPortal(<div className="ax-page" role="dialog" aria-modal="true" aria-label={current.name}>{card}</div>, document.body)}
      {phone && !current && !picking && canWrite(d, 'assets_create') && createPortal(
        <button type="button" className="ax-fab" onClick={() => open('edit', {})} aria-label="Register asset"><i className="fas fa-plus" aria-hidden="true" /></button>, document.body)}

      {picking && ids.length > 0 && (
        <Bar>
          <span className="rs-bar-t"><b>{plural(ids.length, 'asset')} selected</b><small>Move, assign or retire together</small></span>
          <button type="button" className="rs-btn ghost" disabled={busy} onClick={() => setBulk('transfer')}><i className="fas fa-truck-ramp-box" aria-hidden="true" /><span className="rs-hide-sm">Move</span></button>
          <button type="button" className="rs-btn ghost" disabled={busy} onClick={() => setBulk('assign')}><i className="fas fa-user-tag" aria-hidden="true" /><span className="rs-hide-sm">Assign</span></button>
          <Menu label="" items={[
            canWrite(d, 'assets_dispose') && { icon: 'fa-box-archive', label: 'Dispose / retire', onClick: () => setBulk('dispose') },
            canWrite(d, 'assets_delete') && { icon: 'fa-trash', label: 'Delete permanently', danger: true, onClick: bulkDelete }]} />
        </Bar>
      )}

      {filters && (
        <Sheet title="Filter assets" onClose={() => setFilters(false)}>
          <div className="sl-form">
            <div className="ax-lbl">Status</div>
            <div className="rs-chips">{['', ...d.statuses].map((x) => <button type="button" key={x || 'all'} className={'rs-chip' + (status === x ? ' on' : '')} onClick={() => setStatus(x)}>{x || 'Any'}</button>)}</div>
            <div className="ax-lbl">Section</div>
            <div className="rs-chips">{[{ key: '', label: 'Whole school' }, ...d.sections].map((x) => <button type="button" key={x.key || 'all'} className={'rs-chip' + (section === x.key ? ' on' : '')} onClick={() => setSection(x.key)}>{x.label}</button>)}</div>
            <div className="ax-sheet-a">
              {nFilters > 0 && <button type="button" className="rs-btn ghost" onClick={() => { setStatus(''); setSection(''); }}>Clear</button>}
              <button type="button" className="rs-btn primary" onClick={() => setFilters(false)}>Show {plural(shown.length, 'asset')}</button>
            </div>
          </div>
        </Sheet>
      )}
      {(bulk === 'transfer' || bulk === 'assign') && (
        <Sheet title={bulk === 'transfer' ? `Move ${plural(ids.length, 'asset')}` : `Assign ${plural(ids.length, 'asset')}`} onClose={() => setBulk(null)}>
          <div className="sl-form">
            <p className="rs-muted">Applies to batch-tracked assets. Individually tracked ones are moved unit by unit from “Units”.</p>
            <PlaceInput d={d} kind={bulk === 'transfer' ? 'place' : 'person'} value={bulkVal} onChange={setBulkVal} />
            <button type="button" className="rs-btn primary wide" disabled={busy || (bulk === 'transfer' && !bulkVal.trim())}
              onClick={() => (bulk === 'transfer' ? runBulk(d.bulk_transfer_url, { location: bulkVal.trim() }, 'Moved.') : runBulk(d.bulk_assign_url, { custodian: bulkVal.trim() }, 'Assigned.'))}>
              {bulk === 'transfer' ? 'Move here' : bulkVal.trim() ? 'Assign' : 'Remove custodian'}</button>
          </div>
        </Sheet>
      )}
      {bulk === 'dispose' && <BulkDisposeModal count={ids.length} url={d.bulk_dispose_url} notify={notify} onClose={() => setBulk(null)}
        onSaved={(msg) => { setBulk(null); notify('success', msg); setSelected(new Set()); setPicking(false); nav.refresh(); }} />}

      {modal && modal.kind === 'edit' && <AssetForm d={d} asset={modal.asset.id ? modal.asset : null} notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'dispose' && <DisposeModal asset={modal.asset} notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'transfer' && <QuickPlaceSheet d={d} asset={modal.asset} kind="place" notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'assign' && <QuickPlaceSheet d={d} asset={modal.asset} kind="person" notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'status' && <MoveStatusModal asset={modal.asset} d={d} notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'checkout' && <CheckoutModal asset={modal.asset} notify={notify} onClose={close} onSaved={saved} />}
      {modal && modal.kind === 'units' && <AssetUnitsModal asset={modal.asset} d={d} notify={notify} onClose={close} onSaved={() => nav.refresh()} />}
      {modal && modal.kind === 'history' && <AssetHistoryModal asset={modal.asset} onClose={close} />}
      {modal && modal.kind === 'maint' && <AssetMaintenanceModal asset={modal.asset} d={d} notify={notify} onClose={close} onSaved={saved} />}
    </>
  );
}

// Suggest places / people already used in the register so moves are one tap.
function PlaceInput({ d, kind, value, onChange }) {
  const opts = useMemo(() => {
    const set = new Map();
    (d.assets || []).forEach((a) => {
      const v = kind === 'place' ? a.location : a.custodian;
      if (v) set.set(v, (set.get(v) || 0) + 1);
    });
    if (kind === 'person') (d.teachers || []).forEach((t) => { if (t.name && !set.has(t.name)) set.set(t.name, 0); });
    return [...set.entries()].sort((a, b) => b[1] - a[1]).map(([v]) => v).slice(0, 14);
  }, [d, kind]);
  return (
    <>
      <label className="sl-f"><span>{kind === 'place' ? 'Where is it going?' : 'Who is responsible for it?'}</span>
        <input value={value} onChange={(e) => onChange(e.target.value)} autoFocus placeholder={kind === 'place' ? 'e.g. ICT Lab 2' : 'e.g. Mr Bello (blank to remove)'} /></label>
      {opts.length > 0 && <div className="rs-chips ax-sugg">{opts.map((o) => <button type="button" key={o} className={'rs-chip' + (value === o ? ' on' : '')} onClick={() => onChange(o)}>{o}</button>)}</div>}
    </>
  );
}

function QuickPlaceSheet({ d, asset, kind, onClose, onSaved, notify }) {
  const [val, setVal] = useState(kind === 'place' ? '' : (asset.custodian || ''));
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(kind === 'place' ? asset.transfer_url : asset.assign_url,
      kind === 'place' ? { location: val.trim(), note } : { custodian: val.trim(), note });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Saved.'); onSaved(); } else notify('error', r.error || 'Could not save.');
  };
  return (
    <Sheet title={kind === 'place' ? `Move ${asset.name}` : `Assign ${asset.name}`} onClose={onClose}>
      <div className="sl-form">
        <p className="rs-muted">{kind === 'place' ? `Now: ${asset.location || 'no location'}` : `Now: ${asset.custodian || 'nobody'}`}</p>
        <PlaceInput d={d} kind={kind} value={val} onChange={setVal} />
        <label className="sl-f"><span>Note (optional)</span><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why it moved, handover reference…" /></label>
        <button type="button" className="rs-btn primary wide" disabled={busy || (kind === 'place' && !val.trim())} onClick={save}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{kind === 'place' ? 'Move here' : val.trim() ? 'Assign' : 'Remove custodian'}</button>
      </div>
    </Sheet>
  );
}

function AssetCard({ a, d, open, doDelete, phone, onBack }) {
  const [full, setFull] = useState(null);
  useEffect(() => {
    let alive = true;
    if (a.detail_url) apiGet(a.detail_url).then((r) => { if (alive && r.asset) setFull(r.asset); }).catch(() => {});
    return () => { alive = false; };
  }, [a.detail_url, a.book_value, a.quantity, a.location, a.custodian]);
  const w = (k) => canWrite(d, k);
  const live = !a.is_disposed;
  const batch = !a.is_individually_tracked;
  const acts = [
    live && batch && w('assets_edit') && { k: 'transfer', icon: 'fa-truck-ramp-box', label: 'Move' },
    live && batch && w('assets_edit') && { k: 'assign', icon: 'fa-user-tag', label: 'Assign' },
    live && batch && w('assets_loans') && { k: 'checkout', icon: 'fa-right-from-bracket', label: 'Lend out' },
    live && batch && w('assets_edit') && { k: 'status', icon: 'fa-right-left', label: 'Change status' },
    a.is_individually_tracked && { k: 'units', icon: 'fa-qrcode', label: 'Units' },
    w('assets_maintenance') && { k: 'maint', icon: 'fa-wrench', label: 'Maintenance', warn: a.maintenance_overdue },
    w('assets_edit') && { k: 'edit', icon: 'fa-pen', label: 'Edit' },
  ].filter(Boolean);
  const more = [
    { icon: 'fa-clock-rotate-left', label: 'Full history', onClick: () => open('history', a) },
    live && w('assets_dispose') && { icon: 'fa-box-archive', label: 'Dispose / retire', onClick: () => open('dispose', a) },
    w('assets_delete') && { icon: 'fa-trash', label: 'Delete permanently', danger: true, onClick: () => doDelete(a) },
  ];
  const age = a.acquisition_date ? Math.max(0, (Date.now() - new Date(a.acquisition_date)) / 31557600000) : null;
  const lifeLeft = a.useful_life_years && age != null ? Math.max(0, a.useful_life_years - age) : null;
  const ownership = [a.class_name && `${a.class_name}${a.arm_name ? ' ' + a.arm_name : ''}`, a.teacher_name, a.effective_section_label].filter(Boolean).join(' · ');
  const maint = (full && full.maintenance) || [];
  const timeline = (full && full.timeline) || [];
  const evText = (l) => {
    if (l.event_type === 'transferred') return `${l.location_before || 'Unspecified'} → ${l.location_after || 'Unspecified'}`;
    if (l.event_type === 'assigned') return l.custodian_after;
    if (l.event_type === 'unassigned') return `was ${l.custodian_before || '—'}`;
    if (l.breakdown_snapshot) return Object.entries(l.breakdown_snapshot).map(([k, v]) => `${v} ${k}`).join(', ');
    if (l.status_after) return `${l.status_before || '—'} → ${l.status_after}`;
    return '';
  };
  return (
    <article className="ax-card">
      <header className="ax-card-h">
        {phone && <button type="button" className="ax-back" onClick={onBack} aria-label="Back to assets"><i className="fas fa-chevron-left" aria-hidden="true" /></button>}
        <CatIcon category={a.category} size="lg" />
        <div className="ax-card-t">
          <h2>{a.name}</h2>
          <p>{[a.category, a.asset_tag, a.serial_number && `SN ${a.serial_number}`].filter(Boolean).join(' · ')}</p>
        </div>
        <Menu label="" items={more} />
      </header>
      <div className="ax-card-b">
        {a.is_disposed ? <div className="ax-note"><i className="fas fa-box-archive" aria-hidden="true" />Disposed on {a.disposed_on}{a.disposal_amount ? ` · sold for ${naira(a.disposal_amount)}` : ''}</div> : (
          <div className="ax-units"><div><b>{a.active_quantity ?? a.quantity}</b><span>{(a.active_quantity ?? a.quantity) === 1 ? 'unit' : 'units'} in all</span></div><StatusStrip a={a} legend /></div>)}

        {acts.length > 0 && (
          <div className={'ax-acts' + (phone ? ' dock' : '')}>
            {(phone ? acts.slice(0, 4) : acts).map((x) => (
              <button type="button" key={x.k} className={'ax-act' + (x.warn ? ' warn' : '')} onClick={() => open(x.k, a)}>
                <i className={'fas ' + x.icon} aria-hidden="true" /><span>{x.label}</span></button>))}
            {phone && acts.length > 4 && <Menu label="More" items={acts.slice(4).map((x) => ({ icon: x.icon, label: x.label, onClick: () => open(x.k, a) }))} />}
          </div>)}

        <div className="ax-facts">
          <div><i className="fas fa-location-dot" aria-hidden="true" /><span>Where</span>{a.location ? <b>{a.location}</b>
            : (live && batch && w('assets_edit') ? <button type="button" className="ax-set" onClick={() => open('transfer', a)}>Set location</button> : <b><em>Not set</em></b>)}</div>
          <div><i className="fas fa-user" aria-hidden="true" /><span>Responsible</span>{a.custodian ? <b>{a.custodian}</b>
            : (live && batch && w('assets_edit') ? <button type="button" className="ax-set" onClick={() => open('assign', a)}>Assign someone</button> : <b><em>Nobody</em></b>)}</div>
          {ownership && <div className="wide"><i className="fas fa-school" aria-hidden="true" /><span>Belongs to</span><b className="wrap">{ownership}</b></div>}
          {a.on_loan_quantity > 0 && <div><i className="fas fa-right-from-bracket" aria-hidden="true" /><span>Lent out</span><b>{a.on_loan_quantity} of {a.active_quantity} · {a.available_quantity} still here</b></div>}
          {a.supplier && <div><i className="fas fa-store" aria-hidden="true" /><span>Supplier</span><b>{a.supplier}</b></div>}
          {a.acquisition_date && <div><i className="fas fa-calendar" aria-hidden="true" /><span>Bought</span><b>{fmtDate(a.acquisition_date)}{age != null ? ` · ${age < 1 ? 'this year' : Math.floor(age) + ' yr ago'}` : ''}</b></div>}
        </div>

        <section className="ax-sec">
          <h3>Value</h3>
          {!(a.acquisition_cost > 0) ? (
            <div className="ax-note"><i className="fas fa-tag" aria-hidden="true" /><span>No purchase price recorded, so value and depreciation can't be worked out.</span>
              {w('assets_edit') && <button type="button" className="ax-set" onClick={() => open('edit', a)}>Add price</button>}</div>
          ) : (<>
            <div className="ax-val">
              <div><span>Worth now</span><b title={naira(a.book_value)}>{phone ? short(a.book_value) : naira(a.book_value)}</b></div>
              <div><span>Paid</span><b title={naira(a.acquisition_cost)}>{phone ? short(a.acquisition_cost) : naira(a.acquisition_cost)}</b></div>
              <div><span>Loses</span><b>{a.annual_depreciation > 0 ? <>{short(a.annual_depreciation)}<small>/yr</small></> : '—'}</b></div>
            </div>
            <Meter value={a.book_value} max={a.acquisition_cost} tone={a.book_value / a.acquisition_cost > 0.5 ? 'good' : a.book_value / a.acquisition_cost > 0.2 ? 'mid' : 'bad'} />
            {lifeLeft != null ? <p className="ax-small">{lifeLeft > 0 ? `About ${lifeLeft < 1 ? 'less than a year' : Math.round(lifeLeft) + ' years'} of useful life left (of ${a.useful_life_years}).` : `Past its ${a.useful_life_years}-year useful life — plan a replacement.`}</p>
              : <p className="ax-small">Add a useful life (years) to see depreciation.</p>}
          </>)}
        </section>

        <section className="ax-sec">
          <h3>Maintenance {w('assets_maintenance') && <button type="button" className="rs-link" onClick={() => open('maint', a)}>Log / view all</button>}</h3>
          {a.next_maintenance_due ? <div className={'ax-note ' + (a.maintenance_overdue ? 'bad' : '')}><i className="fas fa-wrench" aria-hidden="true" />{a.maintenance_overdue ? `Overdue since ${a.next_maintenance_due}` : `Next service due ${a.next_maintenance_due}`}</div>
            : <p className="ax-small">No service scheduled.</p>}
          {full && full.possibly_uneconomical && <div className="ax-note mid"><i className="fas fa-triangle-exclamation" aria-hidden="true" />Repairs have cost over half its price — consider replacing it.</div>}
          {maint.slice(0, 3).map((m) => (
            <div className="ax-tl" key={m.id}><i className="fas fa-screwdriver-wrench" aria-hidden="true" />
              <div><b>{m.problem || 'Service'}</b><small>{[m.completed_on || m.started_on || m.created_at, m.technician, m.status].filter(Boolean).join(' · ')}</small></div>
              <span>{m.cost ? naira(m.cost) : ''}</span></div>))}
          {(a.total_maintenance_cost || 0) > 0 && <p className="ax-small">Spent on upkeep so far: <b>{naira(a.total_maintenance_cost)}</b></p>}
        </section>

        {a.is_individually_tracked && full && full.units && (
          <section className="ax-sec">
            <h3>Units <button type="button" className="rs-link" onClick={() => open('units', a)}>Manage</button></h3>
            <p className="ax-small">{plural(full.units.length, 'unit')} with their own tag and QR code — move, assign or check them out one by one.</p>
          </section>)}

        <section className="ax-sec">
          <h3>Recent activity <button type="button" className="rs-link" onClick={() => open('history', a)}>Full history</button></h3>
          {!full ? <p className="ax-small">Loading…</p> : timeline.length ? timeline.slice(0, 6).map((l) => (
            <div className="ax-tl" key={l.id}><i className={'fas ' + (EV_IC[l.event_type] || 'fa-circle-dot')} aria-hidden="true" />
              <div><b>{EV[l.event_type] || l.event_type} {evText(l) && <span>· {evText(l)}</span>}</b><small>{l.created_at}{l.created_by ? ` · ${l.created_by}` : ''}{l.note ? ` · ${l.note}` : ''}</small></div></div>))
            : <p className="ax-small">No activity yet.</p>}
        </section>
        {full && full.active_audit_items && full.active_audit_items.length > 0 && (
          <div className="ax-note"><i className="fas fa-clipboard-check" aria-hidden="true" />In audit “{full.active_audit_items[0].audit_name}” — {full.active_audit_items[0].state}</div>)}
      </div>
    </article>
  );
}

// ── Loans ──────────────────────────────────────────────────────────────────
function Loans({ d, notify }) {
  const [loans, setLoans] = useState(null);
  const [show, setShow] = useState('out');
  const load = async () => { try { const r = await apiGet(d.loans_url + (show === 'all' ? '?status=all' : '')); setLoans(r.loans || []); } catch (e) { setLoans([]); } };
  useEffect(() => { load(); }, [d.loans_url, show]); // eslint-disable-line
  const doReturn = async (l) => {
    const note = await promptDialog({ title: `Return from ${l.borrower}`, label: 'Return note (optional)', placeholder: 'e.g. condition on return', required: false });
    if (note === null) return;
    const r = await submitJson(l.return_url, { return_note: note });
    if (r.ok) { notify('success', r.message); load(); } else notify('error', r.error || 'Could not mark returned.');
  };
  const out = loans ? loans.filter((l) => l.is_out) : [];
  const late = out.filter((l) => l.is_overdue);
  const rows = loans ? (show === 'late' ? late : loans) : [];
  return (
    <>
      <Tiles items={[
        { label: 'Checked out now', value: out.length, sub: `${out.reduce((t, l) => t + (l.quantity || 0), 0)} units` },
        { label: 'Overdue', value: late.length, tone: late.length ? 'bad' : 'good', sub: late.length ? 'chase these first' : 'nothing late' },
      ]} />
      <Seg label="Show" value={show} onChange={setShow} options={[{ value: 'out', label: 'Out now' }, { value: 'late', label: 'Overdue', count: late.length || null }, { value: 'all', label: 'Include returned' }]} />
      {!loans ? <p className="rs-muted">Loading…</p> : rows.length ? (
        <section className="rs-card flush"><div className="as-loans">
          {rows.map((l) => (
            <div key={l.id} className={'as-loan' + (l.is_out && l.is_overdue ? ' late' : '')}>
              <span className="n"><b>{l.asset_name}{l.unit_tag ? ` · ${l.unit_tag}` : ''}</b><small>{l.quantity > 1 ? `${l.quantity} units · ` : ''}{l.purpose || 'No purpose given'}</small></span>
              <span className="w"><b>{l.borrower}</b><small>out {l.checked_out_at}{l.due_back ? ` · due ${l.due_back}` : ''}</small></span>
              <span className="s">{l.is_out ? <Pill tone={l.is_overdue ? 'bad' : 'mid'}>{l.is_overdue ? 'Overdue' : 'Out'}</Pill> : <Pill tone="good">Returned {l.returned_at}</Pill>}</span>
              <span className="a">{l.is_out && canWrite(d, 'assets_loans') && <button type="button" className="rs-btn sm primary" onClick={() => doReturn(l)}><i className="fas fa-check" aria-hidden="true" /> Returned</button>}</span>
            </div>
          ))}
        </div></section>
      ) : <Blank icon="fa-right-from-bracket" title={show === 'late' ? 'Nothing overdue' : 'Nothing checked out'}><p>Use “Check out” on an asset (or a unit) to lend it out and track when it comes back.</p></Blank>}
    </>
  );
}

// ── Verification audits ────────────────────────────────────────────────────
const AU_TONE = { Verified: 'good', Missing: 'bad', Damaged: 'mid', 'Wrong Location': 'mid', Unexpected: 'info', Pending: '' };
const AU_STATUS = { Draft: '', 'In Progress': 'mid', Completed: 'good' };
function Audits({ d, notify }) {
  const [audits, setAudits] = useState(null);
  const [creating, setCreating] = useState(false);
  const [cf, setCf] = useState({ name: '', description: '', category_filter: '' });
  const [active, setActive] = useState(null);
  const [detail, setDetail] = useState(null);
  const [show, setShow] = useState('Pending');
  const [q, setQ] = useState('');
  const can = canWrite(d, 'assets_audit');
  const loadAudits = async () => { try { const r = await apiGet(d.audits_url); setAudits(r.audits || []); } catch (e) { setAudits([]); } };
  useEffect(() => { loadAudits(); }, [d.audits_url]); // eslint-disable-line
  const loadDetail = async (a) => { setActive(a); setDetail(null); try { const r = await apiGet(a.detail_url); setDetail(r.audit); } catch (e) { setDetail(null); } };
  const create = async () => {
    if (!cf.name.trim()) { notify('error', 'Give the audit a name.'); return; }
    const r = await submitJson(d.create_audit_url, cf);
    if (r.ok) { notify('success', r.message); setCreating(false); setCf({ name: '', description: '', category_filter: '' }); loadAudits(); } else notify('error', r.error || 'Could not create audit.');
  };
  const act = async (url, msg) => { const r = await submitJson(url, {}); if (r.ok) { notify('success', r.message || msg); loadAudits(); if (active) loadDetail(active); } else notify('error', r.error || 'Failed.'); };
  const mark = async (item, state, extra = {}) => {
    const r = await submitJson(item.mark_url, { state, ...extra });
    if (r.ok) { if (active) loadDetail(active); loadAudits(); } else notify('error', r.error || 'Failed.');
  };
  const wrongPlace = async (item) => {
    const where = await promptDialog({ title: 'Where was it found?', label: `Actual location of ${item.asset_name}`, placeholder: 'e.g. Staff room', required: true });
    if (where) mark(item, 'Wrong Location', { found_location: where });
  };

  if (active) {
    const counts = (detail ? detail.counts : active.counts) || {};
    const total = detail ? detail.total_items : active.total_items;
    const items = (detail && detail.items) || [];
    const done = total - (counts.Pending || 0);
    const t = q.trim().toLowerCase();
    const rows = items.filter((i) => (show === 'all' || i.state === show) && (!t || `${i.asset_name} ${i.unit_tag || ''} ${i.expected_location || ''}`.toLowerCase().includes(t)));
    const open = detail && detail.status !== 'Completed';
    return (
      <>
        <section className="rs-card as-audit-h">
          <button type="button" className="rs-icon-btn" onClick={() => { setActive(null); setDetail(null); }} aria-label="Back to audits"><i className="fas fa-arrow-left" aria-hidden="true" /></button>
          <div><b>{active.name}</b><small>{detail ? detail.status : active.status} · {done} of {total} checked</small><Meter value={done} max={total} /></div>
          {detail && detail.status === 'Draft' && can && <button type="button" className="rs-btn primary" onClick={() => act(active.start_url, 'Audit started.')}><i className="fas fa-play" aria-hidden="true" /> Start</button>}
          {detail && detail.status === 'In Progress' && can && <button type="button" className="rs-btn success" onClick={async () => { if (await confirm(`Complete the audit? ${counts.Pending || 0} unchecked item(s) will be marked Missing.`)) act(active.complete_url, 'Audit completed.'); }}><i className="fas fa-flag-checkered" aria-hidden="true" /><span className="rs-hide-sm">Complete</span></button>}
        </section>
        <Tiles items={['Verified', 'Missing', 'Damaged', 'Wrong Location'].map((k) => ({ label: k, value: counts[k] || 0, tone: k === 'Verified' ? 'good' : (counts[k] ? (k === 'Missing' ? 'bad' : 'mid') : '') }))} />
        <div className="rs-toolbar">
          <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><input type="search" placeholder="Find an item or location" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find" /></label>
          <Seg label="Show" value={show} onChange={setShow} options={[{ value: 'Pending', label: 'To check', count: counts.Pending || 0 }, { value: 'Missing', label: 'Missing', count: counts.Missing || null }, { value: 'all', label: 'All' }]} />
        </div>
        {!detail ? <p className="rs-muted">Loading items…</p> : rows.length ? (
          <section className="rs-card flush"><div className="as-checks">
            {rows.map((i) => (
              <div key={i.id} className={'as-check ' + (AU_TONE[i.state] || '')}>
                <span className="n"><b>{i.asset_name}{i.unit_tag ? ` · ${i.unit_tag}` : ''}</b>
                  <small>{i.expected_location ? `Expected in ${i.expected_location}` : 'No expected location'}{i.found_location && i.found_location !== i.expected_location ? ` · found in ${i.found_location}` : ''}{i.note ? ` · ${i.note}` : ''}</small></span>
                {open && can && i.state === 'Pending' ? (
                  <span className="as-mark">
                    <button type="button" className="ok" onClick={() => mark(i, 'Verified')}><i className="fas fa-check" aria-hidden="true" /><span>Found</span></button>
                    <button type="button" className="warn" onClick={() => mark(i, 'Damaged', { note: 'Reported damaged during audit' })}><i className="fas fa-triangle-exclamation" aria-hidden="true" /><span>Damaged</span></button>
                    <button type="button" className="warn" onClick={() => wrongPlace(i)}><i className="fas fa-location-dot" aria-hidden="true" /><span>Elsewhere</span></button>
                    <button type="button" className="bad" onClick={() => mark(i, 'Missing')}><i className="fas fa-question" aria-hidden="true" /><span>Missing</span></button>
                  </span>
                ) : (
                  <span className="as-mark done"><Pill tone={AU_TONE[i.state]}>{i.state}</Pill>
                    {open && can && i.state !== 'Pending' && <button type="button" className="rs-link" onClick={() => mark(i, 'Pending')}>Undo</button>}</span>
                )}
              </div>
            ))}
          </div></section>
        ) : <Blank icon="fa-circle-check" title={show === 'Pending' ? 'Everything is checked' : 'Nothing here'}><p>{show === 'Pending' ? 'Complete the audit to lock in the results.' : 'No items match.'}</p></Blank>}
      </>
    );
  }
  return (
    <>
      <div className="as-row-h">
        <p className="rs-muted">Walk the school with a list of what should be where, and tick each item off.</p>
        {can && <button type="button" className="rs-btn primary" onClick={() => setCreating(true)}><i className="fas fa-plus" aria-hidden="true" /> New audit</button>}
      </div>
      {!audits ? <p className="rs-muted">Loading…</p> : audits.length ? (
        <div className="as-audits">
          {audits.map((a) => {
            const c = a.counts || {}; const done = a.total_items - (c.Pending || 0);
            return (
              <section key={a.id} className="rs-card as-audit">
                <header><b>{a.name}</b><Pill tone={AU_STATUS[a.status]}>{a.status}</Pill></header>
                <small>{a.category_filter || 'All categories'} · {a.total_items} items</small>
                <Meter value={done} max={a.total_items || 1} />
                <div className="as-audit-c">{Object.entries(c).filter(([, n]) => n).map(([k, n]) => <Pill key={k} tone={AU_TONE[k]}>{n} {k}</Pill>)}</div>
                <div className="as-audit-a">
                  <button type="button" className="rs-btn sm primary" onClick={() => loadDetail(a)}>{a.status === 'In Progress' ? 'Continue' : 'Open'}</button>
                  {a.status === 'Draft' && can && <button type="button" className="rs-btn sm ghost" onClick={() => act(a.start_url, 'Started.')}>Start</button>}
                  {can && <button type="button" className="rs-icon-btn" onClick={async () => { if (await confirm(`Delete audit "${a.name}"?`)) act(a.delete_url, 'Deleted.'); }} aria-label={`Delete ${a.name}`}><i className="fas fa-trash" aria-hidden="true" /></button>}
                </div>
              </section>
            );
          })}
        </div>
      ) : <Blank icon="fa-clipboard-check" title="No audits yet"><p>Create an audit to physically verify assets against the register.</p></Blank>}
      {creating && (
        <Sheet title="New asset audit" onClose={() => setCreating(false)}>
          <div className="sl-form">
            <label className="sl-f"><span>Name</span><input value={cf.name} onChange={(e) => setCf((x) => ({ ...x, name: e.target.value }))} placeholder="e.g. Third term ICT audit" autoFocus /></label>
            <label className="sl-f"><span>Category</span><select value={cf.category_filter} onChange={(e) => setCf((x) => ({ ...x, category_filter: e.target.value }))}><option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="sl-f"><span>Description</span><input value={cf.description} onChange={(e) => setCf((x) => ({ ...x, description: e.target.value }))} /></label>
            <button type="button" className="rs-btn primary wide" onClick={create}><i className="fas fa-clipboard-list" aria-hidden="true" /> Create the checklist</button>
          </div>
        </Sheet>
      )}
    </>
  );
}

// ── Analytics ──────────────────────────────────────────────────────────────
function Analytics({ d }) {
  const [f, setF] = useState({ category: '', section: '', class_id: '', status: '' });
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [brk, setBrk] = useState('category');
  useEffect(() => {
    let alive = true; setData(null);
    const p = new URLSearchParams(); Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, v); });
    apiGet(d.analytics_url + (p.toString() ? `?${p}` : '')).then((r) => { if (alive) setData(r); }).catch(() => { if (alive) setErr('Could not load analytics.'); });
    return () => { alive = false; };
  }, [f, d.analytics_url]);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const o = (data && data.overview) || {};
  const rows = data ? (data[`by_${brk}`] || []) : [];
  const delta = (now, then) => (then == null ? <span className="rs-muted">—</span> : <>{then}{now - then !== 0 && <small className={now - then > 0 ? 'good' : 'bad'}> {now - then > 0 ? '+' : ''}{now - then}</small>}</>);
  return (
    <>
      <div className="rs-toolbar">
        <select className="sl-select" value={f.category} onChange={(e) => set('category', e.target.value)} aria-label="Category"><option value="">All categories</option>{d.categories.map((c) => <option key={c}>{c}</option>)}</select>
        <select className="sl-select" value={f.status} onChange={(e) => set('status', e.target.value)} aria-label="Status"><option value="">All statuses</option>{d.statuses.map((x) => <option key={x}>{x}</option>)}</select>
        <select className="sl-select" value={f.section} onChange={(e) => set('section', e.target.value)} aria-label="Section"><option value="">All sections</option>{d.sections.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</select>
        <select className="sl-select" value={f.class_id} onChange={(e) => set('class_id', e.target.value)} aria-label="Class"><option value="">All classes</option>{(d.classes || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      </div>
      {err ? <p className="bad">{err}</p> : !data ? <p className="rs-muted">Loading analytics…</p> : (<>
        <Tiles items={[
          { label: 'Units', value: o.quantity || 0, sub: plural(o.count || 0, 'asset record') },
          { label: 'Book value', value: short(o.total_book || 0), sub: `cost ${short(o.total_cost || 0)}` },
          { label: 'Disposed units', value: o.disposed_units || 0 },
          { label: 'Not placed', value: o.unassigned_placement || 0, sub: 'no class, teacher or section', tone: o.unassigned_placement ? 'mid' : '' },
        ]} />
        <div className="an-grid two">
          <section className="rs-card">
            <header className="rs-card-h"><h3><i className="fas fa-chart-bar" aria-hidden="true" /> Where the units are</h3></header>
            <Seg label="Group by" value={brk} onChange={setBrk} options={[{ value: 'category', label: 'Category' }, { value: 'status', label: 'Status' }, { value: 'section', label: 'Section' }, { value: 'class', label: 'Class' }, { value: 'teacher', label: 'Teacher' }]} />
            <div style={{ marginTop: '.8rem' }}><Bars rows={rows} label={(r) => r.label} value={(r) => r.quantity} fmt={(v) => plural(v, 'unit')} sub={(r) => plural(r.count, 'record')} /></div>
          </section>
          <section className="rs-card flush">
            <header className="rs-card-h pad"><h3><i className="fas fa-scale-balanced" aria-hidden="true" /> Change over time</h3></header>
            <div className="sl-tbl-wrap"><table className="sl-tbl">
              <thead><tr><th>Category</th><th className="r">Now</th><th className="r">7 days ago</th>
                <th className="r">{(data.comparison[0] && data.comparison[0].last_term_label) || 'Last term'}</th>
                <th className="r">{(data.comparison[0] && data.comparison[0].last_session_label) || 'Last session'}</th></tr></thead>
              <tbody>{(data.comparison || []).map((r) => (
                <tr key={r.category} className={r.category === 'Total' ? 'tot' : ''}><td className={r.category === 'Total' ? 'main' : ''}>{r.category}</td><td className="r"><b>{r.now}</b></td>
                  <td className="r">{delta(r.now, r.last_week)}</td><td className="r">{delta(r.now, r.last_term)}</td><td className="r">{delta(r.now, r.last_session)}</td></tr>
              ))}</tbody></table></div>
          </section>
        </div>
      </>)}
    </>
  );
}

// ── History (as-of snapshots + term comparison) ────────────────────────────
function Snapshots({ d }) {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);
  const [snap, setSnap] = useState(null);
  const [terms, setTerms] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let alive = true; setSnap(null);
    apiGet(`${d.snapshot_url}?date=${date}`).then((r) => { if (alive) setSnap(r); }).catch(() => { if (alive) setErr('Could not load the snapshot.'); });
    return () => { alive = false; };
  }, [date, d.snapshot_url]);
  useEffect(() => { apiGet(d.snapshot_terms_url).then(setTerms).catch(() => setTerms({ ok: false, error: 'Could not load the term comparison.' })); }, [d.snapshot_terms_url]);
  return (
    <>
      <div className="rs-toolbar as-date">
        <label className="sl-f"><span>Show the register as it was on</span><input type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <p className="rs-muted">Rebuilt from each asset’s history, so it shows exactly what was known that day.</p>
      </div>
      {err ? <p className="bad">{err}</p> : !snap ? <p className="rs-muted">Loading…</p> : (<>
        <Tiles items={[
          { label: 'Asset records', value: snap.overview.asset_records || 0 },
          { label: 'Units', value: snap.overview.total_units || 0 },
          ...Object.entries(snap.overview.by_status || {}).slice(0, 3).map(([k, v]) => ({ label: k, value: v, tone: ST_TONE[k] === 'bad' ? 'bad' : '' })),
        ]} />
        <div className="an-grid two">
          <section className="rs-card"><header className="rs-card-h"><h3><i className="fas fa-tags" aria-hidden="true" /> By category</h3></header>
            <Bars rows={snap.by_category || []} label={(r) => r.label} value={(r) => r.quantity} fmt={(v) => plural(v, 'unit')} /></section>
          <section className="rs-card"><header className="rs-card-h"><h3><i className="fas fa-layer-group" aria-hidden="true" /> By section</h3></header>
            <Bars rows={snap.by_section || []} label={(r) => r.label} value={(r) => r.quantity} fmt={(v) => plural(v, 'unit')} /></section>
        </div>
      </>)}
      <section className="rs-card flush">
        <header className="rs-card-h pad"><h3><i className="fas fa-table-columns" aria-hidden="true" /> Units by status, term by term</h3></header>
        {!terms ? <p className="rs-muted rs-pad">Loading…</p> : !terms.ok ? <p className="rs-muted rs-pad">{terms.error}</p> : (
          <div className="sl-tbl-wrap"><table className="sl-tbl">
            <thead><tr><th>Status</th>{terms.columns.map((c) => <th key={c.term} className="r">{c.term}</th>)}</tr></thead>
            <tbody>
              {terms.statuses.map((st) => <tr key={st}><td>{st}</td>{terms.columns.map((c) => <td key={c.term} className="r">{c.totals[st] || 0}</td>)}</tr>)}
              <tr className="tot"><td className="main">Total</td>{terms.columns.map((c) => <td key={c.term} className="r"><b>{c.total_units}</b></td>)}</tr>
            </tbody></table></div>
        )}
      </section>
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Dialogs (unchanged)
// ═══════════════════════════════════════════════════════════════════════════
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

