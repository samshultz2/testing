// Library — one React app for the whole section: overview, catalogue, add /
// edit book (ISBN lookup + barcode scan), issue, loans, holds, borrowers,
// reading lists, reports and settings. Built on the results kit + app kit so
// it feels native on phones (bottom sheets, pinned action bars, tap targets)
// and on laptops (dense lists, side summaries). Endpoints are unchanged.
import React, { useState, useMemo, useRef } from 'react';
import { submitJson, postFile } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, promptDialog, SectionShell, Toast } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Head, Tiles, Seg, Chips, Sheet, Menu, Blank, Bar, Meter, usePhone, initials } from '../subjects/results';
import { A, SecNav, Field, Toggle, Pill, SearchBox, Lookup, plural } from '../components/appkit';

// ---- helpers -----------------------------------------------------------------
const HUES = [210, 160, 25, 280, 340, 190, 45, 120, 0, 250];
const hue = (s) => HUES[[...String(s || '')].reduce((a, c) => a + c.charCodeAt(0), 0) % HUES.length];
const Cover = ({ title, size }) => (
  <span className={'lb-cover' + (size ? ' ' + size : '')} style={{ '--h': hue(title) }} aria-hidden="true">{initials(title)}</span>
);
function loanTone(l) {
  if (l.status === 'Lost') return ['bad', 'Lost'];
  if (l.status === 'Damaged') return ['mid', 'Damaged'];
  if (l.status === 'Returned') return ['good', 'Returned'];
  return l.is_overdue ? ['bad', `${plural(l.days_overdue, 'day')} late`] : ['info', `Due ${l.due}`];
}
const LoanPill = ({ l }) => { const [t, x] = loanTone(l); return <Pill tone={t}>{x}</Pill>; };

function LNav({ d, active }) {
  const u = d.urls || {};
  return <SecNav label="Library" active={active} items={[
    ['dashboard', 'fa-house', 'Overview', u.dashboard],
    ['books', 'fa-book', 'Catalogue', u.books],
    ['issue', 'fa-hand-holding', 'Issue', canWrite(d, 'circulation_issue') ? u.issue : null],
    ['loans', 'fa-rotate-left', 'Loans', u.loans],
    ['reservations', 'fa-bookmark', 'Holds', u.reservations],
    ['borrowers', 'fa-users', 'Borrowers', u.borrowers],
    ['reading_lists', 'fa-list-check', 'Reading lists', u.reading_lists],
    ['reports', 'fa-chart-line', 'Reports', u.reports, { x: true }],
    ['settings', 'fa-gear', 'Settings', u.settings, { x: true }],
  ]} />;
}
const ACTIVE = { book_form: 'books', borrower: 'borrowers' };
const Page = ({ d, children, className }) => (
  <div className={'rs cm lb ' + (className || '')}><LNav d={d} active={ACTIVE[d.page] || d.page} />{children}</div>
);

// Loan actions (return / renew / lost / damaged), shared by every loan list.
function useLoanActions(d, notify) {
  const nav = useNav();
  const [busy, setBusy] = useState(null);
  const act = async (l, url, fields, msg) => {
    setBusy(l.id);
    const r = await submitJson(url, fields || {});
    setBusy(null);
    if (r.ok) { notify('success', r.message || msg || 'Done.'); nav.refresh(); } else notify('error', r.error || 'That didn’t work.');
  };
  const ret = async (l) => {
    if (l.is_overdue && d.settings && Number(d.settings.fine_per_day)) {
      const fine = Number(d.settings.fine_per_day) * l.days_overdue;
      const charge = await confirm({ title: 'Return late book', message: `“${l.book}” is ${plural(l.days_overdue, 'day')} late. Charge the ${naira(fine)} fine?`,
        confirmText: 'Charge fine', cancelText: 'Waive fine' });
      act(l, l.return_url, charge ? {} : { waive: '1' }, 'Returned.');
    } else act(l, l.return_url, {}, 'Returned.');
  };
  const mark = async (l, kind) => {
    const cost = await promptDialog({ title: `Mark as ${kind.toLowerCase()}`, label: `${kind === 'Lost' ? 'Replacement cost' : 'Charge'} to bill the borrower (₦)`,
      placeholder: 'Blank = the book’s price', inputType: 'number', required: false });
    if (cost === null) return;
    act(l, l.mark_url, { kind, cost });
  };
  const canRet = canWrite(d, 'circulation_return');
  const actions = (l, compact) => (l.status === 'Borrowed' && canRet ? (
    <span className="lb-acts">
      <button type="button" className={'rs-btn primary sm' + (compact ? ' icon' : '')} disabled={busy === l.id} onClick={() => ret(l)} aria-label={'Return ' + l.book}>
        <i className={'fas ' + (busy === l.id ? 'fa-spinner fa-spin' : 'fa-rotate-left')} aria-hidden="true" />{!compact && ' Return'}</button>
      <Menu label="More" items={[
        { icon: 'fa-arrows-rotate', label: 'Renew', onClick: () => act(l, l.renew_url, {}, 'Renewed.') },
        { icon: 'fa-triangle-exclamation', label: 'Mark lost', onClick: () => mark(l, 'Lost') },
        { icon: 'fa-screwdriver-wrench', label: 'Mark damaged', onClick: () => mark(l, 'Damaged') },
        l.borrower_url && { icon: 'fa-user', label: 'Borrower history', onClick: () => nav.go(l.borrower_url) },
      ]} />
    </span>) : null);
  return { actions };
}

function LoanRow({ l, actions, hideBorrower }) {
  return (
    <div className={'lb-row' + (l.is_overdue && l.status === 'Borrowed' ? ' late' : '')}>
      <Cover title={l.book} />
      <span className="lb-row-t"><b>{l.book}</b>
        <small>{!hideBorrower && <>{l.borrower_url ? <A to={l.borrower_url}>{l.student}</A> : l.student}{l.borrower_type === 'staff' && ' (staff)'} · </>}
          out {l.borrowed}{l.renew_count > 0 ? ` · renewed ×${l.renew_count}` : ''}{l.returned ? ` · back ${l.returned}` : ''}</small></span>
      <span className="lb-row-s"><LoanPill l={l} />{(l.fine || l.replacement_cost) ? <small>{naira(l.fine || l.replacement_cost)}</small> : null}</span>
      {actions && actions(l)}
    </div>
  );
}

