// Website overview: go live, pages (with menu order), look, admissions and
// the one-click site builder.
import React, { useState } from 'react';
import { confirm } from '../components/ui';
import { Sheet } from '../subjects/results';
import { useWs, submitJson, Switch, Field, AutoText, copyText } from './kit';

const fmt = (n) => (n == null ? '—' : Number(n).toLocaleString());

export function Overview() {
  const { d } = useWs();
  return (
    <div className="ws-ov">
      <Status />
      <div className="ws-ov-grid">
        <div className="ws-col">
          <Pages />
          <Builder />
        </div>
        <div className="ws-col">
          <Look />
          <Admissions />
        </div>
      </div>
      {!d.pages.length && <p className="rs-muted">No pages yet.</p>}
    </div>
  );
}

function Status() {
  const { d, setData, notify, write } = useWs();
  const [busy, setBusy] = useState(false);
  const c = d.counts || {};
  const toggle = async (on) => {
    if (on && !(await confirm({ title: 'Make your website public?', message: 'Anyone with the link — and search engines — will be able to see it.', confirmText: 'Go live' }))) return;
    setBusy(true);
    const r = await submitJson(d.urls.publish, { published: on ? 'on' : '' });
    setBusy(false);
    if (r.ok) { setData({ ...d, published: r.published }); notify('ok', r.message); } else notify('error', r.error || 'Could not change that.');
  };
  return (
    <section className={'ws-status ' + (d.published ? 'live' : 'draft')}>
      <div className="ws-status-top">
        <span className="ws-status-ic"><i className="fas fa-globe" aria-hidden="true" /></span>
        <div className="ws-status-t">
          <h1>{d.site_name}</h1>
          <p><span className={'ws-dot ' + (d.published ? 'live' : 'draft')} aria-hidden="true" />
            {d.published ? 'Live — anyone can visit your website' : 'Draft — only signed-in staff can see it'}</p>
        </div>
        <div className="ws-status-a">
          <a className="rs-btn" href={d.public_home} target="_blank" rel="noopener"><i className="fas fa-arrow-up-right-from-square" aria-hidden="true" />Open</a>
          <button type="button" className="rs-btn ghost" onClick={() => copyText(d.public_home, notify)}><i className="fas fa-link" aria-hidden="true" /><span className="rs-hide-sm">Copy link</span></button>
        </div>
      </div>
      {write && <Switch on={d.published} disabled={busy} onChange={toggle} label="Website is public" sub={d.published ? 'Turn off to take it offline while you work' : 'Turn on when you’re happy with it'} />}
      <div className="ws-stats">
        <span><b>{d.pages.length}</b><span>Pages</span></span>
        <a href={d.nav.news}><b>{fmt(c.posts)}</b><span>News posts{c.drafts ? ` · ${c.drafts} draft` : ''}</span></a>
        <a href={d.nav.media}><b>{fmt(c.media)}</b><span>Photos</span></a>
        <a href={d.nav.analytics}><b>{fmt(c.views7)}</b><span>Views this week</span></a>
      </div>
    </section>
  );
}

