// News & blog: a searchable list and a distraction-free writing screen.
import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { confirm } from '../components/ui';
import { Seg, Blank, Menu, usePhone } from '../subjects/results';
import { useWs, submitJson, Switch, Field, AutoText, ImagePicker, useLeaveGuard, copyText } from './kit';

const portal = (on, el) => (on ? createPortal(el, document.body) : el);

export function NewsList() {
  const { d, go, notify, write } = useWs();
  const [q, setQ] = useState('');
  const [show, setShow] = useState('all');
  const [busy, setBusy] = useState(false);
  const posts = d.posts;
  const pub = posts.filter((p) => p.published).length;
  const list = useMemo(() => posts.filter((p) => (show === 'all' || (show === 'pub' ? p.published : !p.published))
    && (!q || (p.title + ' ' + p.category + ' ' + p.excerpt).toLowerCase().includes(q.toLowerCase()))), [posts, q, show]);
  const create = async () => {
    setBusy(true);
    const r = await submitJson(d.urls.new, { title: 'Untitled post' });
    setBusy(false);
    if (r.ok) go(r.redirect); else notify('error', r.error || 'Could not create a post.');
  };
  return (
    <div className="ws-list-page">
      <header className="ws-page-h">
        <div><h1>News &amp; blog</h1><p>Stories appear on any page with a “News / blog” section.</p></div>
        {write && <button type="button" className="rs-btn primary" disabled={busy} onClick={create}><i className="fas fa-pen-to-square" aria-hidden="true" />Write a post</button>}
      </header>
      {posts.length > 0 && (
        <div className="ws-filter">
          <span className="ws-in-ic grow"><i className="fas fa-magnifying-glass" aria-hidden="true" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search posts" aria-label="Search posts" /></span>
          <Seg label="Show" value={show} onChange={setShow} options={[
            { value: 'all', label: 'All', count: posts.length }, { value: 'pub', label: 'Published', count: pub },
            { value: 'draft', label: 'Drafts', count: posts.length - pub }]} />
        </div>
      )}
      {!posts.length && (
        <Blank icon="fa-newspaper" title="No posts yet">
          <p>Share sports days, results, open days and other news with parents.</p>
          {write && <button type="button" className="rs-btn primary" onClick={create}>Write your first post</button>}
        </Blank>
      )}
      {posts.length > 0 && (
        <ul className="ws-posts">
          {list.map((p) => (
            <li key={p.id}>
              <a href={p.edit} className="ws-post">
                <span className="ws-post-img">{p.cover ? <img src={p.cover} alt="" loading="lazy" /> : <i className="fas fa-newspaper" aria-hidden="true" />}</span>
                <span className="ws-post-t">
                  <b>{p.title}</b>
                  <small>{[p.category, p.date_label].filter(Boolean).join(' · ') || 'No date'}</small>
                  {p.excerpt && <span className="ws-post-x">{p.excerpt}</span>}
                </span>
                <em className={'ws-pill ' + (p.published ? 'ok' : 'warn')}>{p.published ? 'Published' : 'Draft'}</em>
              </a>
            </li>
          ))}
          {!list.length && <li className="rs-muted ws-pad">No posts match.</li>}
        </ul>
      )}
    </div>
  );
}