// ============================================================================
// Overview
// ============================================================================
function Dashboard({ d, notify }) {
  const { actions } = useLoanActions(d, notify);
  const u = d.urls;
  const catMax = Math.max(1, ...(d.cat_chart || []).map((c) => c.count));
  const topMax = Math.max(1, ...(d.most_borrowed || []).map((c) => c.count));
  const qa = [
    canWrite(d, 'circulation_issue') && { to: u.issue, ic: 'fa-hand-holding', tone: 'sms', t: 'Issue a book', s: 'Scan or search, pick a borrower' },
    canWrite(d, 'circulation_return') && { to: u.loans + '?status=Borrowed', ic: 'fa-rotate-left', tone: 'wa', t: 'Return a book', s: `${plural(d.on_loan, 'copy', 'copies')} out now` },
    canWrite(d, 'catalogue_create') && { to: u.add_book, ic: 'fa-barcode', tone: 'app', t: 'Add a book', s: 'Type or scan the ISBN' },
    { to: u.books, ic: 'fa-magnifying-glass', tone: 'em', t: 'Find a book', s: `${plural(d.titles, 'title')} · ${d.available} on the shelf` },
  ].filter(Boolean);
  const attn = [
    d.overdue ? { to: u.loans + '?status=Overdue', ic: 'fa-clock', tone: 'bad', t: `${plural(d.overdue, 'book')} overdue` } : null,
    d.res_ready ? { to: u.reservations + '?status=Ready', ic: 'fa-bookmark', tone: 'good', t: `${plural(d.res_ready, 'hold')} ready to collect` } : null,
    d.res_queued ? { to: u.reservations + '?status=Queued', ic: 'fa-hourglass-half', tone: 'info', t: `${plural(d.res_queued, 'person', 'people')} waiting for a copy` } : null,
    (d.lost + d.damaged) ? { to: u.loans + '?status=Lost', ic: 'fa-triangle-exclamation', tone: 'mid', t: `${d.lost} lost · ${d.damaged} damaged` } : null,
  ].filter(Boolean);
  return (
    <Page d={d}>
      <Head icon="fa-book-open" title="Library" sub={`${plural(d.titles, 'title')} · ${plural(d.copies, 'copy', 'copies')}`}>
        {canWrite(d, 'circulation_issue') && <A to={u.issue} className="rs-btn primary"><i className="fas fa-hand-holding" aria-hidden="true" /> Issue a book</A>}
        <Menu items={[
          canWrite(d, 'catalogue_create') && { icon: 'fa-plus', label: 'Add a book', href: u.add_book },
          canWrite(d, 'catalogue_export') && { icon: 'fa-file-csv', label: 'Export catalogue (CSV)', href: u.export, native: true },
          { icon: 'fa-chart-line', label: 'Reports', href: u.reports },
        ]} />
      </Head>
      <div className="cm-qa lb-qa">{qa.map((q) => (
        <A key={q.t} to={q.to} className="cm-qa-i"><span className={'cm-ch lg ' + q.tone}><i className={'fas ' + q.ic} aria-hidden="true" /></span>
          <span><b>{q.t}</b><small>{q.s}</small></span></A>))}</div>
      <div className="cm-grid2">
        <section className="rs-card cm-cov">
          <div className="cm-cov-t"><span className="k">On the shelf</span>
            <strong>{d.available}<small> of {d.copies} copies</small></strong>
            <Meter value={d.available} max={d.copies || 1} tone="good" />
            <span className="cm-mute">{d.on_loan} out on loan · {d.active_borrowers} active borrowers</span></div>
          {attn.length > 0 && <div className="cm-attn"><span className="k">Needs attention</span>
            {attn.map((a) => <A key={a.t} to={a.to} className={'cm-attn-i ' + a.tone}><i className={'fas ' + a.ic} aria-hidden="true" />{a.t}<i className="fas fa-chevron-right" aria-hidden="true" /></A>)}</div>}
        </section>
        <Tiles items={[
          { label: 'Issued today', value: d.issued_today || 0, sub: `${d.returned_today || 0} returned today` },
          { label: 'Overdue', value: d.overdue || 0, tone: d.overdue ? 'bad' : 'good', sub: d.overdue ? 'tap Needs attention' : 'all on time' },
          { label: 'New this month', value: d.added_month || 0, sub: 'titles added' },
          { label: 'Borrowers', value: d.active_borrowers || 0, sub: 'with a book out' },
        ]} />
      </div>
      <div className="cm-grid2">
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-calendar-day" aria-hidden="true" /> Due back soon</h3><A to={u.loans + '?status=Borrowed'} className="cm-link">All loans</A></div>
          {(d.due_soon || []).length ? <div className="cm-list">{d.due_soon.map((l) => <LoanRow key={l.id} l={l} actions={(x) => actions(x, true)} />)}</div>
            : <p className="cm-mute">Nothing due in the next two days.</p>}
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-clock" aria-hidden="true" /> Overdue</h3>{d.overdue > 0 && <A to={u.loans + '?status=Overdue'} className="cm-link">All {d.overdue}</A>}</div>
          {(d.overdue_list || []).length ? <div className="cm-list">{d.overdue_list.map((l) => <LoanRow key={l.id} l={l} actions={(x) => actions(x, true)} />)}</div>
            : <p className="cm-mute">No overdue books. 🎉</p>}
        </section>
      </div>
      <div className="cm-grid2">
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-fire" aria-hidden="true" /> Most borrowed</h3></div>
          {(d.most_borrowed || []).length ? <div className="lb-bars">{d.most_borrowed.map((b, i) => (
            <div key={i} className="lb-bar"><span className="n">{i + 1}</span><span className="t">{b.title}</span>
              <span className="b"><i style={{ width: (b.count / topMax * 100) + '%' }} /></span><b>{b.count}</b></div>))}</div>
            : <p className="cm-mute">No loans yet.</p>}
        </section>
        <section className="rs-card">
          <div className="rs-card-h"><h3><i className="fas fa-shapes" aria-hidden="true" /> By category</h3></div>
          {(d.cat_chart || []).length ? <div className="lb-bars">{[...d.cat_chart].sort((a, b) => b.count - a.count).map((c) => (
            <A key={c.name} to={u.books + '?category=' + encodeURIComponent(c.name === 'Uncategorised' ? '' : c.name)} className="lb-bar link">
              <Cover title={c.name} size="xs" /><span className="t">{c.name}</span>
              <span className="b"><i style={{ width: (c.count / catMax * 100) + '%' }} /></span><b>{c.count}</b></A>))}</div>
            : <p className="cm-mute">No books yet.</p>}
        </section>
      </div>
      <section className="rs-card">
        <div className="rs-card-h"><h3><i className="fas fa-clock-rotate-left" aria-hidden="true" /> Recent loans</h3><A to={u.loans + '?status=all'} className="cm-link">View all</A></div>
        {(d.recent || []).length ? <div className="cm-list">{d.recent.map((l) => <LoanRow key={l.id} l={l} />)}</div>
          : <Blank icon="fa-hand-holding" title="No loans yet">{canWrite(d, 'circulation_issue') && <A to={u.issue} className="rs-btn primary">Issue the first book</A>}</Blank>}
      </section>
    </Page>
  );
}

