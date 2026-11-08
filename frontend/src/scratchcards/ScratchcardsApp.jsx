import React, { useState } from 'react';
import { useSave } from '../lib/forms';
import { useSection, NavCtx, useNav } from '../lib/section';
import { Banner, SectionShell, confirm } from '../components/ui';
import { Head, Tiles, Seg, Menu, Sheet, Blank, Bar, Meter, usePhone } from '../subjects/results';

const A = ({ to, className, children, title }) => {
  const nav = useNav();
  return <a href={to} className={className} title={title}
    onClick={(e) => { e.preventDefault(); nav.go(to); }}>{children}</a>;
};

function copy(text, notify) {
  try { navigator.clipboard.writeText(text).then(() => notify('success', `Copied ${text}`)); } catch (e) { /* no clipboard */ }
}

// ---- Generate sheet ---------------------------------------------------------
function Generate({ d, save, nav, onClose }) {
  const current = d.terms.find((t) => t.is_current);
  const [gen, setGen] = useState({ count: 50, max_uses: 5, term_id: current ? String(current.id) : '', batch_label: '' });
  const set = (k, v) => setGen((g) => ({ ...g, [k]: v }));
  const n = Math.max(0, parseInt(gen.count, 10) || 0); const u = Math.max(0, parseInt(gen.max_uses, 10) || 0);
  const submit = (e) => { e.preventDefault(); save(d.generate_url, gen, (r) => { onClose(); if (r.redirect) nav.go(r.redirect); }); };
  return (
    <Sheet title="Generate scratch cards" onClose={onClose}>
      <form onSubmit={submit} className="sc-form">
        <label className="sc-f"><span>How many cards</span>
          <input type="number" inputMode="numeric" min="1" max="500" value={gen.count} onChange={(e) => set('count', e.target.value)} />
          <span className="rs-chips">{[20, 50, 100, 200].map((x) => (
            <button type="button" key={x} className={'rs-chip' + (String(x) === String(gen.count) ? ' on' : '')} onClick={() => set('count', x)}>{x}</button>))}</span></label>
        <label className="sc-f"><span>Checks per card</span>
          <input type="number" inputMode="numeric" min="1" max="100" value={gen.max_uses} onChange={(e) => set('max_uses', e.target.value)} />
          <small>How many times a parent can check results with one card.</small></label>
        <label className="sc-f"><span>Works for</span>
          <select value={gen.term_id} onChange={(e) => set('term_id', e.target.value)}>
            <option value="">Any term</option>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_current ? ' (current)' : ''}</option>)}</select></label>
        <label className="sc-f"><span>Batch name <em>(optional)</em></span>
          <input type="text" value={gen.batch_label} onChange={(e) => set('batch_label', e.target.value)} placeholder="e.g. Third term sales" maxLength={60} /></label>
        <p className="sc-sum"><i className="fas fa-ticket" aria-hidden="true" /> {n} card{n === 1 ? '' : 's'} · {n * u} result checks in total</p>
        <button type="submit" className="rs-btn primary wide"><i className="fas fa-print" aria-hidden="true" /> Generate &amp; print</button>
      </form>
    </Sheet>
  );
}

// ---- Delete-by-rule sheet ---------------------------------------------------
function RuleDelete({ d, save, nav, onClose, clear }) {
  const [limit, setLimit] = useState(200);
  const scope = d.batch ? `batch “${d.batch}”` : 'all batches';
  const what = d.status ? `${d.status} cards` : 'cards';
  const go = async () => {
    if (!await confirm(`Delete up to ${limit} ${what} in ${scope}, oldest first? This can't be undone.`)) return;
    save(d.bulk_delete_url, { batch: d.batch || '', status: d.status || '', limit: String(limit) }, () => { clear(); onClose(); nav.refresh(); });
  };
  return (
    <Sheet title="Delete matching cards" onClose={onClose}>
      <p className="sc-note">Deletes <b>{what}</b> in <b>{scope}</b> (your current filters), oldest first. The check log is kept.</p>
      <label className="sc-f"><span>At most</span>
        <input type="number" min="1" max="100000" value={limit} onChange={(e) => setLimit(e.target.value)} /></label>
      <button type="button" className="rs-btn danger wide" onClick={go}><i className="fas fa-trash" aria-hidden="true" /> Delete matching cards</button>
    </Sheet>
  );
}

