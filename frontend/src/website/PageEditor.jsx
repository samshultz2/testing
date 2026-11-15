// Page editor: an outline of sections beside the selected section's editor on
// laptops; on phones the outline is a list and a section opens full screen,
// with Save docked at the bottom.
import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { confirm } from '../components/ui';
import { Sheet, Menu, usePhone, useMedia } from '../subjects/results';
import { useWs, postJson, submitJson, Switch, Field, AutoText, useLeaveGuard } from './kit';
import { FieldEditor } from './Fields';

const pick = (b) => ({ props: b.props, variant: b.variant, enabled: b.enabled });

export function PageEditor() {
  const { d, setData, notify, write, go } = useWs();
  const phone = usePhone();
  const wide = useMedia('(min-width: 980px)');
  const [sel, setSel] = useState(wide ? (d.blocks.length > 1 ? 1 : 0) : null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState('');
  const blocks = d.blocks;
  const cur = sel != null ? blocks[sel] : null;
  const base = cur ? pick(cur) : null;
  const edit = draft || base;
  const dirty = !!(draft && base && JSON.stringify(draft) !== JSON.stringify(base));
  useLeaveGuard(dirty);

  const apply = (r, keepSel) => {
    if (r.page) setData({ ...d, ...r.page });
    if (r.selected != null && !keepSel) setSel(r.selected);
    setDraft(null);
  };
  const leaveOk = async () => !dirty || confirm({ title: 'Discard changes?', message: `Your changes to “${cur.label}” haven’t been saved.`, confirmText: 'Discard', tone: 'danger' });
  const choose = async (i) => {
    if (i === sel) return;
    if (!(await leaveOk())) return;
    setDraft(null); setSel(i);
    if (!wide) window.scrollTo(0, 0);
  };
  const save = async () => {
    if (!dirty) return true;
    setBusy(true);
    const r = await postJson(`${d.urls.base}/block/${sel}/save`, { ...draft, expect: cur.type });
    setBusy(false);
    if (r.ok) { apply(r, true); notify('ok', 'Saved — it’s on your ' + (d.published ? 'live site.' : 'draft site.')); return true; }
    if (r.stale) apply(r);
    notify('error', r.error || 'Could not save.');
    return false;
  };
  const op = async (i, name, extra) => {
    if (i === sel && dirty && !(await save())) return;
    if (name === 'delete' && !(await confirm({ title: `Remove “${blocks[i].label}”?`, message: 'This section and its content will be removed from the page.', confirmText: 'Remove', tone: 'danger' }))) return;
    const r = await submitJson(`${d.urls.base}/block/${i}/op`, { op: name, expect: blocks[i].type, ...(extra || {}) });
    if (r.page) { setData({ ...d, ...r.page }); setDraft(null); if (r.selected != null) setSel(name === 'delete' && !wide ? null : r.selected); }
    if (r.ok) notify('ok', r.message); else notify('error', r.error || 'Could not do that.');
  };
  const add = async (type) => {
    if (dirty && !(await save())) return;
    setSheet('');
    const r = await submitJson(d.urls.add, { type });
    if (r.ok) { apply(r); notify('ok', r.message); window.scrollTo(0, 0); } else notify('error', r.error || 'Could not add.');
  };
  const back = async () => { if (await leaveOk()) { setDraft(null); setSel(null); window.scrollTo(0, 0); } };
  const setEdit = (patch) => setDraft({ ...edit, ...patch });

  const links = 'ws-links-' + d.pg.id;
  const showOutline = wide || sel == null;
  const showEditor = cur && (wide || sel != null);

  return (
    <div className={'ws-ed' + (wide ? ' wide' : '')}>
      <datalist id={links}>
        <option value="/site/apply">Application form</option>
        <option value="/site/">Home page</option>
        {(d.pages_for_links || []).map((p) => <option key={p.address} value={p.address}>{p.title}</option>)}
      </datalist>
      {showOutline && (
        <header className="ws-ed-h">
          <a className="ws-back" href={d.nav.home} aria-label="All pages"><i className="fas fa-chevron-left" aria-hidden="true" /><span>Pages</span></a>
          <div className="ws-ed-t">
            <h1>{d.pg.title}</h1>
            <p>{d.pg.address}{!d.pg.published && <em className="warn">Hidden</em>}</p>
          </div>
          <div className="ws-ed-a">
            <button type="button" className="rs-btn" onClick={() => setSheet('preview')}><i className="fas fa-eye" aria-hidden="true" /><span className="rs-hide-sm">Preview</span></button>
            {write && <button type="button" className="rs-btn ghost" onClick={() => setSheet('settings')} aria-label="Page settings"><i className="fas fa-gear" aria-hidden="true" /><span className="rs-hide-sm">Settings</span></button>}
          </div>
        </header>
      )}
      <div className="ws-ed-body">
        {showOutline && (
          <aside className="ws-outline" aria-label="Sections">
            <div className="ws-outline-h"><span>Sections</span><em>{blocks.length}</em></div>
            <ol>
              {blocks.map((b, i) => (
                <li key={i}>
                  <button type="button" className={'ws-sec' + (i === sel ? ' on' : '') + (b.enabled ? '' : ' off')} onClick={() => choose(i)} aria-current={i === sel ? 'true' : undefined}>
                    <span className="ws-sec-ic"><i className={'fas ' + b.icon} aria-hidden="true" /></span>
                    <span className="ws-sec-t"><b>{b.label}</b><small>{b.enabled ? (b.summary || b.desc) : 'Hidden from visitors'}</small></span>
                    {!b.enabled && <i className="fas fa-eye-slash ws-sec-off" aria-hidden="true" />}
                    {i === sel && dirty && <span className="ws-sec-dot" title="Unsaved changes" />}
                    {!wide && <i className="fas fa-chevron-right ws-chev" aria-hidden="true" />}
                  </button>
                </li>
              ))}
            </ol>
            {write && <button type="button" className="ws-add-sec" onClick={() => setSheet('add')}><i className="fas fa-plus" aria-hidden="true" />Add a section</button>}
          </aside>
        )}
        {showEditor && (
          <section className="ws-editor" aria-label={cur.label}>
            <div className="ws-editor-h">
              {!wide && <button type="button" className="ws-back" onClick={back}><i className="fas fa-chevron-left" aria-hidden="true" /><span>Sections</span></button>}
              <span className="ws-editor-ic"><i className={'fas ' + cur.icon} aria-hidden="true" /></span>
              <div className="ws-editor-t"><h2>{cur.label}</h2><p>{cur.desc}</p></div>
              {write && (
                <div className="ws-editor-a">
                  <button type="button" className="rs-btn sm ghost" disabled={sel === 0} onClick={() => op(sel, 'up')} aria-label="Move up"><i className="fas fa-arrow-up" aria-hidden="true" /></button>
                  <button type="button" className="rs-btn sm ghost" disabled={sel === blocks.length - 1} onClick={() => op(sel, 'down')} aria-label="Move down"><i className="fas fa-arrow-down" aria-hidden="true" /></button>
                  <Menu label="More" items={[
                    { icon: 'fa-clone', label: 'Duplicate section', onClick: () => op(sel, 'duplicate') },
                    { icon: 'fa-trash-can', label: 'Remove section', danger: true, onClick: () => op(sel, 'delete') },
                  ]} />
                </div>
              )}
            </div>
            <div className="ws-editor-b">
              {write && <Switch on={edit.enabled} onChange={(v) => setEdit({ enabled: v })} label="Show on the website" sub={edit.enabled ? 'Visitors can see this section' : 'Hidden — kept here for later'} />}
              {cur.variants.length > 1 && (
                <div className="ws-field">
                  <span className="ws-field-l">Design</span>
                  <div className="ws-variants" role="radiogroup" aria-label="Design">
                    {cur.variants.map((v) => (
                      <button type="button" key={v.value} role="radio" aria-checked={v.value === edit.variant} disabled={!write}
                              className={'ws-var' + (v.value === edit.variant ? ' on' : '')} onClick={() => setEdit({ variant: v.value })}>
                        <VariantArt type={cur.type} v={v.value} /><span>{v.label}</span></button>
                    ))}
                  </div>
                </div>
              )}
              {cur.note && <p className="ws-note"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" />{cur.note}</p>}
              {cur.ai && write && <button type="button" className="ws-ai" onClick={() => setSheet('ai')}><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /><span><b>Write with AI</b><small>Get a first draft of the words — you check it before saving.</small></span><i className="fas fa-chevron-right" aria-hidden="true" /></button>}
              <fieldset disabled={!write} className="ws-fields">
                {cur.fields.map((f) => (
                  <FieldEditor key={f.key} f={f} links={links} value={edit.props[f.key]}
                               onChange={(v) => setEdit({ props: { ...edit.props, [f.key]: v } })}
                               onImage={(key) => {
                                 const shows = (cur.image_variants || {})[key] || [];
                                 if (shows.length && !shows.includes(edit.variant)) {
                                   setDraft((x) => ({ ...(x || edit), variant: shows[0] }));
                                   notify('ok', 'Switched to a design that shows this picture.');
                                 }
                               }} />
                ))}
                {!cur.fields.length && !cur.note && <p className="rs-muted">Nothing to fill in for this section.</p>}
              </fieldset>
            </div>
            {write && (
              <SaveBar phone={phone} dirty={dirty} busy={busy} onSave={save} onUndo={() => setDraft(null)} />
            )}
          </section>
        )}
        {wide && !cur && <section className="ws-editor ws-editor-empty"><p>Choose a section on the left to edit it.</p></section>}
      </div>
      {sheet === 'add' && <AddSheet catalogue={d.catalogue} onClose={() => setSheet('')} onPick={add} />}
      {sheet === 'settings' && <SettingsSheet onClose={() => setSheet('')} />}
      {sheet === 'preview' && <PreviewSheet url={d.public_url} dirty={dirty} onClose={() => setSheet('')} />}
      {sheet === 'ai' && cur && <AiSheet idx={sel} block={cur} onClose={() => setSheet('')}
        onDraft={(s) => { setDraft({ ...edit, props: { ...edit.props, ...s } }); setSheet(''); }} />}
    </div>
  );
}

function SaveBar({ phone, dirty, busy, onSave, onUndo }) {
  if (phone && !dirty) return null;
  // On phones the bar is fixed to the screen bottom; portalled to <body> so a
  // transformed page wrapper can't trap it (it then sat under the content).
  const bar = (
    <div className={'ws-save' + (phone ? ' fixed' : '') + (dirty ? ' dirty' : '')}>
      <span className="ws-save-t">{dirty ? <><span className="ws-sec-dot" aria-hidden="true" />Unsaved changes</> : <><i className="fas fa-check" aria-hidden="true" />All changes saved</>}</span>
      {dirty && <button type="button" className="rs-btn ghost sm" onClick={onUndo} disabled={busy}>Undo</button>}
      <button type="button" className="rs-btn primary sm" disabled={!dirty || busy} onClick={onSave}>
        <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" />{busy ? 'Saving…' : 'Save'}</button>
    </div>
  );
  return phone ? createPortal(bar, document.body) : bar;
}

// Tiny wireframes so a design can be recognised without reading its name.
function VariantArt({ v }) {
  const k = v || '';
  let cls = 'c';
  if (/split|left|right|alternating|two-col/.test(k)) cls = 's';
  if (/right/.test(k)) cls = 'r';
  if (/grid|cards|three|boxed|masonry|showcase/.test(k)) cls = 'g';
  if (/list|stacked|timeline|accordion|table/.test(k)) cls = 'l';
  if (/bg|image$|gradient|band|dark/.test(k)) cls = 'f';
  if (/slider/.test(k)) cls = 'f sl';
  return <span className={'ws-art ' + cls} aria-hidden="true"><i /><i /><i /></span>;
}

function AddSheet({ catalogue, onClose, onPick }) {
  const [q, setQ] = useState('');
  const list = useMemo(() => catalogue.filter((c) => !q || (c.label + ' ' + c.desc).toLowerCase().includes(q.toLowerCase())), [q, catalogue]);
  return (
    <Sheet title="Add a section" onClose={onClose}>
      <div className="ws-pad">
        <span className="ws-in-ic"><i className="fas fa-magnifying-glass" aria-hidden="true" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sections" aria-label="Search sections" /></span>
        <div className="ws-cat">
          {list.map((c) => (
            <button type="button" key={c.type} className="ws-cat-it" onClick={() => onPick(c.type)}>
              <span className="ws-sec-ic"><i className={'fas ' + c.icon} aria-hidden="true" /></span>
              <span className="ws-sec-t"><b>{c.label}</b><small>{c.desc}</small></span>
              <i className="fas fa-plus ws-chev" aria-hidden="true" />
            </button>
          ))}
          {!list.length && <p className="rs-muted">No section matches “{q}”.</p>}
        </div>
      </div>
    </Sheet>
  );
}

function SettingsSheet({ onClose }) {
  const { d, setData, notify, go } = useWs();
  const pg = d.pg;
  const [f, setF] = useState({ title: pg.title, slug: pg.slug, meta: pg.meta_description, nav: pg.in_nav, pub: pg.published });
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    const r = await submitJson(d.urls.meta, { title: f.title, slug: pg.is_home ? '' : f.slug, meta_description: f.meta,
      show_in_nav: f.nav ? 'on' : '', is_published: f.pub ? 'on' : '' });
    setBusy(false);
    if (r.ok) {
      setData({ ...d, ...r.page });
      if (r.page.pg.slug !== pg.slug) window.history.replaceState(window.history.state, '', window.location.href);
      notify('ok', r.message); onClose();
    } else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!(await confirm({ title: `Delete “${pg.title}”?`, message: 'The page and all its sections will be deleted. This can’t be undone.', confirmText: 'Delete page', tone: 'danger' }))) return;
    const r = await submitJson(d.urls.delete, {});
    if (r.ok) { notify('ok', r.message); go(r.redirect || d.nav.home); } else notify('error', r.error || 'Could not delete.');
  };
  const slugPreview = (f.slug || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return (
    <Sheet title="Page settings" onClose={onClose}>
      <form className="ws-pad" onSubmit={save}>
        <Field label="Page name"><input value={f.title} maxLength={120} onChange={(e) => setF({ ...f, title: e.target.value })} required /></Field>
        {!pg.is_home && (
          <Field label="Web address" hint={window.location.host + '/site/' + (slugPreview || '…')}>
            <span className="ws-in-ic"><span className="ws-prefix">/site/</span><input value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} /></span>
          </Field>
        )}
        <Field label="Description on Google" max={180} count={(f.meta || '').length}>
          <AutoText minRows={2} value={f.meta} maxLength={180} onChange={(v) => setF({ ...f, meta: v })} placeholder="What visitors will find on this page" /></Field>
        <Switch on={f.nav} onChange={(v) => setF({ ...f, nav: v })} label="Show in the menu" sub="Adds this page to your website’s navigation" />
        {!pg.is_home && <Switch on={f.pub} onChange={(v) => setF({ ...f, pub: v })} label="Visible to visitors" sub={f.pub ? 'Anyone can open this page' : 'Hidden while you work on it'} />}
        <button className="rs-btn primary wide" disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button>
        {!pg.is_home && <button type="button" className="rs-btn ghost wide danger-t ws-del" onClick={del}><i className="fas fa-trash-can" aria-hidden="true" />Delete this page</button>}
      </form>
    </Sheet>
  );
}