// ============================================================================
// Catalogue
// ============================================================================
function Books({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [category, setCategory] = useState(d.category || '');
  const [subject, setSubject] = useState(d.subject || '');
  const [avail, setAvail] = useState(d.avail === '1' ? '1' : '');
  const [limit, setLimit] = useState(60);
  const [reserving, setReserving] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();
  const del = async (b) => {
    if (!await confirm({ title: 'Remove book?', message: `“${b.title}” will be taken out of the catalogue.`, tone: 'danger', confirmText: 'Remove' })) return;
    const r = await submitJson(b.delete_url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not remove the book.');
  };
  const onImport = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    const r = await postFile(d.urls.import, file);
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Imported.'); nav.refresh(); } else notify('error', r.error || 'Could not import that file.');
  };
  const shown = d.books.filter((b) =>
    (!q || (b.title + ' ' + (b.author || '') + ' ' + (b.isbn || '') + ' ' + (b.barcode || '') + ' ' + (b.subject || '')).toLowerCase().includes(q.toLowerCase()))
    && (!category || b.category === category) && (!subject || b.subject === subject)
    && (!avail || (b.copies_available > 0 && !b.reference_only)));
  return (
    <Page d={d}>
      <Head icon="fa-book" title="Catalogue" sub={`${plural(shown.length, 'title')}${shown.length !== d.books.length ? ` of ${d.books.length}` : ''}`}>
        {canWrite(d, 'catalogue_create') && <A to={d.urls.add_book} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Add book</span></A>}
        <Menu items={[
          canWrite(d, 'catalogue_import') && { icon: busy ? 'fa-spinner' : 'fa-file-import', label: 'Import from CSV', onClick: () => fileRef.current && fileRef.current.click() },
          canWrite(d, 'catalogue_export') && { icon: 'fa-file-csv', label: 'Export catalogue (CSV)', href: d.urls.export, native: true },
        ]} />
        <input type="file" ref={fileRef} accept=".csv,text/csv" hidden onChange={onImport} />
      </Head>
      <div className="cm-filters">
        <SearchBox value={q} onChange={setQ} placeholder="Title, author, ISBN, barcode, subject" />
        {(d.subjects || []).length > 0 && (
          <select className="cm-sel" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject">
            <option value="">All subjects</option>{d.subjects.map((c) => <option key={c} value={c}>{c}</option>)}</select>)}
        <Seg label="Availability" value={avail} onChange={setAvail} options={[{ value: '', label: 'All' }, { value: '1', label: 'On the shelf' }]} />
      </div>
      {d.categories.length > 0 && <Chips label="Category" value={category} onChange={setCategory}
        items={[{ value: '', label: 'All' }, ...d.categories.map((c) => ({ value: c, label: c }))]} />}
      <section className="rs-card">
        {shown.length ? (
          <div className="cm-list">
            {shown.slice(0, limit).map((b) => {
              const out = b.copies_available <= 0;
              return (
                <div key={b.id} className={'lb-row book' + (b.status === 'Withdrawn' ? ' off' : '')}>
                  <Cover title={b.title} />
                  <span className="lb-row-t"><b>{b.title}</b>
                    <small>{[b.author, b.category, b.subject].filter(Boolean).join(' · ') || '—'}</small>
                    {(b.shelf || b.rack || b.isbn) && <small className="lb-where">{(b.shelf || b.rack) && <><i className="fas fa-location-dot" aria-hidden="true" /> {[b.shelf, b.rack].filter(Boolean).join(' · ')}</>}{b.isbn ? `  ${b.isbn}` : ''}</small>}</span>
                  <span className="lb-row-s">
                    {b.reference_only ? <Pill tone="info" icon="fa-book-bookmark">Reference</Pill>
                      : <Pill tone={out ? 'bad' : 'good'}>{out ? 'All out' : `${b.copies_available} of ${b.copies_total} in`}</Pill>}
                    {b.status === 'Withdrawn' && <Pill>Withdrawn</Pill>}
                  </span>
                  <span className="lb-acts">
                    {!out && !b.reference_only && canWrite(d, 'circulation_issue') && <A to={b.issue_url} className="rs-btn primary sm icon" aria-label={'Issue ' + b.title} title="Issue"><i className="fas fa-hand-holding" aria-hidden="true" /></A>}
                    <Menu label="More" items={[
                      !b.reference_only && canWrite(d, 'reservations_create') && { icon: 'fa-bookmark', label: out ? 'Reserve (join the queue)' : 'Hold a copy', onClick: () => setReserving(b) },
                      canWrite(d, 'catalogue_edit') && { icon: 'fa-pen', label: 'Edit details / copies', href: b.edit_url },
                      canWrite(d, 'catalogue_delete') && { icon: 'fa-trash', label: 'Remove', danger: true, onClick: () => del(b) },
                    ]} />
                  </span>
                </div>);
            })}
            {shown.length > limit && <button type="button" className="cm-showmore" onClick={() => setLimit((l) => l + 120)}>Show more ({shown.length - limit} left)</button>}
          </div>
        ) : (
          <Blank icon="fa-book" title={d.books.length ? 'No books match' : 'The catalogue is empty'}>
            <p>{d.books.length ? 'Try another search or clear the filters.' : 'Add books one by one with the ISBN, or import a CSV.'}</p>
            {canWrite(d, 'catalogue_create') && !d.books.length && <A to={d.urls.add_book} className="rs-btn primary"><i className="fas fa-plus" aria-hidden="true" /> Add a book</A>}
          </Blank>)}
      </section>
      {reserving && <ReserveSheet d={d} book={reserving} notify={notify} onClose={() => setReserving(null)} />}
    </Page>
  );
}

function BorrowerPick({ d, type, setType, picked, setPicked, autoFocus }) {
  return (
    <div className="cm-stack">
      <Seg label="Borrower type" value={type} onChange={(v) => { setType(v); setPicked(null); }}
           options={[{ value: 'student', icon: 'fa-user-graduate', label: 'Student' }, { value: 'staff', icon: 'fa-user-tie', label: 'Staff' }]} />
      <Lookup key={type} url={type === 'staff' ? d.urls.staff_search : d.urls.student_search} autoFocus={autoFocus}
              placeholder={type === 'staff' ? 'Search staff name or ID…' : 'Search student name or ID…'}
              picked={picked} onPick={setPicked} onClear={() => setPicked(null)} />
    </div>
  );
}

function ReserveSheet({ d, book, notify, onClose }) {
  const [type, setType] = useState('student');
  const [who, setWho] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!who) { notify('error', 'Choose who it’s for.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.reserve, { book_id: book.id, borrower_type: type,
      student_id: type === 'student' ? who.id : '', staff_id: type === 'staff' ? who.id : '' });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Reserved.'); onClose(); } else notify('error', r.error || 'Could not reserve.');
  };
  return (
    <Sheet title="Reserve a copy" onClose={onClose}>
      <div className="cm-sheet">
        <div className="lb-book-h"><Cover title={book.title} /><span><b>{book.title}</b><small>{book.copies_available > 0
          ? 'A copy is free — it will be held for them now.' : 'All copies are out — they join the queue and are next when one comes back.'}</small></span></div>
        <BorrowerPick d={d} type={type} setType={setType} picked={who} setPicked={setWho} autoFocus />
        <div className="cm-sheet-f">
          <button type="button" className="rs-btn ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="rs-btn primary" disabled={busy || !who} onClick={submit}><i className="fas fa-bookmark" aria-hidden="true" /> Reserve</button>
        </div>
      </div>
    </Sheet>
  );
}