export function PostEditor() {
  const { d, setData, notify, write, go } = useWs();
  const phone = usePhone();
  const p = d.post;
  const init = { title: p.title, excerpt: p.excerpt, body: p.body, category: p.category, author: p.author, date: p.date, published: p.published, cover: p.cover };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(f) !== JSON.stringify(init);
  useLeaveGuard(dirty);
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v && v.target ? v.target.value : v }));
  const save = async (publish) => {
    const next = publish == null ? f : { ...f, published: publish };
    if (!next.title.trim()) { notify('error', 'Give your post a title.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.save, { title: next.title, excerpt: next.excerpt, body: next.body, category: next.category,
      author: next.author, published_at: next.date, is_published: next.published ? 'on' : '',
      cover_url: next.cover || '', clear_cover: next.cover ? '' : '1' });
    setBusy(false);
    if (r.ok) { setData({ ...d, post: r.post }); setF({ title: r.post.title, excerpt: r.post.excerpt, body: r.post.body, category: r.post.category, author: r.post.author, date: r.post.date, published: r.post.published, cover: r.post.cover }); notify('ok', r.message); }
    else notify('error', r.error || 'Could not save.');
  };
  const del = async () => {
    if (!(await confirm({ title: 'Delete this post?', message: `“${p.title}” will be removed from your website.`, confirmText: 'Delete', tone: 'danger' }))) return;
    const r = await submitJson(d.urls.delete, {});
    if (r.ok) { notify('ok', r.message); go(r.redirect || d.nav.news); } else notify('error', r.error || 'Could not delete.');
  };
  const words = (f.body || '').trim() ? f.body.trim().split(/\s+/).length : 0;
  return (
    <div className="ws-post-ed">
      <header className="ws-ed-h">
        <a className="ws-back" href={d.nav.news}><i className="fas fa-chevron-left" aria-hidden="true" /><span>News</span></a>
        <div className="ws-ed-t"><h1>{p.title || 'Untitled post'}</h1>
          <p><em className={'ws-pill ' + (p.published ? 'ok' : 'warn')}>{p.published ? 'Published' : 'Draft'}</em> {words} words · {Math.max(1, Math.round(words / 200))} min read</p></div>
        <div className="ws-ed-a">
          <a className="rs-btn" href={p.public} target="_blank" rel="noopener"><i className="fas fa-eye" aria-hidden="true" /><span className="rs-hide-sm">{p.published ? 'View' : 'Preview'}</span></a>
          <Menu items={[
            { icon: 'fa-link', label: 'Copy link', onClick: () => copyText(p.public, notify) },
            write && { icon: 'fa-trash-can', label: 'Delete post', danger: true, onClick: del },
          ]} />
        </div>
      </header>
      <fieldset className="ws-post-grid" disabled={!write}>
        <div className="ws-write">
          <input className="ws-title-in" value={f.title} onChange={set('title')} placeholder="Post title" aria-label="Title" maxLength={200} />
          <Field label="Summary" hint="One or two sentences shown in the news list." max={400} count={(f.excerpt || '').length}>
            <AutoText minRows={2} value={f.excerpt} maxLength={400} onChange={set('excerpt')} placeholder="What’s this story about?" /></Field>
          <Field label="Story" hint="Leave an empty line between paragraphs.">
            <AutoText className="ws-body-in" minRows={phone ? 10 : 16} value={f.body} onChange={set('body')} placeholder="Write your story here…" /></Field>
        </div>
        <aside className="ws-side">
          <div className="ws-card ws-pad">
            {p.published
              ? <Switch on={f.published} onChange={set('published')} label="Published" sub={f.published ? 'Visible on your website' : 'Will be hidden when you save'} />
              : <p className="ws-note"><i className="fas fa-lock" aria-hidden="true" />Draft — only staff can see it until you tap Publish.</p>}
            <div className="ws-two">
              <Field label="Date"><input type="date" value={f.date} onChange={set('date')} /></Field>
              <Field label="Category">
                <input value={f.category} list="ws-cats" onChange={set('category')} placeholder="e.g. Events" maxLength={60} />
                <datalist id="ws-cats">{(d.categories || []).map((c) => <option key={c} value={c} />)}</datalist></Field>
            </div>
            <Field label="Written by"><input value={f.author} onChange={set('author')} placeholder="e.g. The Principal" maxLength={120} /></Field>
            <div className="ws-field"><span className="ws-field-l">Cover picture</span>
              <ImagePicker wide value={f.cover} label="cover picture" onChange={set('cover')} /></div>
          </div>
        </aside>
      </fieldset>
      {write && portal(phone,
        <div className={'ws-save' + (phone ? ' fixed' : '') + (dirty ? ' dirty' : '')}>
          <span className="ws-save-t">{dirty ? <><span className="ws-sec-dot" aria-hidden="true" />Unsaved changes</> : <><i className="fas fa-check" aria-hidden="true" />Saved</>}</span>
          {!p.published && <button type="button" className="rs-btn ghost sm" disabled={busy || !dirty} onClick={() => save()}>Save draft</button>}
          {p.published
            ? <button type="button" className="rs-btn primary sm" disabled={busy || !dirty} onClick={() => save()}>{busy ? 'Saving…' : 'Save'}</button>
            : <button type="button" className="rs-btn primary sm" disabled={busy} onClick={() => save(true)}><i className="fas fa-paper-plane" aria-hidden="true" />{busy ? 'Saving…' : 'Publish'}</button>}
        </div>)}
    </div>
  );
}