// ---- Index ------------------------------------------------------------------
function Index({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const save = useSave(notify);
  const [sheet, setSheet] = useState(null);
  const [sel, setSel] = useState(() => new Set());
  const cards = d.cards;
  const st = d.stats;
  const pg = d.pg || { page: 1, pages: 1, total: cards.length, per_page: 50, has_prev: false, has_next: false };
  const listUrl = (over) => {
    const p = { batch: d.batch || '', status: d.status || '', page: pg.page, per_page: pg.per_page, ...over };
    const qs = Object.entries(p).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    return qs ? `${d.self_url}?${qs}` : d.self_url;
  };
  const goList = (over) => { setSel(new Set()); nav.go(listUrl(over)); };
  const publish = (t) => save(t.publish_url, {}, () => nav.refresh());
  const toggle = (c) => save(c.toggle_url, {}, () => nav.refresh());
  const allOnPage = cards.length > 0 && cards.every((c) => sel.has(c.id));
  const toggleSel = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const toggleAll = () => setSel(() => (allOnPage ? new Set() : new Set(cards.map((c) => c.id))));
  const bulkToggle = (active) => save(d.bulk_toggle_url, { ids: Array.from(sel).join(','), active: active ? '1' : '0' }, () => { setSel(new Set()); nav.refresh(); });
  const bulkDelete = async () => {
    if (!await confirm(`Delete ${sel.size} selected card(s)? This can't be undone.`)) return;
    save(d.bulk_delete_url, { ids: Array.from(sel).join(',') }, () => { setSel(new Set()); nav.refresh(); });
  };
  const usedPct = st.capacity ? Math.round((st.used / st.capacity) * 100) : 0;
  const statusOpts = [{ value: '', label: 'All' }, { value: 'unused', label: 'Unused' }, { value: 'used', label: 'Used' },
    { value: 'active', label: 'Active' }, { value: 'disabled', label: 'Disabled' }];
  const current = d.terms.find((t) => t.is_current);

  const release = (
    <section className="rs-card">
      <header className="rs-card-h"><h3><i className="fas fa-unlock" aria-hidden="true" /> Release results</h3><small>Parents can only check a released term</small></header>
      <div className="sc-terms">
        {d.terms.map((t) => (
          <div key={t.id} className={'sc-term' + (t.results_published ? ' on' : '')}>
            <span className="n"><b>{t.name}</b><small>{t.results_published ? 'Released — visible on the checker' : 'Hidden from parents'}{t.is_current ? ' · current term' : ''}</small></span>
            <button type="button" role="switch" aria-checked={t.results_published} aria-label={`${t.results_published ? 'Hide' : 'Release'} ${t.name}`}
                    className={'sc-switch' + (t.results_published ? ' on' : '')} onClick={() => publish(t)}><i /></button>
          </div>
        ))}
      </div>
    </section>
  );
  const batches = d.batch_summary && d.batch_summary.length > 0 && (
    <section className="rs-card">
      <header className="rs-card-h"><h3><i className="fas fa-layer-group" aria-hidden="true" /> Batches</h3><small>Tap one to see its cards</small></header>
      <div className="sc-batches">
        {d.batch_summary.map((b) => (
          <button type="button" key={b.label || '_'} className={'sc-batch' + ((d.batch || '') === b.label ? ' on' : '')} onClick={() => b.label && goList({ batch: b.label, page: 1 })} disabled={!b.label}>
            <span className="n"><b>{b.label || 'No batch name'}</b><small>{b.cards} cards · {b.unused} unused · {b.created}</small></span>
            <Meter value={b.checks} max={b.capacity} tone={b.capacity && b.checks / b.capacity > 0.8 ? 'bad' : 'n'} />
            <small className="c">{b.checks}/{b.capacity}</small>
          </button>
        ))}
      </div>
    </section>
  );
  const recent = d.recent && d.recent.length > 0 && (
    <section className="rs-card">
      <header className="rs-card-h"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Latest checks</h3>
        <A to={d.logs_url} className="rs-link">See all</A></header>
      <div className="sc-recent">
        {d.recent.map((r, i) => (
          <div key={i} className="sc-log">
            <span className={'sc-dot ' + (r.success ? 'ok' : 'bad')}><i className={'fas ' + (r.success ? 'fa-check' : 'fa-xmark')} aria-hidden="true" /></span>
            <span className="n"><b>{r.student || 'Unknown student'}</b><small>{r.success ? r.card : (r.detail || 'Failed')}</small></span>
            <small className="w">{r.when}</small>
          </div>
        ))}
      </div>
    </section>
  );

  return (
    <div className={'rs' + (phone && sel.size ? ' has-bar' : '')}>
      <Head icon="fa-ticket" title="Scratch cards" sub="PINs parents use to check results online">
        <button type="button" className="rs-btn primary" onClick={() => setSheet('gen')}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm">Generate cards</span></button>
        <Menu label="More" items={[
          { icon: 'fa-list-check', label: 'Result check log', onClick: () => nav.go(d.logs_url) },
          d.print_batch_url && { icon: 'fa-print', label: `Print batch “${d.batch}”`, href: d.print_batch_url, native: true },
          { icon: 'fa-trash', label: 'Delete matching cards…', onClick: () => setSheet('rule'), danger: true },
        ]} />
      </Head>

      <Tiles items={[
        { label: 'Ready to sell', value: st.unused, sub: 'active, never used', tone: st.unused < 20 ? 'mid' : 'good' },
        { label: 'Checks used', value: st.used, sub: `${usedPct}% of ${st.capacity}` },
        { label: 'Used up', value: st.exhausted, sub: `of ${st.total} cards` },
        { label: 'Checks this week', value: st.checks_7d, sub: st.failed_7d ? `${st.failed_7d} failed attempts` : 'no failed attempts', tone: st.failed_7d > st.checks_7d && st.failed_7d > 5 ? 'bad' : '' },
      ]} />
      {current && !current.results_published && (
        <div className="sc-alert"><i className="fas fa-eye-slash" aria-hidden="true" /><span><b>{current.name}</b> isn’t released yet, so parents can’t check results with their cards.</span>
          <button type="button" className="rs-btn sm success" onClick={() => publish(current)}>Release now</button></div>
      )}
      {st.failed_7d > 10 && st.failed_7d > st.checks_7d && (
        <div className="sc-alert bad"><i className="fas fa-shield-halved" aria-hidden="true" /><span>More failed checks than successful ones this week — someone may be guessing PINs. Review the log.</span>
          <A to={d.logs_url} className="rs-btn sm ghost">Open log</A></div>
      )}

      <div className="rs-split">
        <div className="rs-main">
          {phone && release}
          <section className="rs-card flush">
            <div className="sc-tools">
              <select value={d.batch || ''} onChange={(e) => goList({ batch: e.target.value, page: 1 })} aria-label="Batch">
                <option value="">All batches</option>
                {d.batches.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
              <Seg label="Status" value={d.status || ''} onChange={(v) => goList({ status: v, page: 1 })} options={statusOpts} />
              <span className="sc-count">{pg.total} card{pg.total === 1 ? '' : 's'}</span>
            </div>
            {cards.length ? (<>
              <div className="sc-head">
                <label className="rs-check"><input type="checkbox" checked={allOnPage} onChange={toggleAll} /> Select page</label>
              </div>
              <div className="sc-list">
                {cards.map((c) => (
                  <div key={c.id} className={'sc-card' + (sel.has(c.id) ? ' sel' : '') + (c.is_active ? '' : ' off')}>
                    <input type="checkbox" checked={sel.has(c.id)} onChange={() => toggleSel(c.id)} aria-label={`Select ${c.serial}`} />
                    <span className="sc-id"><b>{c.serial}</b>
                      <button type="button" className="sc-pin" onClick={() => copy(c.pin, notify)} title="Copy PIN"><code>{c.pin}</code><i className="fas fa-copy" aria-hidden="true" /></button></span>
                    <span className="sc-uses"><Meter value={c.used_count} max={c.max_uses} tone={c.uses_left === 0 ? 'bad' : c.used_count ? 'mid' : 'good'} />
                      <small>{c.used_count}/{c.max_uses} used{c.uses_left === 0 ? ' · used up' : ''}</small></span>
                    <span className="sc-meta"><small>{c.term_name === 'Any' ? 'Any term' : c.term_name}</small><small>{c.batch_label !== '—' ? c.batch_label : 'No batch'}</small>{c.student_name && <small className="lock"><i className="fas fa-lock" aria-hidden="true" /> {c.student_name}</small>}</span>
                    <button type="button" role="switch" aria-checked={c.is_active} aria-label={`${c.is_active ? 'Disable' : 'Enable'} ${c.serial}`}
                            className={'sc-switch' + (c.is_active ? ' on' : '')} onClick={() => toggle(c)} title={c.is_active ? 'Active — tap to disable' : 'Disabled — tap to enable'}><i /></button>
                  </div>
                ))}
              </div>
            </>) : <Blank icon="fa-ticket" title="No cards here"><p>{d.batch || d.status ? 'No cards match these filters.' : 'Generate your first batch of scratch cards to sell to parents.'}</p>
              {!d.batch && !d.status && <button type="button" className="rs-btn primary" onClick={() => setSheet('gen')}><i className="fas fa-plus" aria-hidden="true" /> Generate cards</button>}</Blank>}
            {pg.pages > 1 && (
              <div className="sc-pager">
                <span>Page {pg.page} of {pg.pages}</span>
                <select value={pg.per_page} onChange={(e) => goList({ per_page: e.target.value, page: 1 })} aria-label="Cards per page">
                  {[50, 100, 200].map((n) => <option key={n} value={n}>{n} per page</option>)}</select>
                <button type="button" className="rs-icon-btn" disabled={!pg.has_prev} onClick={() => goList({ page: pg.page - 1 })} aria-label="Previous page"><i className="fas fa-chevron-left" aria-hidden="true" /></button>
                <button type="button" className="rs-icon-btn" disabled={!pg.has_next} onClick={() => goList({ page: pg.page + 1 })} aria-label="Next page"><i className="fas fa-chevron-right" aria-hidden="true" /></button>
              </div>
            )}
            {sel.size > 0 && (
              <Bar>
                <span className="rs-bar-t"><b>{sel.size} selected</b><small><button type="button" className="rs-link" onClick={() => setSel(new Set())}>Clear</button></small></span>
                <button type="button" className="rs-btn ghost" onClick={() => bulkToggle(true)}>Enable</button>
                <button type="button" className="rs-btn ghost" onClick={() => bulkToggle(false)}>Disable</button>
                <button type="button" className="rs-btn danger" onClick={bulkDelete} aria-label="Delete selected"><i className="fas fa-trash" aria-hidden="true" /><span className="rs-hide-sm">Delete</span></button>
              </Bar>
            )}
          </section>
          {phone && batches}
          {phone && recent}
        </div>
        {!phone && <aside className="rs-rail">{release}{batches}{recent}</aside>}
      </div>
      {sheet === 'gen' && <Generate d={d} save={save} nav={nav} onClose={() => setSheet(null)} />}
      {sheet === 'rule' && <RuleDelete d={d} save={save} nav={nav} onClose={() => setSheet(null)} clear={() => setSel(new Set())} />}
    </div>
  );
}

// ---- Logs -------------------------------------------------------------------
function Logs({ d }) {
  const [show, setShow] = useState('all');
  const [q, setQ] = useState('');
  const ok = d.rows.filter((r) => r.success).length;
  const t = q.trim().toLowerCase();
  const rows = d.rows.filter((r) => (show === 'all' || (show === 'ok' ? r.success : !r.success))
    && (!t || [r.student, r.card, r.ip, r.detail].join(' ').toLowerCase().includes(t)));
  return (
    <div className="rs">
      <Head icon="fa-list-check" title="Result check log" sub="Every attempt on the public result checker (latest 500)">
        <A to={d.index_url} className="rs-btn ghost"><i className="fas fa-arrow-left" aria-hidden="true" /><span className="rs-hide-sm">Scratch cards</span></A>
      </Head>
      <Tiles items={[
        { label: 'Attempts', value: d.rows.length },
        { label: 'Successful', value: ok, tone: 'good' },
        { label: 'Failed', value: d.rows.length - ok, tone: d.rows.length - ok ? 'bad' : '' },
      ]} />
      <div className="rs-toolbar">
        <label className="rs-search"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input type="search" placeholder="Student, card, IP…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the log" /></label>
        <Seg label="Show" value={show} onChange={setShow} options={[{ value: 'all', label: 'All' }, { value: 'ok', label: 'Successful' }, { value: 'fail', label: 'Failed' }]} />
      </div>
      {rows.length ? (
        <section className="rs-card flush">
          <div className="sc-loglist">
            {rows.map((r, i) => (
              <div key={i} className="sc-log big">
                <span className={'sc-dot ' + (r.success ? 'ok' : 'bad')}><i className={'fas ' + (r.success ? 'fa-check' : 'fa-xmark')} aria-hidden="true" /></span>
                <span className="n"><b>{r.student !== '—' ? r.student : 'Unknown student'}</b>
                  <small>{[r.term !== '—' && r.term, r.card !== '—' && `card ${r.card}`, r.detail].filter(Boolean).join(' · ')}</small></span>
                <span className="w"><small>{r.when}</small>{r.ip && <small className="ip">{r.ip}</small>}</span>
              </div>
            ))}
          </div>
        </section>
      ) : <Blank icon="fa-list-check" title={d.rows.length ? 'Nothing matches' : 'No checks yet'}><p>{d.rows.length ? 'Try a different search or filter.' : 'Checks appear here once parents start using their cards.'}</p></Blank>}
    </div>
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