// ============================================================================
// Add / edit book
// ============================================================================
function BookForm({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const b = d.book || {};
  const editing = !!d.book;
  const init = (k, dv) => (b[k] != null && b[k] !== '' ? b[k] : dv);
  const [f, setF] = useState({
    title: init('title', ''), subtitle: init('subtitle', ''), author: init('author', ''),
    isbn: init('isbn', ''), barcode: init('barcode', ''), category: init('category', ''),
    subject: init('subject', ''), keywords: init('keywords', ''), publisher: init('publisher', ''),
    edition: init('edition', ''), publication_year: init('publication_year', ''),
    language: init('language', ''), description: init('description', ''), shelf: init('shelf', ''),
    rack: init('rack', ''), condition: init('condition', 'Good'), status: init('status', 'Available'),
    price: init('price', ''), reference_only: !!b.reference_only,
    supplier: init('supplier', ''), source: init('source', 'Purchase'), donated_by: init('donated_by', ''),
    copies_total: b.copies_total != null ? b.copies_total : 1, notes: init('notes', ''),
  });
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(editing);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const [looking, setLooking] = useState(false);
  const [lookMsg, setLookMsg] = useState(null);
  const [dupes, setDupes] = useState([]);
  const fileRef = useRef(null);
  const applyMeta = (m) => setF((s) => {
    const next = { ...s };
    ['title', 'subtitle', 'author', 'publisher', 'subject', 'keywords', 'description', 'language'].forEach((k) => {
      if (m[k] && !String(next[k] || '').trim()) next[k] = m[k];
    });
    if (m.publication_year && !next.publication_year) next.publication_year = m.publication_year;
    if (m.isbn) next.isbn = m.isbn;
    return next;
  });
  const doLookup = async (isbnArg) => {
    const isbn = (isbnArg != null ? isbnArg : f.isbn) || '';
    if (!isbn.trim()) { setLookMsg({ tone: 'mid', text: 'Type or scan an ISBN first.' }); return; }
    setLooking(true); setLookMsg(null); setDupes([]);
    try {
      const res = await apiGet(`${d.urls.isbn_lookup}?isbn=${encodeURIComponent(isbn)}`);
      setDupes(res.existing || []);
      if (res.found) { applyMeta(res.book); setLookMsg({ tone: 'good', text: `Found via ${res.book.source} — details filled in. Check them and save.` }); }
      else { set('isbn', res.isbn || isbn); setLookMsg({ tone: 'mid', text: 'Not in the online catalogues (common for locally published books). Just type the title below.' }); }
    } catch (_) {
      setLookMsg({ tone: 'bad', text: 'Lookup failed — check the connection, or type the details.' });
    } finally { setLooking(false); }
  };
  const scanSupported = typeof window !== 'undefined' && 'BarcodeDetector' in window;
  const onScanFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (!scanSupported) { setLookMsg({ tone: 'mid', text: 'Barcode scanning isn’t supported on this device — type the ISBN instead.' }); return; }
    setLookMsg({ tone: 'info', text: 'Reading the barcode…' });
    try {
      const bitmap = await createImageBitmap(file);
      // eslint-disable-next-line no-undef
      const codes = await new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] }).detect(bitmap);
      if (codes && codes.length) { const code = codes[0].rawValue; set('isbn', code); doLookup(code); }
      else setLookMsg({ tone: 'mid', text: 'Couldn’t read a barcode — try a sharper photo or type the ISBN.' });
    } catch (_) { setLookMsg({ tone: 'bad', text: 'Could not read that image. Type the ISBN instead.' }); }
  };
  const addCopies = async (dupe) => {
    const n = Number(await promptDialog({ title: 'Add copies', label: `How many copies of “${dupe.title}” to add?`, inputType: 'number', defaultValue: '1' }));
    if (!n || n <= 0) return;
    const r = await submitJson(dupe.add_copies_url, { count: n });
    if (r.ok) nav.go(d.urls.books); else notify('error', r.error || 'Could not add copies.');
  };
  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!f.title.trim()) { notify('error', 'A book needs a title.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, reference_only: f.reference_only ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not save the book.');
  };
  const canSave = canWrite(d, editing ? 'catalogue_edit' : 'catalogue_create');
  const T = (k, label, extra) => <Field label={label} grow><input value={f[k]} onChange={(e) => set(k, e.target.value)} {...extra} /></Field>;
  return (
    <Page d={d} className="lb-formpage">
      <Head icon={editing ? 'fa-pen' : 'fa-plus'} title={editing ? 'Edit book' : 'Add a book'} sub={editing ? `${b.copies_available} of ${b.copies_total} on the shelf · ${b.on_loan} on loan` : 'Scan or type the ISBN to fill in the details for you.'} />
      <form onSubmit={submit} className="lb-form">
        {!editing && (
          <section className="rs-card lb-isbn">
            <div className="cm-step-h"><span className="cm-ch app sm"><i className="fas fa-barcode" aria-hidden="true" /></span><h3>Quick add by ISBN</h3></div>
            <div className="lb-isbn-r">
              <div className="cm-search grow"><i className="fas fa-barcode" aria-hidden="true" />
                <input value={f.isbn} placeholder="10 or 13-digit ISBN" inputMode="numeric" aria-label="ISBN"
                       onChange={(e) => set('isbn', e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); doLookup(); } }} /></div>
              <button type="button" className="rs-btn primary" onClick={() => doLookup()} disabled={looking}>
                <i className={'fas ' + (looking ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles')} aria-hidden="true" /> {looking ? 'Looking…' : 'Fill in'}</button>
              <button type="button" className="rs-btn ghost" onClick={() => fileRef.current && fileRef.current.click()} title="Take a photo of the barcode">
                <i className="fas fa-camera" aria-hidden="true" /><span className="rs-hide-sm"> Scan</span></button>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={onScanFile} />
            </div>
            {lookMsg && <p className={'lb-msg ' + lookMsg.tone} role="status">{lookMsg.text}</p>}
            {dupes.length > 0 && (
              <div className="lb-dupes"><b><i className="fas fa-circle-info" aria-hidden="true" /> Already in your catalogue?</b>
                {dupes.map((x) => (
                  <div key={x.id} className="lb-dupe"><span>{x.title}{x.author ? ` · ${x.author}` : ''} <small>({x.copies_available}/{x.copies_total} on the shelf)</small></span>
                    <button type="button" className="rs-btn primary sm" onClick={() => addCopies(x)}><i className="fas fa-plus" aria-hidden="true" /> Add copies to this</button></div>))}
                <small className="cm-mute">Or fill in the form to add it as a separate book.</small></div>)}
          </section>)}
        <section className="rs-card lb-stackcard">
          <div className="cm-step-h"><h3>The book</h3></div>
          <div className="cm-row2">{T('title', 'Title', { placeholder: 'e.g. New General Mathematics' })}{T('author', 'Author(s)')}</div>
          <div className="cm-row2">
            <Field label="Category" grow><input value={f.category} list="lbCats" onChange={(e) => set('category', e.target.value)} placeholder="Textbook, Story, Reference…" />
              <datalist id="lbCats">{(d.categories || []).map((c) => <option key={c} value={c} />)}</datalist></Field>
            <Field label="Subject" grow><input value={f.subject} list="lbSubs" onChange={(e) => set('subject', e.target.value)} placeholder="Mathematics, English…" />
              <datalist id="lbSubs">{(d.subjects || []).map((c) => <option key={c} value={c} />)}</datalist></Field>
          </div>
          <div className="cm-row2">
            <Field label="Copies" grow><input type="number" min="0" value={f.copies_total} onChange={(e) => set('copies_total', e.target.value)} /></Field>
            {T('shelf', 'Shelf', { placeholder: 'e.g. B3' })}{T('rack', 'Rack / row')}
          </div>
          <Toggle title="Reference only" sub="Stays in the library — can’t be borrowed" on={f.reference_only} onChange={(v) => set('reference_only', v)} />
          <button type="button" className="cm-more" aria-expanded={more} onClick={() => setMore((v) => !v)}>
            <i className={'fas ' + (more ? 'fa-chevron-up' : 'fa-sliders')} aria-hidden="true" /> {more ? 'Fewer details' : 'More details — publisher, ISBN, barcode, price, source…'}</button>
          {more && (
            <div className="cm-stack">
              <div className="cm-row2">{T('subtitle', 'Subtitle')}{T('publisher', 'Publisher')}</div>
              <div className="cm-row2">{editing && T('isbn', 'ISBN')}{T('barcode', 'Barcode / accession no.', { placeholder: 'Scannable code' })}{T('edition', 'Edition')}
                <Field label="Year" grow><input type="number" value={f.publication_year} onChange={(e) => set('publication_year', e.target.value)} /></Field></div>
              <div className="cm-row2">{T('language', 'Language')}{T('keywords', 'Keywords', { placeholder: 'Comma-separated, searchable' })}</div>
              <div className="cm-row2">
                <div className="cm-f grow"><span>Condition</span><Seg label="Condition" value={f.condition} onChange={(v) => set('condition', v)} options={['Good', 'Fair', 'Poor'].map((x) => ({ value: x, label: x }))} /></div>
                <div className="cm-f grow"><span>Status</span><Seg label="Status" value={f.status} onChange={(v) => set('status', v)} options={['Available', 'Withdrawn'].map((x) => ({ value: x, label: x }))} /></div>
              </div>
              <div className="cm-row2">
                <div className="cm-f grow"><span>Acquired by</span><Seg label="Acquired by" value={f.source} onChange={(v) => set('source', v)} options={['Purchase', 'Donation'].map((x) => ({ value: x, label: x }))} /></div>
                <Field label="Unit price (₦)" grow><input type="number" min="0" step="0.01" value={f.price} onChange={(e) => set('price', e.target.value)} /></Field>
              </div>
              <div className="cm-row2">{f.source === 'Donation' ? T('donated_by', 'Donated by') : T('supplier', 'Supplier / vendor')}</div>
              <Field label="Description"><textarea rows={2} value={f.description} onChange={(e) => set('description', e.target.value)} /></Field>
              <Field label="Notes"><textarea rows={2} value={f.notes} onChange={(e) => set('notes', e.target.value)} /></Field>
            </div>)}
        </section>
        {!phone && canSave && (
          <div className="lb-form-f"><A to={d.urls.books} className="rs-btn ghost">Cancel</A>
            <button className="rs-btn primary" disabled={busy}><i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-check')} aria-hidden="true" /> {editing ? 'Save changes' : 'Add to catalogue'}</button></div>)}
      </form>
      {phone && canSave && (
        <Bar><span className="rs-bar-t"><b>{f.title || 'New book'}</b><small>{plural(Number(f.copies_total) || 0, 'copy', 'copies')}</small></span>
          <button type="button" className="rs-btn primary" disabled={busy} onClick={() => submit()}><i className="fas fa-check" aria-hidden="true" /> Save</button></Bar>)}
    </Page>
  );
}

// ============================================================================
// Issue
// ============================================================================
function Issue({ d, notify }) {
  const nav = useNav();
  const phone = usePhone();
  const [book, setBook] = useState(d.preset ? { id: d.preset.id, label: d.preset.title } : null);
  const [type, setType] = useState('student');
  const [who, setWho] = useState(null);
  const [due, setDue] = useState(d.default_due);
  const [scan, setScan] = useState('');
  const [busy, setBusy] = useState(false);
  const days = Number((d.settings || {}).loan_days) || 14;
  const addDays = (n) => { const t = new Date(); t.setDate(t.getDate() + n); return t.toISOString().slice(0, 10); };
  const lookup = async () => {
    if (!scan.trim()) return;
    try {
      const r = await fetch(d.urls.barcode_lookup + '?code=' + encodeURIComponent(scan.trim()), { credentials: 'same-origin' });
      const j = await r.json();
      if (!j.ok) { notify('error', 'No book matches that barcode or ISBN.'); return; }
      if (j.book.reference_only) { notify('error', `“${j.book.title}” is reference-only and can’t be borrowed.`); return; }
      if (j.book.available <= 0) { notify('error', `All copies of “${j.book.title}” are out.`); return; }
      setBook({ id: j.book.id, label: `${j.book.title} (${j.book.available} avail)` }); setScan('');
    } catch (_) { /* ignore */ }
  };
  const submit = async (e) => {
    if (e) e.preventDefault();
    if (!book || !who) { notify('error', !book ? 'Pick a book first.' : 'Pick who is borrowing it.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { book_id: book.id, borrower_type: type,
      student_id: type === 'student' ? who.id : '', staff_id: type === 'staff' ? who.id : '', due_date: due });
    setBusy(false);
    if (r.ok) nav.go(r.redirect); else notify('error', r.error || 'Could not issue the book.');
  };
  const presets = [[7, '1 week'], [days, `${days} days`], [days * 2, `${days * 2} days`]].filter((x, i, a) => a.findIndex((y) => y[0] === x[0]) === i);
  const ready = book && who;
  return (
    <Page d={d} className="lb-issue-page">
      <Head icon="fa-hand-holding" title="Issue a book" sub="Book → borrower → due date. That’s it." />
      <form onSubmit={submit} className="lb-issue">
        <section className="rs-card cm-step">
          <div className="cm-step-h"><b>1</b><h3>Which book?</h3></div>
          {book ? (
            <div className="cm-picked"><Cover title={book.label} size="sm" /><b>{book.label}</b>
              <button type="button" className="cm-ib" onClick={() => setBook(null)} aria-label="Change book"><i className="fas fa-xmark" aria-hidden="true" /></button></div>
          ) : (
            <div className="cm-stack">
              <div className="cm-search"><i className="fas fa-barcode" aria-hidden="true" />
                <input value={scan} placeholder="Scan the barcode / ISBN, then Enter" aria-label="Scan barcode or ISBN" autoFocus={!phone}
                       onChange={(e) => setScan(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); lookup(); } }} /></div>
              <Lookup url={d.urls.book_search} placeholder="…or search title, author or ISBN" onPick={setBook} icon="fa-book" />
            </div>)}
        </section>
        <section className="rs-card cm-step">
          <div className="cm-step-h"><b>2</b><h3>Who’s borrowing it?</h3></div>
          <BorrowerPick d={d} type={type} setType={setType} picked={who} setPicked={setWho} />
        </section>
        <section className="rs-card cm-step">
          <div className="cm-step-h"><b>3</b><h3>Due back</h3></div>
          <Chips label="Loan length" value={presets.find((p) => addDays(p[0]) === due) ? String(presets.find((p) => addDays(p[0]) === due)[0]) : ''}
                 onChange={(v) => setDue(addDays(Number(v)))} items={presets.map(([n, l]) => ({ value: String(n), label: l }))} />
          <Field label="Date"><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
          <small className="cm-mute">{d.settings && Number(d.settings.fine_per_day) ? `Late returns are fined ${naira(d.settings.fine_per_day)} a day.` : 'No late fines are set.'}</small>
        </section>
        {!phone && (
          <div className="lb-form-f"><button className="rs-btn primary" disabled={busy || !ready}>
            <i className={'fas ' + (busy ? 'fa-spinner fa-spin' : 'fa-hand-holding')} aria-hidden="true" /> Issue book</button></div>)}
      </form>
      {phone && (
        <Bar><span className="rs-bar-t"><b>{ready ? 'Ready to issue' : !book ? 'Pick a book' : 'Pick a borrower'}</b><small>{who ? who.label : book ? book.label : ''}</small></span>
          <button type="button" className="rs-btn primary" disabled={busy || !ready} onClick={() => submit()}><i className="fas fa-hand-holding" aria-hidden="true" /> Issue</button></Bar>)}
    </Page>
  );
}

