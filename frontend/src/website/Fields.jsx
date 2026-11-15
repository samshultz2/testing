// Field editors for a section's content — no JSON anywhere: text, links,
// pictures, photo lists, bullet lists and lists of cards.
import React, { useState, useRef } from 'react';
import { useWs, postFiles, Field, AutoText, ImagePicker, Library } from './kit';

const ICONS = ['fa-graduation-cap', 'fa-book', 'fa-book-open', 'fa-child', 'fa-flask', 'fa-laptop-code', 'fa-calculator',
  'fa-palette', 'fa-music', 'fa-futbol', 'fa-trophy', 'fa-medal', 'fa-chalkboard-teacher', 'fa-users', 'fa-heart',
  'fa-shield-halved', 'fa-bus', 'fa-utensils', 'fa-globe', 'fa-star', 'fa-lightbulb', 'fa-microscope', 'fa-seedling', 'fa-hand-holding-heart'];

export function FieldEditor({ f, value, onChange, links, onImage }) {
  switch (f.kind) {
    case 'image':
      return <div className="ws-field"><span className="ws-field-l">{f.label}</span>
        <ImagePicker value={value || ''} label={f.label} wide onChange={(u) => { onChange(u); if (onImage && u) onImage(f.key); }} /></div>;
    case 'images': return <ImagesField label={f.label} value={Array.isArray(value) ? value : []} onChange={onChange} />;
    case 'strings': return <StringsField label={f.label} value={Array.isArray(value) ? value : []} onChange={onChange} />;
    case 'items': return <ItemsField f={f} value={Array.isArray(value) ? value : []} onChange={onChange} links={links} />;
    default: return <Simple f={f} value={value} onChange={onChange} links={links} />;
  }
}

function Simple({ f, value, onChange, links }) {
  const v = value == null ? '' : String(value);
  if (f.kind === 'long') {
    const hint = f.key === 'map_embed' ? 'In Google Maps: Share → Embed a map → copy the link inside src="…".' : null;
    return <Field label={f.label} hint={hint}><AutoText minRows={f.key === 'map_embed' ? 2 : 3} value={v} onChange={onChange} /></Field>;
  }
  if (f.kind === 'link') {
    return (
      <Field label={f.label} hint={f.key.endsWith('_href') || f.key === 'href' ? 'Pick a page or paste a web address.' : null}>
        <span className="ws-in-ic"><i className="fas fa-link" aria-hidden="true" />
          <input value={v} list={links} inputMode="url" placeholder={f.key.endsWith('href') ? '/site/apply' : 'https://'} onChange={(e) => onChange(e.target.value)} /></span>
      </Field>
    );
  }
  if (f.kind === 'icon') return <IconField label={f.label} value={v} onChange={onChange} />;
  return <Field label={f.label}><input value={v} onChange={(e) => onChange(e.target.value)} /></Field>;
}

function IconField({ label, value, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ws-field">
      <span className="ws-field-l">{label}</span>
      <button type="button" className="ws-icon-cur" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <i className={'fas ' + (value || 'fa-star')} aria-hidden="true" /><span>{open ? 'Close' : 'Change icon'}</span></button>
      {open && (
        <div className="ws-icons" role="radiogroup" aria-label={label}>
          {ICONS.map((ic) => (
            <button type="button" key={ic} role="radio" aria-checked={ic === value} className={ic === value ? 'on' : ''}
                    onClick={() => { onChange(ic); setOpen(false); }} aria-label={ic.replace('fa-', '').replace(/-/g, ' ')}>
              <i className={'fas ' + ic} aria-hidden="true" /></button>
          ))}
        </div>
      )}
    </div>
  );
}

function ImagesField({ label, value, onChange }) {
  const { urls, notify } = useWs();
  const [busy, setBusy] = useState(false);
  const [lib, setLib] = useState(false);
  const input = useRef(null);
  const upload = async (files) => {
    if (!files || !files.length) return;
    setBusy(true);
    const f = new FormData();
    Array.from(files).forEach((x) => f.append('file', x));
    const r = await postFiles(urls.upload, f);
    setBusy(false);
    if (input.current) input.current.value = '';
    if (r.ok) {
      onChange(value.concat(r.items.map((m) => m.url)));
      if (r.errors && r.errors.length) notify('error', r.errors[0]);
    } else notify('error', r.error || 'Upload failed.');
  };
  const move = (i, dir) => {
    const n = value.slice(); const j = i + dir;
    if (j < 0 || j >= n.length) return;
    [n[i], n[j]] = [n[j], n[i]]; onChange(n);
  };
  return (
    <div className="ws-field">
      <span className="ws-field-l">{label}<em>{value.length}</em></span>
      <div className="ws-thumbs">
        {value.map((u, i) => (
          <div key={u + i} className="ws-thumb">
            <img src={u} alt="" loading="lazy" />
            <div className="ws-thumb-a">
              {i > 0 && <button type="button" aria-label="Move earlier" onClick={() => move(i, -1)}><i className="fas fa-chevron-left" aria-hidden="true" /></button>}
              <button type="button" aria-label="Remove photo" onClick={() => onChange(value.filter((_, k) => k !== i))}><i className="fas fa-xmark" aria-hidden="true" /></button>
            </div>
          </div>
        ))}
        <button type="button" className="ws-thumb add" disabled={busy} onClick={() => input.current && input.current.click()}>
          <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-plus')} aria-hidden="true" /><span>{busy ? 'Uploading' : 'Upload'}</span></button>
        <button type="button" className="ws-thumb add" disabled={busy} onClick={() => setLib(true)}>
          <i className="fas fa-photo-film" aria-hidden="true" /><span>Library</span></button>
      </div>
      <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />
      {lib && <Library multi onClose={() => setLib(false)} onPick={(list) => { onChange(value.concat(list.filter((u) => !value.includes(u)))); setLib(false); }} />}
    </div>
  );
}