function PreviewSheet({ url, dirty, onClose }) {
  const phone = usePhone();
  const [dev, setDev] = useState(phone ? 'phone' : 'laptop');
  const [n, setN] = useState(0);
  return (
    <Sheet title="Preview" onClose={onClose}>
      <div className="ws-prev">
        <div className="ws-prev-bar">
          {!phone && <div className="rs-seg" role="radiogroup" aria-label="Device">
            {[['laptop', 'fa-laptop', 'Laptop'], ['phone', 'fa-mobile-screen', 'Phone']].map(([k, ic, l]) => (
              <button type="button" key={k} role="radio" aria-checked={dev === k} className={dev === k ? 'on' : ''} onClick={() => setDev(k)}><i className={'fas ' + ic} aria-hidden="true" /><span>{l}</span></button>
            ))}
          </div>}
          {dirty && <span className="ws-prev-warn"><i className="fas fa-circle-info" aria-hidden="true" />Save to see your latest changes</span>}
          <button type="button" className="rs-btn sm ghost" onClick={() => setN(n + 1)}><i className="fas fa-rotate" aria-hidden="true" />Reload</button>
          <a className="rs-btn sm ghost" href={url} target="_blank" rel="noopener"><i className="fas fa-arrow-up-right-from-square" aria-hidden="true" />New tab</a>
        </div>
        <div className={'ws-prev-frame ' + dev}>
          <iframe key={n} title="Page preview" src={url} />
        </div>
      </div>
    </Sheet>
  );
}