// ============================================================================
// Loans
// ============================================================================
function Loans({ d, notify }) {
  const nav = useNav();
  const { actions } = useLoanActions(d, notify);
  const [q, setQ] = useState('');
  const c = d.counts || {};
  const shown = d.loans.filter((l) => !q || (l.book + ' ' + l.student + ' ' + (l.borrower_ref || '')).toLowerCase().includes(q.toLowerCase()));
  const remind = async () => {
    if (!await confirm({ title: 'Remind parents?', message: 'A text reminder to the parents of students with overdue books will be drafted in Communication. Nothing is sent until you review it.', confirmText: 'Draft reminder' })) return;
    const r = await submitJson(d.urls.remind_overdue, {});
    if (r.ok) { notify('success', r.message); if (r.redirect) nav.go(r.redirect); } else notify('error', r.error || 'Could not draft reminders.');
  };
  return (
    <Page d={d}>
      <Head icon="fa-rotate-left" title="Loans" sub={`${plural(c.Borrowed || 0, 'book')} out · ${c.Overdue || 0} overdue`}>
        {canWrite(d, 'circulation_issue') && <A to={d.urls.issue} className="rs-btn primary"><i className="fas fa-hand-holding" aria-hidden="true" /><span className="rs-hide-sm"> Issue</span></A>}
        {canWrite(d, 'circulation_remind') && (c.Overdue || 0) > 0 && <Menu items={[{ icon: 'fa-comment-sms', label: 'Text parents about overdue books', onClick: remind }]} />}
      </Head>
      <div className="cm-filters">
        <SearchBox value={q} onChange={setQ} placeholder="Find a book or borrower" />
      </div>
      <Seg label="Show" value={d.status} onChange={(v) => nav.go(d.urls.loans + '?status=' + v)} options={[
        { value: 'Borrowed', label: 'Out', count: c.Borrowed }, { value: 'Overdue', label: 'Overdue', count: c.Overdue },
        { value: 'Returned', label: 'Returned' }, { value: 'Lost', label: 'Lost', count: c.Lost || undefined },
        { value: 'Damaged', label: 'Damaged', count: c.Damaged || undefined }, { value: 'all', label: 'All' }]} />
      <section className="rs-card">
        {shown.length ? <div className="cm-list">{shown.map((l) => <LoanRow key={l.id} l={l} actions={actions} />)}</div>
          : <Blank icon="fa-rotate-left" title={q ? 'No loans match' : d.status === 'Overdue' ? 'Nothing overdue' : 'No loans here'} />}
      </section>
    </Page>
  );
}