function StringsField({ label, value, onChange }) {
  const set = (i, v) => onChange(value.map((x, k) => (k === i ? v : x)));
  return (
    <div className="ws-field">
      <span className="ws-field-l">{label}</span>
      <div className="ws-strings">
        {value.map((s, i) => (
          <div key={i} className="ws-string">
            <i className="fas fa-check" aria-hidden="true" />
            <input value={s} onChange={(e) => set(i, e.target.value)} aria-label={label + ' ' + (i + 1)} />
            <button type="button" aria-label="Remove" onClick={() => onChange(value.filter((_, k) => k !== i))}><i className="fas fa-xmark" aria-hidden="true" /></button>
          </div>
        ))}
        <button type="button" className="ws-add-row" onClick={() => onChange(value.concat(''))}><i className="fas fa-plus" aria-hidden="true" />Add a point</button>
      </div>
    </div>
  );
}

function ItemsField({ f, value, onChange, links }) {
  const [open, setOpen] = useState(value.length <= 2 ? 0 : -1);
  const head = f.item_fields[0] ? f.item_fields[0].key : null;
  const set = (i, k, v) => onChange(value.map((x, n) => (n === i ? { ...x, [k]: v } : x)));
  const move = (i, dir) => {
    const n = value.slice(); const j = i + dir;
    if (j < 0 || j >= n.length) return;
    [n[i], n[j]] = [n[j], n[i]]; onChange(n); setOpen(j);
  };
  const add = () => {
    const blank = {};
    f.item_fields.forEach((x) => { blank[x.key] = x.kind === 'icon' ? 'fa-star' : ''; });
    onChange(value.concat(blank)); setOpen(value.length);
  };
  const cap = f.noun.charAt(0).toUpperCase() + f.noun.slice(1);
  return (
    <div className="ws-field">
      <span className="ws-field-l">{f.label}<em>{value.length}</em></span>
      <div className="ws-items">
        {value.map((it, i) => {
          const isOpen = open === i;
          const title = (head && it[head]) || `${cap} ${i + 1}`;
          return (
            <div key={i} className={'ws-item' + (isOpen ? ' open' : '')}>
              <div className="ws-item-h">
                <button type="button" className="ws-item-t" onClick={() => setOpen(isOpen ? -1 : i)} aria-expanded={isOpen}>
                  {it.icon ? <i className={'fas ' + it.icon} aria-hidden="true" /> : it.image ? <img src={it.image} alt="" /> : <b>{i + 1}</b>}
                  <span>{title}</span>
                  <i className={'fas fa-chevron-' + (isOpen ? 'up' : 'down')} aria-hidden="true" />
                </button>
              </div>
              {isOpen && (
                <div className="ws-item-b">
                  {f.item_fields.map((x) => (
                    x.kind === 'image'
                      ? <div key={x.key} className="ws-field"><span className="ws-field-l">{x.label}</span>
                          <ImagePicker value={it[x.key] || ''} label={x.label} onChange={(u) => set(i, x.key, u)} /></div>
                      : <Simple key={x.key} f={x} value={it[x.key]} links={links} onChange={(v) => set(i, x.key, v)} />
                  ))}
                  <div className="ws-item-a">
                    <button type="button" className="rs-btn sm ghost" disabled={i === 0} onClick={() => move(i, -1)}><i className="fas fa-arrow-up" aria-hidden="true" />Up</button>
                    <button type="button" className="rs-btn sm ghost" disabled={i === value.length - 1} onClick={() => move(i, 1)}><i className="fas fa-arrow-down" aria-hidden="true" />Down</button>
                    <button type="button" className="rs-btn sm ghost danger-t" onClick={() => { onChange(value.filter((_, n) => n !== i)); setOpen(-1); }}>
                      <i className="fas fa-trash-can" aria-hidden="true" />Remove</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <button type="button" className="ws-add-row" onClick={add}><i className="fas fa-plus" aria-hidden="true" />Add {f.noun}</button>
      </div>
    </div>
  );
}