function Pages() {
  const { d, go, setData, notify, write } = useWs();
  const [adding, setAdding] = useState(false);
  const [order, setOrder] = useState(null);
  const pages = order || d.pages;
  const move = async (i, dir) => {
    const next = pages.slice();
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    setOrder(next);
    const r = await submitJson(d.urls.reorder, { order: next.map((p) => p.id).join(',') });
    if (r.ok) { setData({ ...d, pages: next }); setOrder(null); } else { setOrder(null); notify('error', r.error || 'Could not reorder.'); }
  };
  return (
    <section className="ws-card">
      <header className="ws-card-h">
        <div><h2>Pages</h2><p>Tap a page to edit it. Arrows set the order in your menu.</p></div>
        {write && <button type="button" className="rs-btn primary sm" onClick={() => setAdding(true)}><i className="fas fa-plus" aria-hidden="true" />New page</button>}
      </header>
      <ul className="ws-pages">
        {pages.map((p, i) => (
          <li key={p.id}>
            <a className="ws-page" href={p.edit}>
              <span className="ws-page-ic"><i className={'fas ' + (p.is_home ? 'fa-house' : 'fa-file-lines')} aria-hidden="true" /></span>
              <span className="ws-page-t">
                <b>{p.title}</b>
                <small>{p.address} · {p.sections} section{p.sections === 1 ? '' : 's'}</small>
              </span>
              <span className="ws-page-tags">
                {!p.published && <em className="warn">Hidden</em>}
                {p.published && !p.in_nav && !p.is_home && <em>Not in menu</em>}
              </span>
              <i className="fas fa-chevron-right ws-chev" aria-hidden="true" />
            </a>
            {write && pages.length > 1 && (
              <span className="ws-order">
                <button type="button" aria-label={'Move ' + p.title + ' up'} disabled={i === 0} onClick={() => move(i, -1)}><i className="fas fa-chevron-up" aria-hidden="true" /></button>
                <button type="button" aria-label={'Move ' + p.title + ' down'} disabled={i === pages.length - 1} onClick={() => move(i, 1)}><i className="fas fa-chevron-down" aria-hidden="true" /></button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {adding && <NewPage onClose={() => setAdding(false)} onDone={(url) => { setAdding(false); go(url); }} />}
    </section>
  );
}

const SUGGEST = ['About us', 'Academics', 'Admissions', 'Fees', 'Gallery', 'News', 'Contact'];

function NewPage({ onClose, onDone }) {
  const { d, notify } = useWs();
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const taken = new Set(d.pages.map((p) => p.title.toLowerCase()));
  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    const r = await submitJson(d.urls.new_page, { title: title.trim() });
    setBusy(false);
    if (r.ok) onDone(r.redirect); else notify('error', r.error || 'Could not create the page.');
  };
  return (
    <Sheet title="New page" onClose={onClose}>
      <form className="ws-pad" onSubmit={submit}>
        <Field label="Page name" hint="This is the name in your menu. You can change it later.">
          <input autoFocus value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Admissions" />
        </Field>
        <div className="rs-chips ws-suggest">
          {SUGGEST.filter((s) => !taken.has(s.toLowerCase())).map((s) => (
            <button type="button" key={s} className={'rs-chip' + (title === s ? ' on' : '')} onClick={() => setTitle(s)}>{s}</button>
          ))}
        </div>
        <button className="rs-btn primary wide" disabled={busy || !title.trim()}>{busy ? 'Creating…' : 'Create page'}</button>
      </form>
    </Sheet>
  );
}

function Look() {
  const { d, setData, notify, write } = useWs();
  const t0 = d.theme;
  const preset0 = d.presets.find((p) => p.key === t0.preset) || d.presets[0];
  const init = { preset: t0.preset, custom: !!(t0.primary || t0.accent), primary: t0.primary || preset0.primary,
    accent: t0.accent || preset0.accent, seo_title: t0.seo_title, seo_description: t0.seo_description };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(f) !== JSON.stringify(init);
  const preset = d.presets.find((p) => p.key === f.preset) || d.presets[0];
  const pick = (p) => setF((x) => ({ ...x, preset: p.key, primary: x.custom ? x.primary : p.primary, accent: x.custom ? x.accent : p.accent }));
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.theme, { preset: f.preset, custom_colors: f.custom ? 'on' : 'off',
      primary: f.primary, accent: f.accent, seo_title: f.seo_title, seo_description: f.seo_description });
    setBusy(false);
    if (r.ok) {
      setData({ ...d, theme: { preset: f.preset, primary: f.custom ? f.primary : '', accent: f.custom ? f.accent : '', seo_title: f.seo_title.slice(0, 70), seo_description: f.seo_description.slice(0, 180) } });
      notify('ok', r.message);
    } else notify('error', r.error || 'Could not save.');
  };
  const primary = f.custom ? f.primary : preset.primary;
  const accent = f.custom ? f.accent : preset.accent;
  return (
    <section className="ws-card">
      <header className="ws-card-h"><div><h2>Look</h2><p>Pick a style. Fonts, colours and shapes change together.</p></div></header>
      <div className="ws-presets" role="radiogroup" aria-label="Style">
        {d.presets.map((p) => (
          <button type="button" key={p.key} role="radio" aria-checked={f.preset === p.key} disabled={!write}
                  className={'ws-preset' + (f.preset === p.key ? ' on' : '')} onClick={() => pick(p)}
                  style={{ '--p': p.primary, '--a': p.accent, '--m': p.muted, '--r': p.radius }}>
            <span className="ws-preset-sw"><i /><i /><b style={{ fontFamily: p.font }}>Aa</b></span>
            <span className="ws-preset-t"><b>{p.label}</b><small>{p.mood}</small></span>
            {f.preset === p.key && <i className="fas fa-circle-check ws-preset-ok" aria-hidden="true" />}
          </button>
        ))}
      </div>
      <div className="ws-pad-x">
        <Switch on={f.custom} disabled={!write} onChange={(v) => setF({ ...f, custom: v, primary: v ? f.primary : preset.primary, accent: v ? f.accent : preset.accent })}
                label="Use my school colours" sub={f.custom ? 'Your colours replace the style’s colours' : 'Using the colours that come with ' + preset.label} />
        {f.custom && (
          <div className="ws-colors">
            <label className="ws-color"><input type="color" value={f.primary} onChange={(e) => setF({ ...f, primary: e.target.value })} /><span><b>Main colour</b><small>{f.primary}</small></span></label>
            <label className="ws-color"><input type="color" value={f.accent} onChange={(e) => setF({ ...f, accent: e.target.value })} /><span><b>Highlight colour</b><small>{f.accent}</small></span></label>
          </div>
        )}
        <div className="ws-mini" style={{ '--p': primary, '--a': accent, '--r': preset.radius }} aria-hidden="true">
          <div className="ws-mini-nav"><i /><span /><span /><span /><b /></div>
          <div className="ws-mini-hero"><strong style={{ fontFamily: preset.font }}>{d.site_name}</strong><span /><em>Apply now</em></div>
        </div>
        <details className="ws-more" open={!!(f.seo_title || f.seo_description) && false}>
          <summary><i className="fas fa-magnifying-glass" aria-hidden="true" />How you appear on Google <small>{f.seo_title ? 'Set' : 'Optional'}</small></summary>
          <Field label="Title on Google" max={70} count={f.seo_title.length}>
            <input value={f.seo_title} disabled={!write} maxLength={70} placeholder={d.site_name + ' — a short tagline'} onChange={(e) => setF({ ...f, seo_title: e.target.value })} /></Field>
          <Field label="Description on Google" max={180} count={f.seo_description.length}>
            <AutoText minRows={2} value={f.seo_description} disabled={!write} maxLength={180} placeholder="One or two sentences about your school" onChange={(v) => setF({ ...f, seo_description: v })} /></Field>
          <div className="ws-serp"><b>{f.seo_title || d.site_name}</b><small>{window.location.host}/site</small><span>{f.seo_description || 'Your description will appear here.'}</span></div>
        </details>
      </div>
      {write && dirty && (
        <footer className="ws-card-f">
          <button type="button" className="rs-btn ghost sm" onClick={() => setF(init)}>Undo</button>
          <button type="button" className="rs-btn primary sm" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save look'}</button>
        </footer>
      )}
    </section>
  );
}

function Admissions() {
  const { d, setData, notify, write } = useWs();
  const init = { open: d.adm.open, session_id: String(d.adm.session_id || ''), fee: d.adm.fee ? String(d.adm.fee) : '', intro: d.adm.intro };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(f) !== JSON.stringify(init);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.admissions, { web_admissions_open: f.open ? 'on' : '', session_id: f.session_id, fee: f.fee || '0', intro: f.intro });
    setBusy(false);
    if (r.ok) { setData({ ...d, adm: { open: f.open, session_id: f.session_id, fee: Number(f.fee) || 0, intro: f.intro } }); notify('ok', r.message); }
    else notify('error', r.error || 'Could not save.');
  };
  const fee = Number(f.fee) || 0;
  return (
    <section className="ws-card">
      <header className="ws-card-h">
        <div><h2>Online admissions</h2><p>Parents apply from your website. Applications appear in Admissions.</p></div>
      </header>
      <div className="ws-pad-x">
        <Switch on={f.open} disabled={!write} onChange={(v) => setF({ ...f, open: v })} label="Accept applications" sub={f.open ? 'The Apply form is open' : 'The Apply form shows “closed”'} />
        <div className="ws-link-row">
          <i className="fas fa-link" aria-hidden="true" /><span>{window.location.host}{d.apply_url}</span>
          <button type="button" className="rs-btn sm ghost" onClick={() => copyText(d.apply_url, notify)}>Copy</button>
          <a className="rs-btn sm ghost" href={d.apply_url} target="_blank" rel="noopener">Open</a>
        </div>
        {f.open && <>
          <div className="ws-two">
            <Field label="For which session">
              <select value={f.session_id} disabled={!write} onChange={(e) => setF({ ...f, session_id: e.target.value })}>
                <option value="">Not specified</option>
                {d.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select></Field>
            <Field label="Application fee (₦)" hint={fee > 0 ? (d.pay_configured ? 'Paid online before the form is sent.' : 'Online payment isn’t set up — the fee is shown for information only.') : 'Leave empty for free applications.'}>
              <input type="number" inputMode="decimal" min="0" step="0.01" value={f.fee} disabled={!write} placeholder="0" onChange={(e) => setF({ ...f, fee: e.target.value })} /></Field>
          </div>
          <Field label="Welcome note on the form" max={600} count={(f.intro || '').length}>
            <AutoText minRows={2} value={f.intro} disabled={!write} maxLength={600} placeholder="e.g. We’re delighted you’re considering our school…" onChange={(v) => setF({ ...f, intro: v })} /></Field>
        </>}
      </div>
      {write && dirty && (
        <footer className="ws-card-f">
          <button type="button" className="rs-btn ghost sm" onClick={() => setF(init)}>Undo</button>
          <button type="button" className="rs-btn primary sm" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save admissions'}</button>
        </footer>
      )}
    </section>
  );
}

function Builder() {
  const { d, refresh, notify, write } = useWs();
  const [busy, setBusy] = useState('');
  const [ai, setAi] = useState(true);
  if (!write) return null;
  const many = d.pages.length > 1;
  const run = async (fresh) => {
    const ok = await confirm({
      title: fresh ? 'Try a different design?' : 'Build your website?',
      message: 'This replaces all your current pages and sections with a new set. News, photos and assignments are kept.',
      confirmText: fresh ? 'Try a new design' : 'Build it', tone: 'danger' });
    if (!ok) return;
    setBusy(fresh ? 'fresh' : 'build');
    const fields = { use_ai: d.ai_available && ai ? 'on' : '' };
    if (fresh) fields.salt = String(Math.floor(Math.random() * 1e6));
    const r = await submitJson(d.urls.generate, fields);
    setBusy('');
    if (r.ok) { notify('ok', r.message); refresh(); } else notify('error', r.error || 'Could not build the site.');
  };
  return (
    <section className="ws-card ws-build">
      <div className="ws-build-ic"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /></div>
      <div className="ws-build-t">
        <h2>{many ? 'Want a fresh look?' : 'Build my website for me'}</h2>
        <p>{many ? 'Get a new design with the same kinds of sections — restyled and rearranged.'
          : 'A home page plus About, Academics, Admissions and Contact, ready to edit.'}</p>
        {d.ai_available && <label className="ws-check"><input type="checkbox" checked={ai} onChange={(e) => setAi(e.target.checked)} /> Write the words with AI</label>}
      </div>
      <div className="ws-build-a">
        {many && <button type="button" className="rs-btn" disabled={!!busy} onClick={() => run(true)}>
          <i className={'fas ' + (busy === 'fresh' ? 'fa-spinner fa-spin' : 'fa-shuffle')} aria-hidden="true" />Try another design</button>}
        <button type="button" className={'rs-btn' + (many ? ' ghost' : ' primary')} disabled={!!busy} onClick={() => run(false)}>
          <i className={'fas ' + (busy === 'build' ? 'fa-spinner fa-spin' : 'fa-bolt')} aria-hidden="true" />{many ? 'Rebuild from scratch' : 'Build my website'}</button>
      </div>
    </section>
  );
}