// ============================================================================
// Holds (reservations)
// ============================================================================
function Reservations({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(null);
  const act = async (r, url, opts) => {
    if (opts && !await confirm(opts)) return;
    setBusy(r.id);
    const res = await submitJson(url, {});
    setBusy(null);
    if (res.ok) { if (res.message) notify('success', res.message); nav.refresh(); } else notify('error', res.error || 'That didn’t work.');
  };
  const tone = { Ready: 'good', Queued: 'mid', Fulfilled: '', Cancelled: '', Expired: 'bad' };
  return (
    <Page d={d}>
      <Head icon="fa-bookmark" title="Holds" sub="Books put aside or queued for a borrower.">
        {canWrite(d, 'reservations_create') && <A to={d.urls.books} className="rs-btn ghost"><i className="fas fa-plus" aria-hidden="true" /> Reserve from catalogue</A>}
      </Head>
      <Seg label="Show" value={d.status} onChange={(v) => nav.go(d.urls.reservations + '?status=' + v)} options={[
        { value: 'open', label: 'Open' }, { value: 'Ready', label: 'Ready' }, { value: 'Queued', label: 'Waiting' },
        { value: 'Fulfilled', label: 'Collected' }, { value: 'Cancelled', label: 'Cancelled' }, { value: 'Expired', label: 'Expired' }]} />
      <section className="rs-card">
        {d.reservations.length ? <div className="cm-list">{d.reservations.map((r) => (
          <div key={r.id} className="lb-row">
            <Cover title={r.book} />
            <span className="lb-row-t"><b>{r.book}</b><small>for {r.borrower}{r.borrower_type === 'staff' ? ' (staff)' : ''} · placed {r.created}{r.status === 'Ready' && r.expires ? ` · hold ends ${r.expires}` : ''}</small></span>
            <span className="lb-row-s"><Pill tone={tone[r.status]}>{r.status === 'Queued' ? 'Waiting' : r.status}</Pill></span>
            {(r.status === 'Queued' || r.status === 'Ready') && (
              <span className="lb-acts">
                {r.available > 0 && canWrite(d, 'reservations_fulfill') && <button type="button" className="rs-btn primary sm" disabled={busy === r.id}
                  onClick={() => act(r, r.fulfill_url, { title: 'Issue now?', message: `Lend “${r.book}” to ${r.borrower}.`, confirmText: 'Issue' })}><i className="fas fa-hand-holding" aria-hidden="true" /><span className="rs-hide-sm"> Issue</span></button>}
                {canWrite(d, 'reservations_cancel') && <button type="button" className="cm-ib" disabled={busy === r.id} aria-label="Cancel hold"
                  onClick={() => act(r, r.cancel_url, { title: 'Cancel this hold?', tone: 'danger', confirmText: 'Cancel hold', cancelText: 'Keep' })}><i className="fas fa-xmark" aria-hidden="true" /></button>}
              </span>)}
          </div>))}</div>
          : <Blank icon="fa-bookmark" title="No holds here"><p>Reserve a book from the catalogue to hold it for someone.</p></Blank>}
      </section>
    </Page>
  );
}

// ============================================================================
// Borrowers
// ============================================================================
function Borrowers({ d }) {
  const [q, setQ] = useState(d.q || '');
  const [type, setType] = useState(d.type || '');
  const [limit, setLimit] = useState(80);
  const shown = d.borrowers.filter((b) => (!type || b.type === type)
    && (!q || (b.name + ' ' + b.ref + ' ' + (b.class || '')).toLowerCase().includes(q.toLowerCase())));
  return (
    <Page d={d}>
      <Head icon="fa-users" title="Borrowers" sub={`${plural(d.borrowers.length, 'person', 'people')} have borrowed from the library`} />
      <div className="cm-filters">
        <SearchBox value={q} onChange={setQ} placeholder="Name, ID or class" />
        <Seg label="Type" value={type} onChange={setType} options={[{ value: '', label: 'All' }, { value: 'student', label: 'Students' }, { value: 'staff', label: 'Staff' }]} />
      </div>
      <section className="rs-card">
        {shown.length ? <div className="cm-list">{shown.slice(0, limit).map((b) => (
          <A key={b.type + b.id} to={b.url} className="lb-row link">
            <span className="rs-av" aria-hidden="true">{initials(b.name)}</span>
            <span className="lb-row-t"><b>{b.name}</b><small>{[b.type === 'staff' ? 'Staff' : b.class, b.ref].filter(Boolean).join(' · ')}</small></span>
            <span className="lb-row-s">{b.overdue ? <Pill tone="bad">{b.overdue} overdue</Pill> : b.active ? <Pill tone="info">{b.active} out</Pill> : null}
              <small>{plural(b.total, 'loan')}</small></span>
            <i className="fas fa-chevron-right cm-row-go" aria-hidden="true" />
          </A>))}
          {shown.length > limit && <button type="button" className="cm-showmore" onClick={() => setLimit((l) => l + 150)}>Show more ({shown.length - limit} left)</button>}</div>
          : <Blank icon="fa-users" title={q ? 'No one matches' : 'No borrowers yet'}><p>People appear here once they borrow a book.</p></Blank>}
      </section>
    </Page>
  );
}

function Borrower({ d, notify }) {
  const { actions } = useLoanActions(d, notify);
  const b = d.borrower;
  const s = d.stats;
  return (
    <Page d={d}>
      <Head icon={b.type === 'staff' ? 'fa-user-tie' : 'fa-user-graduate'} title={b.name}
            sub={[b.type === 'staff' ? 'Staff' : 'Student', b.ref, b.class].filter(Boolean).join(' · ')}>
        {canWrite(d, 'circulation_issue') && <A to={d.urls.issue} className="rs-btn primary"><i className="fas fa-hand-holding" aria-hidden="true" /> Issue a book</A>}
      </Head>
      <Tiles items={[
        { label: 'Out now', value: s.out, tone: s.overdue ? 'bad' : '', sub: s.overdue ? `${s.overdue} overdue` : 'none overdue' },
        { label: 'Total loans', value: s.total, sub: 'all time' },
        { label: 'Lost / damaged', value: s.lost + s.damaged, tone: (s.lost + s.damaged) ? 'mid' : '' },
        { label: 'Fines & costs', value: s.fines ? naira(s.fines) : '₦0' },
      ]} />
      <section className="rs-card">
        <div className="rs-card-h"><h3>Has now</h3><small>{plural(d.current.length, 'book')}</small></div>
        {d.current.length ? <div className="cm-list">{d.current.map((l) => <LoanRow key={l.id} l={l} actions={actions} hideBorrower />)}</div>
          : <p className="cm-mute">Nothing out right now.</p>}
      </section>
      <section className="rs-card">
        <div className="rs-card-h"><h3>History</h3><small>{plural(d.past.length, 'loan')}</small></div>
        {d.past.length ? <div className="cm-list">{d.past.map((l) => <LoanRow key={l.id} l={l} hideBorrower />)}</div>
          : <p className="cm-mute">No past loans.</p>}
      </section>
    </Page>
  );
}

// ============================================================================
// Reading lists
// ============================================================================
function ReadingLists({ d, notify }) {
  const nav = useNav();
  const [adding, setAdding] = useState(false);
  const [classId, setClassId] = useState(d.class_id ? String(d.class_id) : '');
  const [book, setBook] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const add = async () => {
    if (!classId || !book) { notify('error', 'Pick a class and a book.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.add, { class_id: classId, book_id: book.id, note });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Added.'); setBook(null); setNote(''); setAdding(false); nav.refresh(); } else notify('error', r.error || 'Could not add.');
  };
  const remove = async (it) => {
    if (!await confirm({ title: 'Remove from list?', message: `“${it.book}” will come off ${it.class}’s list.`, tone: 'danger', confirmText: 'Remove' })) return;
    const r = await submitJson(it.remove_url, {});
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not remove.');
  };
  const groups = useMemo(() => {
    const g = {};
    d.items.forEach((it) => { (g[it.class] = g[it.class] || []).push(it); });
    return Object.entries(g);
  }, [d.items]);
  const can = canWrite(d, 'reading_lists_manage');
  return (
    <Page d={d}>
      <Head icon="fa-list-check" title="Reading lists" sub="Books recommended to each class.">
        {can && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}><i className="fas fa-plus" aria-hidden="true" /><span className="rs-hide-sm"> Recommend a book</span></button>}
      </Head>
      <div className="cm-filters">
        <select className="cm-sel" value={d.class_id || ''} onChange={(e) => nav.go(e.target.value ? d.urls.self + '?class_id=' + e.target.value : d.urls.self)} aria-label="Class">
          <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      </div>
      {groups.length ? groups.map(([cls, items]) => (
        <section className="rs-card" key={cls}>
          <div className="rs-card-h"><h3><i className="fas fa-school" aria-hidden="true" /> {cls}</h3><small>{plural(items.length, 'book')}</small></div>
          <div className="cm-list">{items.map((it) => (
            <div key={it.id} className="lb-row">
              <Cover title={it.book} />
              <span className="lb-row-t"><b>{it.book}</b><small>{[it.author, it.note, it.by && `added by ${it.by}`].filter(Boolean).join(' · ')}</small></span>
              {can && <button type="button" className="cm-ib" onClick={() => remove(it)} aria-label={'Remove ' + it.book}><i className="fas fa-xmark" aria-hidden="true" /></button>}
            </div>))}</div>
        </section>
      )) : <Blank icon="fa-list-check" title="No recommendations yet"><p>Recommend books to a class and they show up here.</p>
        {can && <button type="button" className="rs-btn primary" onClick={() => setAdding(true)}><i className="fas fa-plus" aria-hidden="true" /> Recommend a book</button>}</Blank>}
      {adding && (
        <Sheet title="Recommend a book" onClose={() => setAdding(false)}>
          <div className="cm-sheet">
            <Field label="Class"><select value={classId} onChange={(e) => setClassId(e.target.value)}>
              <option value="">Choose a class…</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <div className="cm-f"><span>Book</span><Lookup url={d.urls.book_search} placeholder="Search title, author or ISBN" picked={book} onPick={setBook} onClear={() => setBook(null)} icon="fa-book" /></div>
            <Field label="Note (optional)"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Term 1 core text" /></Field>
            <div className="cm-sheet-f"><button type="button" className="rs-btn ghost" onClick={() => setAdding(false)}>Cancel</button>
              <button type="button" className="rs-btn primary" disabled={busy || !book || !classId} onClick={add}><i className="fas fa-plus" aria-hidden="true" /> Add to list</button></div>
          </div>
        </Sheet>)}
    </Page>
  );
}