const TONES = ['Warm', 'Formal', 'Inspiring', 'Friendly', 'Confident'];

function AiSheet({ idx, block, onClose, onDraft }) {
  const { d, notify } = useWs();
  const [tone, setTone] = useState('Warm');
  const [kw, setKw] = useState('');
  const [busy, setBusy] = useState(false);
  const run = async (e) => {
    e.preventDefault();
    setBusy(true);
    const r = await submitJson(`${d.urls.base}/block/${idx}/ai`, { tone, keywords: kw, expect: block.type });
    setBusy(false);
    if (r.ok) { onDraft(r.suggestions || {}); notify('ok', r.message); } else notify('error', r.error || 'AI could not write that.');
  };
  return (
    <Sheet title={'Write “' + block.label + '” with AI'} onClose={onClose}>
      <form className="ws-pad" onSubmit={run}>
        <span className="ws-field-l">Tone</span>
        <div className="rs-chips">{TONES.map((t) => <button type="button" key={t} className={'rs-chip' + (t === tone ? ' on' : '')} onClick={() => setTone(t)}>{t}</button>)}</div>
        <Field label="Anything to mention?" hint="e.g. STEM labs, 30 years of excellence, boarding"><input value={kw} maxLength={200} onChange={(e) => setKw(e.target.value)} /></Field>
        <p className="ws-note"><i className="fas fa-circle-info" aria-hidden="true" />The draft goes into the boxes. Nothing changes on your website until you tap Save.</p>
        <button className="rs-btn primary wide" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles')} aria-hidden="true" />{busy ? 'Writing…' : 'Write a draft'}</button>
      </form>
    </Sheet>
  );
}