// ============================================================================
// Reports
// ============================================================================
function Reports({ d }) {
  const nav = useNav();
  const sel = d.sel || {};
  const rep = d.report || { columns: [], rows: [], summary: [], title: '' };
  const [from, setFrom] = useState(sel.from || '');
  const [to, setTo] = useState(sel.to || '');
  const [category, setCategory] = useState(sel.category || '');
  const [subject, setSubject] = useState(sel.subject || '');
  const [limit, setLimit] = useState(100);
  const params = (extra) => ({ type: sel.type, from, to, category, subject, ...extra });
  const go = (extra) => navParams(nav.go, d.urls.self, params(extra));
  const qs = () => Object.entries(params({})).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const cell = (col, row) => { const v = row[col.key]; if (col.money) return typeof v === 'number' ? naira(v) : v; return (v === '' || v == null) ? '—' : v; };
  return (
    <Page d={d}>
      <Head icon="fa-chart-line" title="Reports" sub={rep.title}>
        {canWrite(d, 'reports_export') && <Menu label="Export" items={[
          { icon: 'fa-file-excel', label: 'Excel', href: `${d.urls.export}?format=xlsx&${qs()}`, native: true },
          { icon: 'fa-file-csv', label: 'CSV', href: `${d.urls.export}?format=csv&${qs()}`, native: true }]} />}
      </Head>
      <Chips label="Report" value={sel.type} onChange={(v) => go({ type: v })} items={d.report_types.map((t) => ({ value: t.key, label: t.label }))} />
      <div className="cm-filters">
        <div className="cm-range lb-range"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" /><span>→</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" /></div>
        <select className="cm-sel" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        {(d.subjects || []).length > 0 && <select className="cm-sel" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject">
          <option value="">All subjects</option>{d.subjects.map((c) => <option key={c} value={c}>{c}</option>)}</select>}
        <button type="button" className="rs-btn primary sm" onClick={() => go({})}>Apply</button>
      </div>
      {rep.summary && rep.summary.length > 0 && <Tiles items={rep.summary.slice(0, 4).map((x) => ({ label: x.label, value: x.value }))} />}
      <section className="rs-card lb-tablecard">
        {rep.rows.length ? (
          <div className="lb-table-wrap"><table className="lb-table">
            <thead><tr>{rep.columns.map((c) => <th key={c.key} className={c.align === 'right' ? 'r' : ''}>{c.label}</th>)}</tr></thead>
            <tbody>{rep.rows.slice(0, limit).map((r, i) => <tr key={i}>{rep.columns.map((c) => <td key={c.key} className={c.align === 'right' ? 'r' : ''}>{cell(c, r)}</td>)}</tr>)}</tbody>
          </table></div>
        ) : <Blank icon="fa-chart-line" title="Nothing in this period"><p>Try a wider date range or another report.</p></Blank>}
        {rep.rows.length > limit && <button type="button" className="cm-showmore" onClick={() => setLimit((l) => l + 200)}>Show more ({rep.rows.length - limit} left)</button>}
      </section>
    </Page>
  );
}

// ============================================================================
// Settings
// ============================================================================
function Settings({ d, notify }) {
  const [loanDays, setLoanDays] = useState(d.settings.loan_days);
  const [fine, setFine] = useState(d.settings.fine_per_day);
  const [busy, setBusy] = useState(false);
  const can = canWrite(d, 'settings');
  const dirty = String(loanDays) !== String(d.settings.loan_days) || String(fine) !== String(d.settings.fine_per_day);
  const save = async () => {
    setBusy(true);
    const r = await submitJson(d.submit_url, { loan_days: loanDays, fine_per_day: fine });
    setBusy(false);
    if (r.ok) notify('success', r.message || 'Saved.'); else notify('error', r.error || 'Could not save.');
  };
  return (
    <Page d={d}>
      <Head icon="fa-gear" title="Library settings" sub="Loan rules used when books are issued and returned." />
      <section className="rs-card lb-stackcard lb-set">
        <div className="cm-row2">
          <Field label="Loan period (days)" grow hint="Default due date when issuing."><input type="number" min="1" value={loanDays} disabled={!can} onChange={(e) => setLoanDays(e.target.value)} /></Field>
          <Field label="Late fine (₦ per day)" grow hint="0 turns fines off."><input type="number" min="0" step="1" value={fine} disabled={!can} onChange={(e) => setFine(e.target.value)} /></Field>
        </div>
        <p className="cm-mute">A book issued today is due back in <b>{plural(Number(loanDays) || 0, 'day')}</b>{Number(fine) ? <>; a week late costs <b>{naira(Number(fine) * 7)}</b> (you can waive it on return).</> : <>; late returns aren’t fined.</>}</p>
        {!can && <p className="cm-mute">You don’t have permission to change these.</p>}
      </section>
      {can && dirty && <Bar><span className="rs-bar-t"><b>Unsaved changes</b><small>Loan rules</small></span>
        <button type="button" className="rs-btn primary" disabled={busy} onClick={save}><i className="fas fa-check" aria-hidden="true" /> Save</button></Bar>}
    </Page>
  );
}

const SCREENS = { dashboard: Dashboard, books: Books, book_form: BookForm, issue: Issue, loans: Loans, reservations: Reservations, borrowers: Borrowers, borrower: Borrower, reading_lists: ReadingLists, reports: Reports, settings: Settings };

export default function LibraryApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = (tone, text) => setToast({ tone, text, at: Date.now() });
  const Screen = SCREENS[d.page] || Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        <Screen d={d} notify={notify} />
        {toast && <Toast key={toast.at} tone={toast.tone} onClose={() => setToast(null)}>{toast.text}</Toast>}
      </SectionShell>
    </NavCtx.Provider>
  );
}
