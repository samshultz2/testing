import React, { useState, useEffect, useRef } from 'react';
import { chartPalette } from '../lib/hooks';
import { submitJson, postFile } from '../lib/forms';
import { apiGet } from '../lib/api';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, promptDialog, Banner, PageHeader, Empty, SectionTabs, Autocomplete, SectionShell, Table, Modal } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'],
  ['books', 'fa-book', 'Catalogue'],
  ['issue', 'fa-hand-holding', 'Issue'],
  ['loans', 'fa-rotate-left', 'Loans'],
  ['reservations', 'fa-bookmark', 'Reservations'],
  ['borrowers', 'fa-users', 'Borrowers'],
  ['reading_lists', 'fa-list-check', 'Reading lists'],
  ['reports', 'fa-chart-line', 'Reports'],
  ['settings', 'fa-gear', 'Settings'],
];
const ACTIVE = { dashboard: 'dashboard', books: 'books', book_form: 'books', issue: 'issue', loans: 'loans', reservations: 'reservations', borrowers: 'borrowers', borrower: 'borrowers', reading_lists: 'reading_lists', reports: 'reports', settings: 'settings' };
const Tabs = ({ urls, page }) => { const { go } = useNav(); return <SectionTabs tabs={TABS} urls={urls} active={ACTIVE[page]} go={go} />; };

function statusBadge(l) {
  if (l.status === 'Lost') return <span className="badge badge-danger">Lost</span>;
  if (l.status === 'Damaged') return <span className="badge badge-warning">Damaged</span>;
  const cls = l.status === 'Returned' ? 'badge-success' : (l.is_overdue ? 'badge-danger' : 'badge-warning');
  return <span className={'badge ' + cls}>{l.is_overdue ? 'Overdue' : l.status}</span>;
}

// ---- Dashboard -------------------------------------------------------------
function Dashboard({ d }) {
  const ref = useRef();
  useEffect(() => {
    if (!ref.current || !window.Chart || !d.cat_chart.length) return;
    window.Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-secondary') || '#666';
    const chart = new window.Chart(ref.current, {
      type: 'doughnut',
      data: { labels: d.cat_chart.map((x) => x.name), datasets: [{ data: d.cat_chart.map((x) => x.count),
        backgroundColor: chartPalette().categorical, borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } },
    });
    return () => chart.destroy();
  }, [d.cat_chart]);

  const kpis = [
    ['blue', 'fa-book', d.titles, 'Titles', d.urls.books],
    ['green', 'fa-layer-group', `${d.available}/${d.copies}`, 'Available', d.urls.books + '?avail=1'],
    ['amber', 'fa-hand-holding', d.on_loan, 'On loan', d.urls.loans + '?status=Borrowed'],
    ['red', 'fa-clock', d.overdue, 'Overdue', d.urls.loans + '?status=Overdue'],
    ['green', 'fa-arrow-up-from-bracket', d.issued_today, 'Issued today', null],
    ['green', 'fa-arrow-down-to-bracket', d.returned_today, 'Returned today', null],
    ['blue', 'fa-plus', d.added_month, 'Added this month', null],
    ['blue', 'fa-users', d.active_borrowers, 'Active borrowers', null],
    ['red', 'fa-triangle-exclamation', d.lost, 'Lost', d.urls.loans + '?status=Lost'],
    ['amber', 'fa-screwdriver-wrench', d.damaged, 'Damaged', d.urls.loans + '?status=Damaged'],
  ];
  const quick = [
    [d.urls.add_book, 'fa-plus', 'Register book', 'btn-primary'],
    [d.urls.issue, 'fa-hand-holding', 'Issue', 'btn-secondary'],
    [d.urls.loans + '?status=Borrowed', 'fa-rotate-left', 'Return', 'btn-secondary'],
    [d.urls.loans + '?status=Overdue', 'fa-clock', 'Overdue', 'btn-secondary'],
    [d.urls.books, 'fa-magnifying-glass', 'Search books', 'btn-secondary'],
    [d.urls.export, 'fa-file-csv', 'Export', 'btn-secondary', true],
  ];
  return (
    <>
      <PageHeader title="Library" actions={<>
        <a href={d.urls.issue} className="btn btn-primary"><i aria-hidden="true" className="fas fa-hand-holding" /> Issue Book</a>
        <a href={d.urls.add_book} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-plus" /> Add Book</a>
      </>} />
      <Tabs urls={d.urls} page="dashboard" />
      <div className="d-flex gap-2 flex-wrap mb-3">
        {quick.map(([href, ic, label, cls, native]) => (
          <a key={label} href={href} {...(native ? { 'data-native': true } : {})} className={'btn btn-sm ' + cls}><i aria-hidden="true" className={'fas ' + ic} /> {label}</a>))}
      </div>
      <div className="kpi-row">
        {kpis.map(([c, ic, v, l, href]) => {
          const inner = <><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
            <div><div className="v">{v}</div><div className="l">{l}</div></div></>;
          return href ? <a className="kpi" key={l} href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{inner}</a>
            : <div className="kpi" key={l}>{inner}</div>;
        })}
      </div>

      <div className="cm-grid split">
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-shapes" /> By category</h3></div>
          <div className="wb"><div className="chart-box">
            {d.cat_chart.length ? <canvas ref={ref} /> : <Empty icon="fa-book" title="No books yet" />}
          </div></div>
        </div>
        <div className="widget">
          <div className="wh"><h3><i aria-hidden="true" className="fas fa-fire" /> Most borrowed</h3></div>
          <div className="wb" style={{ padding: 0 }}>
            {(d.most_borrowed || []).length ? (
              <table className="data-table"><tbody>{d.most_borrowed.map((b, i) => (
                <tr key={i}><td>{b.title}</td><td className="text-right"><span className="badge badge-secondary">{b.count}</span></td></tr>))}
              </tbody></table>
            ) : <Empty icon="fa-fire" title="No loans yet" />}
          </div>
        </div>
      </div>

      <div className="widget">
        <div className="wh"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent loans</h3><a href={d.urls.loans} className="text-sm">View all</a></div>
        <div className="wb" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.recent}
            empty={<Empty icon="fa-hand-holding" title="No loans yet" />}
            columns={[
              { key: 'book', label: 'Book', render: (l) => l.book },
              { key: 'student', label: 'Borrower', render: (l) => <>{l.student}{l.borrower_type === 'staff' && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>Staff</span>}</> },
              { key: 'borrowed', label: 'Borrowed', render: (l) => l.borrowed },
              { key: 'due', label: 'Due', render: (l) => l.due },
              { key: 'status', label: 'Status', render: (l) => statusBadge(l) },
            ]} />
        </div>
      </div>
    </>
  );
}

// ---- Catalogue -------------------------------------------------------------
function Books({ d, notify }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [category, setCategory] = useState(d.category || '');
  const [subject, setSubject] = useState(d.subject || '');
  const [availOnly, setAvailOnly] = useState(d.avail === '1');
  const [busy, setBusy] = useState(false);
  const [reserving, setReserving] = useState(null);
  const fileRef = useRef();

  const del = async (b) => {
    if (!await confirm(`Remove ${b.title}?`)) return;
    setBusy(true);
    const r = await submitJson(b.delete_url, {});
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not remove the book.');
  };

  const onImport = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    const r = await postFile(d.urls.import, file);
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Imported.'); nav.refresh(); }
    else notify('error', r.error || 'Could not import that file.');
  };

  const shown = d.books.filter((b) =>
    (!q || (b.title + ' ' + (b.author || '') + ' ' + (b.isbn || '') + ' ' + (b.barcode || '') + ' ' + (b.subject || '')).toLowerCase().includes(q.toLowerCase()))
    && (!category || b.category === category)
    && (!subject || b.subject === subject)
    && (!availOnly || (b.copies_available > 0 && !b.reference_only)));

  return (
    <>
      <PageHeader title="Catalogue" actions={<>
        <input type="file" ref={fileRef} accept=".csv,text/csv" style={{ display: 'none' }} onChange={onImport} />
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}><i aria-hidden="true" className="fas fa-file-import" /> Import CSV</button>
        <a href={d.urls.export} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> Export</a>
        <a href={d.urls.add_book} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Book</a>
      </>} />
      <Tabs urls={d.urls} page="books" />
      {reserving && <ReserveModal d={d} book={reserving} onClose={() => setReserving(null)}
        onDone={(m) => { setReserving(null); notify('success', m); }} notify={notify} />}

      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Title, author, ISBN, barcode, subject" onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Subject</label>
            <select className="form-control" value={subject} onChange={(e) => setSubject(e.target.value)}>
              <option value="">All</option>{(d.subjects || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <label className="form-check"><input type="checkbox" checked={availOnly} onChange={(e) => setAvailOnly(e.target.checked)} /> Available only</label></div>
        </div>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>{shown.length} title(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(b) => b.id} rows={shown} pageSize={25} sticky maxHeight="65vh"
            empty={<Empty icon="fa-book" title="No books"><p>Add titles to the catalogue.</p><a href={d.urls.add_book} className="btn btn-primary mt-2">Add Book</a></Empty>}
            columns={[
              { key: 'title', label: 'Title', sortable: true, sortValue: (b) => b.title, render: (b) => <><strong>{b.title}</strong>{b.reference_only && <span className="badge badge-warning" style={{ marginLeft: '.3rem' }}>Reference</span>}{b.status === 'Withdrawn' && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>Withdrawn</span>}{(b.isbn || b.barcode) && <div className="text-muted text-sm">{b.isbn || b.barcode}</div>}</> },
              { key: 'author', label: 'Author', sortable: true, sortValue: (b) => b.author || '', render: (b) => b.author || '—' },
              { key: 'category', label: 'Category', render: (b) => <>{b.category && <span className="badge badge-secondary">{b.category}</span>}{b.subject && <span className="badge badge-secondary" style={{ marginLeft: '.2rem' }}>{b.subject}</span>}{!b.category && !b.subject && '—'}</> },
              { key: 'shelf', label: 'Shelf', render: (b) => [b.shelf, b.rack].filter(Boolean).join(' · ') || '—' },
              { key: 'avail', label: 'Avail/Total', align: 'right', render: (b) => <><span className={'badge ' + (b.copies_available ? 'badge-success' : 'badge-danger')}>{b.copies_available}</span> / {b.copies_total}</> },
              { key: 'act', label: '', render: (b) => (
                <div className="d-flex gap-1 justify-end">
                  {b.copies_available > 0 && !b.reference_only && <a href={b.issue_url} className="btn btn-primary btn-sm" title="Issue"><i aria-hidden="true" className="fas fa-hand-holding" /></a>}
                  {!b.reference_only && <button type="button" className="btn btn-secondary btn-sm" title="Reserve / hold" onClick={() => setReserving(b)}><i aria-hidden="true" className="fas fa-bookmark" /></button>}
                  <a href={b.edit_url} className="btn btn-secondary btn-sm" aria-label="Edit"><i aria-hidden="true" className="fas fa-edit" /></a>
                  {d.is_admin && <button type="button" className="btn btn-danger btn-sm" disabled={busy} onClick={() => del(b)}><i aria-hidden="true" className="fas fa-trash" /></button>}
                </div>) },
            ]} />
        </div>
      </div>
    </>
  );
}

// ---- Book form -------------------------------------------------------------
function BookForm({ d, notify }) {
  const nav = useNav();
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
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  // ── ISBN / barcode auto-fill ──────────────────────────────────────────────
  const [looking, setLooking] = useState(false);
  const [lookMsg, setLookMsg] = useState(null);
  const [dupes, setDupes] = useState([]);
  const fileRef = useRef(null);

  const applyMeta = (m) => setF((s) => {
    const next = { ...s };
    // Fill from the catalogue result, keeping anything the user already typed.
    ['title', 'subtitle', 'author', 'publisher', 'subject', 'keywords', 'description', 'language'].forEach((k) => {
      if (m[k] && !String(next[k] || '').trim()) next[k] = m[k];
    });
    if (m.publication_year && !next.publication_year) next.publication_year = m.publication_year;
    if (m.isbn) next.isbn = m.isbn;
    return next;
  });

  const doLookup = async (isbnArg) => {
    const isbn = (isbnArg != null ? isbnArg : f.isbn) || '';
    if (!isbn.trim()) { setLookMsg({ tone: 'warn', text: 'Enter or scan an ISBN first.' }); return; }
    setLooking(true); setLookMsg(null); setDupes([]);
    try {
      const res = await apiGet(`${d.urls.isbn_lookup}?isbn=${encodeURIComponent(isbn)}`);
      setDupes(res.existing || []);
      if (res.found) { applyMeta(res.book); setLookMsg({ tone: 'success', text: `Found via ${res.book.source}. Details filled in — review and save.` }); }
      else { set('isbn', res.isbn || isbn); setLookMsg({ tone: 'warn', text: 'Not in the online catalogues (common for locally-published Nigerian books). ISBN saved — just type the title and details, then save.' }); }
    } catch (e2) {
      setLookMsg({ tone: 'error', text: 'Lookup failed. Check the connection or type the details.' });
    } finally { setLooking(false); }
  };

  // Scan a barcode from a photo the user takes/uploads, using the browser's
  // native BarcodeDetector (no external library). A book's barcode is its
  // ISBN-13, so a hit feeds straight into the lookup.
  const scanSupported = typeof window !== 'undefined' && 'BarcodeDetector' in window;
  const onScanFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (!scanSupported) { setLookMsg({ tone: 'warn', text: 'Barcode scanning isn’t supported here — type the ISBN instead.' }); return; }
    setLookMsg({ tone: 'info', text: 'Reading barcode…' });
    try {
      const bitmap = await createImageBitmap(file);
      // eslint-disable-next-line no-undef
      const detector = new BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'code_128'] });
      const codes = await detector.detect(bitmap);
      if (codes && codes.length) { const code = codes[0].rawValue; set('isbn', code); doLookup(code); }
      else setLookMsg({ tone: 'warn', text: 'Couldn’t read a barcode — try a clearer photo or type the ISBN.' });
    } catch (e2) {
      setLookMsg({ tone: 'error', text: 'Could not read the image. Type the ISBN instead.' });
    }
  };

  const addCopies = async (dupe) => {
    const n = Number(await promptDialog({ title: 'Add copies',
      label: `How many copies of "${dupe.title}" to add?`, inputType: 'number', defaultValue: '1' }));
    if (!n || n <= 0) return;
    const r = await submitJson(dupe.add_copies_url, { count: n });
    if (r.ok) nav.go(d.urls.books); else notify('error', r.error || 'Could not add copies.');
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Title is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { ...f, reference_only: f.reference_only ? 'on' : '' });
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify('error', r.error || 'Could not save the book.');
  };

  return (
    <>
      <PageHeader title={editing ? 'Edit Book' : 'Add Book'} />

      {!editing && (
        <div className="card mb-3" style={{ borderColor: 'var(--primary)' }}>
          <div className="card-header"><h3><i aria-hidden="true" className="fas fa-barcode" /> Quick add by ISBN / barcode</h3></div>
          <div className="card-body">
            <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div className="form-group" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                <label className="form-label">ISBN</label>
                <input type="text" className="form-control" placeholder="Type or scan the 10/13-digit ISBN"
                       value={f.isbn} onChange={(e) => set('isbn', e.target.value)}
                       onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); doLookup(); } }} />
              </div>
              <button type="button" className="btn btn-primary" onClick={() => doLookup()} disabled={looking}>
                <i aria-hidden="true" className="fas fa-magnifying-glass" /> {looking ? 'Looking…' : 'Look up'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => fileRef.current && fileRef.current.click()}
                      title={scanSupported ? 'Take or upload a photo of the barcode' : 'Scanning not supported on this device'}>
                <i aria-hidden="true" className="fas fa-camera" /> Scan barcode
              </button>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={onScanFile} />
            </div>
            {lookMsg && <div className={'alert mt-2 alert-' + ({ success: 'success', error: 'danger', warn: 'warning', info: 'info' }[lookMsg.tone] || 'info')} role="status" style={{ marginBottom: 0, marginTop: '.6rem' }}>{lookMsg.text}</div>}
            {dupes.length > 0 && (
              <div className="alert alert-warning" role="status" style={{ marginTop: '.6rem', marginBottom: 0 }}>
                <strong><i aria-hidden="true" className="fas fa-circle-info" /> This title may already be in your catalogue.</strong>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem', marginTop: '.5rem' }}>
                  {dupes.map((b) => (
                    <div key={b.id} style={{ display: 'flex', gap: '.5rem', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                      <span>{b.title}{b.author ? ` · ${b.author}` : ''} <span className="text-muted text-sm">({b.copies_available}/{b.copies_total} available)</span></span>
                      <button type="button" className="btn btn-sm btn-primary" onClick={() => addCopies(b)}><i aria-hidden="true" className="fas fa-plus" /> Add copies to this one</button>
                    </div>
                  ))}
                </div>
                <div className="text-muted text-sm" style={{ marginTop: '.4rem' }}>Or just fill the form below to add it as a separate entry.</div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}><label className="form-label">Title <span className="required">*</span></label>
              <input type="text" className="form-control" required value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Subtitle</label>
              <input type="text" className="form-control" value={f.subtitle} onChange={(e) => set('subtitle', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Author(s)</label>
              <input type="text" className="form-control" value={f.author} onChange={(e) => set('author', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Publisher</label>
              <input type="text" className="form-control" value={f.publisher} onChange={(e) => set('publisher', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">ISBN</label>
              <input type="text" className="form-control" value={f.isbn} onChange={(e) => set('isbn', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Barcode / accession</label>
              <input type="text" className="form-control" placeholder="Scannable code" value={f.barcode} onChange={(e) => set('barcode', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Edition</label>
              <input type="text" className="form-control" value={f.edition} onChange={(e) => set('edition', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Year</label>
              <input type="number" className="form-control" value={f.publication_year} onChange={(e) => set('publication_year', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Category</label>
              <input type="text" className="form-control" list="lib-cats" placeholder="Textbook, Story, Reference…" value={f.category} onChange={(e) => set('category', e.target.value)} />
              <datalist id="lib-cats">{(d.categories || []).map((c) => <option key={c} value={c} />)}</datalist></div>
            <div className="form-group"><label className="form-label">Subject</label>
              <input type="text" className="form-control" list="lib-subs" placeholder="Mathematics, English…" value={f.subject} onChange={(e) => set('subject', e.target.value)} />
              <datalist id="lib-subs">{(d.subjects || []).map((c) => <option key={c} value={c} />)}</datalist></div>
            <div className="form-group"><label className="form-label">Language</label>
              <input type="text" className="form-control" value={f.language} onChange={(e) => set('language', e.target.value)} /></div>
          </div>
          <div className="form-group"><label className="form-label">Keywords</label>
            <input type="text" className="form-control" placeholder="Comma-separated, searchable" value={f.keywords} onChange={(e) => set('keywords', e.target.value)} /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Shelf</label>
              <input type="text" className="form-control" value={f.shelf} onChange={(e) => set('shelf', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Rack / row</label>
              <input type="text" className="form-control" value={f.rack} onChange={(e) => set('rack', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Condition</label>
              <select className="form-control" value={f.condition} onChange={(e) => set('condition', e.target.value)}>{['Good', 'Fair', 'Poor'].map((x) => <option key={x} value={x}>{x}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Unit price (₦)</label>
              <input type="number" className="form-control" min="0" step="0.01" value={f.price} onChange={(e) => set('price', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Total copies</label>
              <input type="number" className="form-control" min="0" value={f.copies_total} onChange={(e) => set('copies_total', e.target.value)} />
              {editing && <span className="form-hint d-block">{b.copies_available} available · {b.on_loan} on loan</span>}</div>
            <div className="form-group"><label className="form-label">Status</label>
              <select className="form-control" value={f.status} onChange={(e) => set('status', e.target.value)}>{['Available', 'Withdrawn'].map((x) => <option key={x} value={x}>{x}</option>)}</select></div>
            <div className="form-group" style={{ alignSelf: 'center' }}><label className="form-check" title="Reference books stay in the library and can't be borrowed"><input type="checkbox" checked={f.reference_only} onChange={(e) => set('reference_only', e.target.checked)} /> Reference-only</label></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Acquired via</label>
              <select className="form-control" value={f.source} onChange={(e) => set('source', e.target.value)}>{['Purchase', 'Donation'].map((x) => <option key={x} value={x}>{x}</option>)}</select></div>
            <div className="form-group"><label className="form-label">Supplier / vendor</label>
              <input type="text" className="form-control" value={f.supplier} onChange={(e) => set('supplier', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Donated by</label>
              <input type="text" className="form-control" placeholder="Donor name (if a donation)" value={f.donated_by} onChange={(e) => set('donated_by', e.target.value)} /></div>
          </div>
          <div className="form-group"><label className="form-label">Description</label>
            <textarea className="form-control" rows="2" value={f.description} onChange={(e) => set('description', e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Notes</label>
            <textarea className="form-control" rows="2" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></div>
          <div className="page-header-actions">
            <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> {editing ? 'Save' : 'Add Book'}</button>
            <a href={d.urls.books} className="btn btn-secondary">Cancel</a>
          </div>
        </form>
      </div></div>
    </>
  );
}

// ---- Issue -----------------------------------------------------------------
function Issue({ d, notify }) {
  const nav = useNav();
  const [bookId, setBookId] = useState(d.preset ? String(d.preset.id) : '');
  const [borrowerType, setBorrowerType] = useState('student');
  const [studentId, setStudentId] = useState('');
  const [staffId, setStaffId] = useState('');
  const [due, setDue] = useState(d.default_due);
  const [busy, setBusy] = useState(false);
  const [scan, setScan] = useState('');
  const [scanned, setScanned] = useState(d.preset ? d.preset.title : '');

  const lookupBarcode = async (code) => {
    if (!code.trim()) return;
    try {
      const r = await fetch(d.urls.barcode_lookup + '?code=' + encodeURIComponent(code.trim()), { credentials: 'same-origin' });
      const j = await r.json();
      if (j.ok) { setBookId(String(j.book.id)); setScanned(j.book.title + (j.book.reference_only ? ' (reference-only)' : ` · ${j.book.available} available`)); }
      else notify('error', 'No book matches that barcode/ISBN.');
    } catch (_) { /* ignore */ }
  };

  const submit = async (e) => {
    e.preventDefault();
    const borrowerId = borrowerType === 'staff' ? staffId : studentId;
    if (!bookId || !borrowerId) { notify('error', 'Select a book and a borrower.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { book_id: bookId, borrower_type: borrowerType,
      student_id: borrowerType === 'student' ? studentId : '', staff_id: borrowerType === 'staff' ? staffId : '',
      due_date: due });
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify('error', r.error || 'Could not issue the book.');
  };

  return (
    <>
      <PageHeader title="Issue Book" />
      <Tabs urls={d.urls} page="issue" />
      <div className="card" style={{ maxWidth: 640 }}><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Scan barcode / ISBN</label>
            <div className="d-flex gap-2">
              <input type="text" className="form-control" value={scan} placeholder="Scan or type a code, then Enter"
                     onChange={(e) => setScan(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); lookupBarcode(scan); } }} />
              <button type="button" className="btn btn-secondary" onClick={() => lookupBarcode(scan)}><i aria-hidden="true" className="fas fa-barcode" /></button>
            </div>
            {scanned && <span className="form-hint d-block"><i aria-hidden="true" className="fas fa-check text-success" /> {scanned}</span>}</div>
          <Autocomplete label="…or search the book" required={!bookId} url={d.urls.book_search} placeholder="Search title / author / ISBN…"
                        initialText={d.preset ? d.preset.title : ''} onPick={(id) => { setBookId(id); }} />

          <div className="borrower-toggle" role="tablist">
            {[['student', 'fa-user-graduate', 'Student'], ['staff', 'fa-user-tie', 'Staff']].map(([v, ic, lab]) => (
              <button type="button" key={v} role="tab" aria-selected={borrowerType === v}
                className={borrowerType === v ? 'on' : ''} onClick={() => setBorrowerType(v)}><i aria-hidden="true" className={'fas ' + ic} /> {lab}</button>))}
          </div>
          {borrowerType === 'student'
            ? <Autocomplete label="Student" required url={d.urls.student_search} placeholder="Search name / student ID…" onPick={setStudentId} />
            : <Autocomplete label="Staff" required url={d.urls.staff_search} placeholder="Search name / staff ID…" onPick={setStaffId} />}

          <div className="form-group"><label className="form-label">Due date</label>
            <input type="date" className="form-control" value={due} onChange={(e) => setDue(e.target.value)} />
            <span className="form-hint d-block">Default loan period is {d.settings.loan_days} days{d.settings.fine_per_day ? ` · ₦${d.settings.fine_per_day}/day overdue fine` : ''}.</span></div>
          <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-hand-holding" /> Issue Book</button>
        </form>
      </div></div>
    </>
  );
}

// ---- Loans -----------------------------------------------------------------
function Loans({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    setBusy(true);
    const r = await submitJson(url, fields || {});
    setBusy(false);
    if (r.ok) { if (r.message) notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const ret = (l) => {
    const overdue = l.is_overdue && d.settings && d.settings.fine_per_day;
    // Offer to waive when the return carries a fine.
    if (overdue) {
      confirm(`'${l.book}' is ${l.days_overdue} day(s) late. Return and CHARGE the fine? (Cancel to waive it.)`)
        .then((charge) => act(l.return_url, charge ? {} : { waive: '1' }));
    } else {
      act(l.return_url, {}, `Mark '${l.book}' as returned?`);
    }
  };
  const markLost = async (l) => {
    const cost = await promptDialog({ title: `Mark '${l.book}' as lost`,
      label: 'Replacement cost to bill the borrower (₦)', placeholder: 'Blank = book price',
      inputType: 'number', required: false });
    if (cost === null) return;
    act(l.mark_url, { kind: 'Lost', cost });
  };
  const markDamaged = async (l) => {
    const cost = await promptDialog({ title: `Mark '${l.book}' as damaged`,
      label: 'Charge to the borrower (₦)', placeholder: 'Blank = book price',
      inputType: 'number', required: false });
    if (cost === null) return;
    act(l.mark_url, { kind: 'Damaged', cost });
  };
  const onStatus = (v) => { nav.go(d.urls.loans + '?status=' + v); };
  const remind = async () => {
    if (!await confirm('Draft an SMS reminder to the parents of students with overdue books? Nothing sends until you review it in Communication.')) return;
    const r = await submitJson(d.urls.remind_overdue, {});
    if (r.ok) { notify('success', r.message); if (r.redirect) nav.go(r.redirect); }
    else notify('error', r.error || 'Could not draft reminders.');
  };

  return (
    <>
      <PageHeader title="Loans" actions={<>
        {d.status === 'Overdue' && <button type="button" className="btn btn-secondary" onClick={remind}><i aria-hidden="true" className="fas fa-comment-sms" /> Remind parents</button>}
        <a href={d.urls.issue} className="btn btn-primary"><i aria-hidden="true" className="fas fa-hand-holding" /> Issue Book</a></>} />
      <Tabs urls={d.urls} page="loans" />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form"><div className="form-group"><label className="form-label">Show</label>
          <select className="form-control" value={d.status} onChange={(e) => onStatus(e.target.value)}>
            {['Borrowed', 'Overdue', 'Returned', 'Lost', 'Damaged'].map((s) => <option key={s} value={s}>{s}</option>)}
            <option value="all">All</option>
          </select></div></div>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>{d.loans.length} loan(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.loans} pageSize={25} sticky maxHeight="65vh"
            empty={<Empty icon="fa-rotate-left" title="No loans"><p>Nothing matches this filter.</p></Empty>}
            columns={[
              { key: 'book', label: 'Book', sortable: true, sortValue: (l) => l.book, render: (l) => l.book },
              { key: 'student', label: 'Borrower', sortable: true, sortValue: (l) => l.student, render: (l) => <>{l.borrower_url ? <a href={l.borrower_url}>{l.student}</a> : l.student}{l.borrower_type === 'staff' && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>Staff</span>}{l.borrower_ref && <div className="text-muted text-sm">{l.borrower_ref}</div>}</> },
              { key: 'borrowed', label: 'Borrowed', render: (l) => l.borrowed },
              { key: 'due', label: 'Due', render: (l) => <>{l.due}{l.is_overdue && <span className="text-danger text-sm"> ({l.days_overdue}d late)</span>}{l.renew_count > 0 && <span className="text-muted text-sm"> · renewed ×{l.renew_count}</span>}</> },
              { key: 'status', label: 'Status', render: (l) => statusBadge(l) },
              { key: 'fine', label: 'Fine / cost', render: (l) => (l.fine || l.replacement_cost) ? naira(l.fine || l.replacement_cost) : '—' },
              { key: 'act', label: '', render: (l) => l.status === 'Borrowed'
                ? <div className="d-flex gap-1 justify-end">
                    <button type="button" className="btn btn-primary btn-sm" disabled={busy} title="Return" onClick={() => ret(l)}><i aria-hidden="true" className="fas fa-rotate-left" /></button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} title="Renew" onClick={() => act(l.renew_url, {})}><i aria-hidden="true" className="fas fa-arrows-rotate" /></button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} title="Mark lost" onClick={() => markLost(l)}><i aria-hidden="true" className="fas fa-triangle-exclamation" /></button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} title="Mark damaged" onClick={() => markDamaged(l)}><i aria-hidden="true" className="fas fa-screwdriver-wrench" /></button>
                  </div>
                : <span className="text-muted text-sm">{l.returned}</span> },
            ]} />
        </div>
      </div>
    </>
  );
}

// ---- Settings --------------------------------------------------------------
function Settings({ d, notify }) {
  const [loanDays, setLoanDays] = useState(d.settings.loan_days);
  const [fine, setFine] = useState(d.settings.fine_per_day);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const r = await submitJson(d.submit_url, { loan_days: loanDays, fine_per_day: fine });
    setBusy(false);
    if (r.ok) notify('success', r.message || 'Saved.');
    else notify('error', r.error || 'Could not save.');
  };
  return (
    <>
      <PageHeader title="Library Settings" />
      <Tabs urls={d.urls} page="settings" />
      <div className="card" style={{ maxWidth: 560 }}>
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-gear" /> Loan rules</h3></div>
        <div className="card-body">
          <form onSubmit={submit}>
            <div className="form-row">
              <div className="form-group"><label className="form-label">Loan period (days)</label>
                <input type="number" className="form-control" min="1" value={loanDays} onChange={(e) => setLoanDays(e.target.value)} /></div>
              <div className="form-group"><label className="form-label">Overdue fine (₦ per day)</label>
                <input type="number" className="form-control" min="0" step="1" value={fine} onChange={(e) => setFine(e.target.value)} />
                <span className="form-hint d-block">0 to disable fines.</span></div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-save" /> Save</button>
          </form>
        </div>
      </div>
    </>
  );
}

// ---- Reports ---------------------------------------------------------------
function Reports({ d }) {
  const nav = useNav();
  const sel = d.sel || {};
  const rep = d.report || { columns: [], rows: [], summary: [], title: '' };
  const [from, setFrom] = useState(sel.from || '');
  const [to, setTo] = useState(sel.to || '');
  const [category, setCategory] = useState(sel.category || '');
  const [subject, setSubject] = useState(sel.subject || '');
  const params = (extra) => ({ type: sel.type, from, to, category, subject, ...extra });
  const go = (extra) => navParams(nav.go, d.urls.self, params(extra));
  const qs = () => Object.entries(params({})).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const cell = (col, row) => {
    const v = row[col.key];
    if (col.money) return typeof v === 'number' ? naira(v) : v;
    return (v === '' || v == null) ? '—' : v;
  };
  return (
    <>
      <PageHeader title="Reports" actions={<>
        <a href={`${d.urls.export}?format=csv&${qs()}`} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> CSV</a>
        <a href={`${d.urls.export}?format=xlsx&${qs()}`} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-excel" /> Excel</a>
      </>} />
      <Tabs urls={d.urls} page="reports" />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Report</label>
            <select className="form-control" value={sel.type} onChange={(e) => go({ type: e.target.value })}>
              {d.report_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></div>
          <div className="form-group"><label className="form-label">From</label>
            <input type="date" className="form-control" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">To</label>
            <input type="date" className="form-control" value={to} onChange={(e) => setTo(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group"><label className="form-label">Subject</label>
            <select className="form-control" value={subject} onChange={(e) => setSubject(e.target.value)}>
              <option value="">All</option>{(d.subjects || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <button type="button" className="btn btn-primary" onClick={() => go({})}><i aria-hidden="true" className="fas fa-filter" /> Apply</button></div>
        </div>
      </div></div>

      {rep.summary && rep.summary.length > 0 && (
        <div className="kpi-row" style={{ gridTemplateColumns: `repeat(${Math.min(rep.summary.length, 4)}, 1fr)` }}>
          {rep.summary.map((s, i) => (
            <div className="kpi" key={i}><div className="ic blue"><i aria-hidden="true" className="fas fa-chart-simple" /></div>
              <div><div className="v" style={{ fontSize: '1.15rem' }}>{s.value}</div><div className="l">{s.label}</div></div></div>))}
        </div>)}

      <div className="card">
        <div className="card-header"><h3>{rep.title} · {rep.rows.length} row(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(r, i) => i} rows={rep.rows} pageSize={50} sticky maxHeight="60vh"
            empty={<Empty icon="fa-chart-line" title="No data"><p>Nothing matches these filters.</p></Empty>}
            columns={rep.columns.map((col) => ({ key: col.key, label: col.label, align: col.align,
              render: (r) => cell(col, r) }))} />
        </div>
      </div>
    </>
  );
}

// ---- Borrowers directory ---------------------------------------------------
function Borrowers({ d }) {
  const nav = useNav();
  const [q, setQ] = useState(d.q || '');
  const [type, setType] = useState(d.type || '');
  const shown = d.borrowers.filter((b) =>
    (!type || b.type === type)
    && (!q || (b.name + ' ' + b.ref + ' ' + (b.class || '')).toLowerCase().includes(q.toLowerCase())));
  return (
    <>
      <PageHeader title="Borrowers" />
      <Tabs urls={d.urls} page="borrowers" />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Name, ID, class" onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Type</label>
            <select className="form-control" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All</option><option value="student">Students</option><option value="staff">Staff</option></select></div>
        </div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>{shown.length} borrower(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(b) => b.type + b.id} rows={shown} pageSize={30} sticky maxHeight="65vh"
            empty={<Empty icon="fa-users" title="No borrowers yet"><p>Loans appear here once books are issued.</p></Empty>}
            columns={[
              { key: 'name', label: 'Borrower', sortable: true, sortValue: (b) => b.name, render: (b) => <><a href={b.url}><strong>{b.name}</strong></a>{b.type === 'staff' && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>Staff</span>}<div className="text-muted text-sm">{b.ref}{b.class ? ` · ${b.class}` : ''}</div></> },
              { key: 'active', label: 'Out now', align: 'right', sortable: true, sortValue: (b) => b.active, render: (b) => b.active || '—' },
              { key: 'overdue', label: 'Overdue', align: 'right', render: (b) => b.overdue ? <span className="badge badge-danger">{b.overdue}</span> : '—' },
              { key: 'total', label: 'Total loans', align: 'right', sortable: true, sortValue: (b) => b.total, render: (b) => b.total },
              { key: 'act', label: '', render: (b) => <a href={b.url} className="btn btn-secondary btn-sm" aria-label="History"><i aria-hidden="true" className="fas fa-arrow-right" /></a> },
            ]} />
        </div>
      </div>
    </>
  );
}

// ---- Borrower history ------------------------------------------------------
function Borrower({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const b = d.borrower;
  const act = async (url, fields, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    setBusy(true);
    const r = await submitJson(url, fields || {});
    setBusy(false);
    if (r.ok) { if (r.message) notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const s = d.stats;
  const kpis = [['blue', 'fa-book', s.total, 'Total loans'], ['amber', 'fa-hand-holding', s.out, 'Out now'],
    ['red', 'fa-clock', s.overdue, 'Overdue'], ['red', 'fa-triangle-exclamation', s.lost + s.damaged, 'Lost/damaged']];
  const loanCols = (withActions) => [
    { key: 'book', label: 'Book', render: (l) => l.book },
    { key: 'borrowed', label: 'Borrowed', render: (l) => l.borrowed },
    { key: 'due', label: 'Due', render: (l) => <>{l.due}{l.is_overdue && <span className="text-danger text-sm"> ({l.days_overdue}d)</span>}</> },
    { key: 'status', label: 'Status', render: (l) => statusBadge(l) },
    ...(withActions ? [{ key: 'act', label: '', render: (l) => (
      <div className="d-flex gap-1 justify-end">
        <button type="button" className="btn btn-primary btn-sm" disabled={busy} title="Return" onClick={() => act(l.return_url, {}, `Return '${l.book}'?`)}><i aria-hidden="true" className="fas fa-rotate-left" /></button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={busy} title="Renew" onClick={() => act(l.renew_url, {})}><i aria-hidden="true" className="fas fa-arrows-rotate" /></button>
      </div>) }] : [{ key: 'closed', label: '', render: (l) => <span className="text-muted text-sm">{l.returned}{l.fine ? ` · ${naira(l.fine)}` : ''}{l.replacement_cost ? ` · ${naira(l.replacement_cost)}` : ''}</span> }]),
  ];
  return (
    <>
      <PageHeader title={b.name} actions={<a href={d.urls.back} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Borrowers</a>} />
      <div className="text-muted mb-3">{b.type === 'staff' ? 'Staff' : 'Student'}{b.ref ? ` · ${b.ref}` : ''}{b.class ? ` · ${b.class}` : ''}{s.fines ? ` · fines/costs ${naira(s.fines)}` : ''}</div>
      <div className="kpi-row">{kpis.map(([c, ic, v, l]) => (
        <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
          <div><div className="v">{v}</div><div className="l">{l}</div></div></div>))}
      </div>
      <div className="card mb-3"><div className="card-header"><h3>Current loans ({d.current.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.current} empty={<Empty icon="fa-hand-holding" title="Nothing out" />} columns={loanCols(true)} />
        </div></div>
      <div className="card"><div className="card-header"><h3>Past loans ({d.past.length})</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.past} pageSize={20} empty={<Empty icon="fa-clock-rotate-left" title="No history" />} columns={loanCols(false)} />
        </div></div>
    </>
  );
}

// ---- Reserve modal ---------------------------------------------------------
function ReserveModal({ d, book, onClose, onDone, notify }) {
  const [borrowerType, setBorrowerType] = useState('student');
  const [studentId, setStudentId] = useState('');
  const [staffId, setStaffId] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    const borrowerId = borrowerType === 'staff' ? staffId : studentId;
    if (!borrowerId) { notify('error', 'Choose a borrower.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.reserve, { book_id: book.id, borrower_type: borrowerType,
      student_id: borrowerType === 'student' ? studentId : '', staff_id: borrowerType === 'staff' ? staffId : '' });
    setBusy(false);
    if (r.ok) onDone(r.message || 'Reserved.');
    else notify('error', r.error || 'Could not reserve.');
  };
  return (
    <Modal title={`Reserve “${book.title}”`} icon="fa-bookmark" size="sm" onClose={onClose}
           footer={<>
             <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
             <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}><i aria-hidden="true" className="fas fa-bookmark" /> Reserve</button>
           </>}>
      <form onSubmit={submit}>
        <p className="text-muted text-sm">{book.copies_available > 0
          ? 'A copy is free — this hold will be ready to collect immediately.'
          : 'No copy is free — the borrower joins the queue and is promoted when one is returned.'}</p>
        <div className="borrower-toggle" role="tablist">
          {[['student', 'fa-user-graduate', 'Student'], ['staff', 'fa-user-tie', 'Staff']].map(([v, ic, lab]) => (
            <button type="button" key={v} role="tab" aria-selected={borrowerType === v}
              className={borrowerType === v ? 'on' : ''} onClick={() => setBorrowerType(v)}><i aria-hidden="true" className={'fas ' + ic} /> {lab}</button>))}
        </div>
        {borrowerType === 'student'
          ? <Autocomplete label="Student" required url={d.urls.student_search} placeholder="Search name / student ID…" onPick={setStudentId} />
          : <Autocomplete label="Staff" required url={d.urls.staff_search} placeholder="Search name / staff ID…" onPick={setStaffId} />}
      </form>
    </Modal>
  );
}

// ---- Reservations ----------------------------------------------------------
function Reservations({ d, notify }) {
  const nav = useNav();
  const [busy, setBusy] = useState(false);
  const act = async (url, confirmMsg) => {
    if (confirmMsg && !await confirm(confirmMsg)) return;
    setBusy(true);
    const r = await submitJson(url, {});
    setBusy(false);
    if (r.ok) { if (r.message) notify('success', r.message); nav.refresh(); }
    else notify('error', r.error || 'Action failed.');
  };
  const onStatus = (v) => nav.go(d.urls.reservations + '?status=' + v);
  const resBadge = (s) => {
    const map = { Ready: 'badge-success', Queued: 'badge-warning', Fulfilled: 'badge-secondary', Cancelled: 'badge-secondary', Expired: 'badge-danger' };
    return <span className={'badge ' + (map[s] || 'badge-secondary')}>{s}</span>;
  };
  return (
    <>
      <PageHeader title="Reservations" />
      <Tabs urls={d.urls} page="reservations" />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form"><div className="form-group"><label className="form-label">Show</label>
          <select className="form-control" value={d.status} onChange={(e) => onStatus(e.target.value)}>
            <option value="open">Open (queued + ready)</option>
            {['Queued', 'Ready', 'Fulfilled', 'Cancelled', 'Expired'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div></div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>{d.reservations.length} reservation(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(r) => r.id} rows={d.reservations} pageSize={30} sticky maxHeight="65vh"
            empty={<Empty icon="fa-bookmark" title="No reservations"><p>Holds placed from the catalogue appear here.</p></Empty>}
            columns={[
              { key: 'book', label: 'Book', sortable: true, sortValue: (r) => r.book, render: (r) => r.book },
              { key: 'borrower', label: 'For', render: (r) => <>{r.borrower}{r.borrower_type === 'staff' && <span className="badge badge-secondary" style={{ marginLeft: '.3rem' }}>Staff</span>}</> },
              { key: 'created', label: 'Placed', render: (r) => r.created },
              { key: 'status', label: 'Status', render: (r) => <>{resBadge(r.status)}{r.status === 'Ready' && r.expires && <div className="text-muted text-sm">expires {r.expires}</div>}</> },
              { key: 'act', label: '', render: (r) => (r.status === 'Queued' || r.status === 'Ready')
                ? <div className="d-flex gap-1 justify-end">
                    {r.available > 0 && <button type="button" className="btn btn-primary btn-sm" disabled={busy} title="Issue now" onClick={() => act(r.fulfill_url, `Issue “${r.book}” to ${r.borrower}?`)}><i aria-hidden="true" className="fas fa-hand-holding" /></button>}
                    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} title="Cancel" onClick={() => act(r.cancel_url, 'Cancel this reservation?')}><i aria-hidden="true" className="fas fa-xmark" /></button>
                  </div>
                : '—' },
            ]} />
        </div>
      </div>
    </>
  );
}

// ---- Reading lists ---------------------------------------------------------
function ReadingLists({ d, notify }) {
  const nav = useNav();
  const [classId, setClassId] = useState(d.class_id ? String(d.class_id) : '');
  const [bookId, setBookId] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const bookRef = useRef(0);
  const add = async (e) => {
    e.preventDefault();
    if (!classId || !bookId) { notify('error', 'Pick a class and a book.'); return; }
    setBusy(true);
    const r = await submitJson(d.urls.add, { class_id: classId, book_id: bookId, note });
    setBusy(false);
    if (r.ok) { notify('success', r.message || 'Added.'); setBookId(''); setNote(''); bookRef.current += 1; nav.refresh(); }
    else notify('error', r.error || 'Could not add.');
  };
  const remove = async (it) => {
    if (!await confirm(`Remove “${it.book}” from ${it.class}?`)) return;
    setBusy(true);
    const r = await submitJson(it.remove_url, {});
    setBusy(false);
    if (r.ok) nav.refresh(); else notify('error', r.error || 'Could not remove.');
  };
  const onClassFilter = (v) => nav.go(v ? d.urls.self + '?class_id=' + v : d.urls.self);
  return (
    <>
      <PageHeader title="Reading lists" />
      <Tabs urls={d.urls} page="reading_lists" />
      <div className="card mb-3">
        <div className="card-header"><h3><i aria-hidden="true" className="fas fa-plus" /> Recommend a book to a class</h3></div>
        <div className="card-body">
          <form onSubmit={add}><div className="form-row">
            <div className="form-group"><label className="form-label">Class <span className="required">*</span></label>
              <select className="form-control" value={classId} onChange={(e) => setClassId(e.target.value)}>
                <option value="">Select…</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="form-group" style={{ flex: 2 }}>
              <Autocomplete key={bookRef.current} label="Book" required url={d.urls.book_search} placeholder="Search title / author / ISBN…" onPick={setBookId} /></div>
            <div className="form-group" style={{ flex: 2 }}><label className="form-label">Note</label>
              <input type="text" className="form-control" placeholder="Optional (e.g. Term 1 core text)" value={note} onChange={(e) => setNote(e.target.value)} /></div>
            <div className="form-group" style={{ alignSelf: 'flex-end' }}>
              <button type="submit" className="btn btn-primary" disabled={busy}><i aria-hidden="true" className="fas fa-plus" /> Add</button></div>
          </div></form>
        </div>
      </div>
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form"><div className="form-group"><label className="form-label">Filter by class</label>
          <select className="form-control" value={d.class_id || ''} onChange={(e) => onClassFilter(e.target.value)}>
            <option value="">All classes</option>{d.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div></div>
      </div></div>
      <div className="card">
        <div className="card-header"><h3>{d.items.length} recommendation(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(it) => it.id} rows={d.items} pageSize={30} sticky maxHeight="60vh"
            empty={<Empty icon="fa-list-check" title="No recommendations yet"><p>Add books above to build class reading lists.</p></Empty>}
            columns={[
              { key: 'class', label: 'Class', sortable: true, sortValue: (it) => it.class, render: (it) => <span className="badge badge-secondary">{it.class}</span> },
              { key: 'book', label: 'Book', sortable: true, sortValue: (it) => it.book, render: (it) => <><strong>{it.book}</strong>{it.author && <div className="text-muted text-sm">{it.author}</div>}</> },
              { key: 'note', label: 'Note', render: (it) => it.note || '—' },
              { key: 'by', label: 'Added by', render: (it) => it.by || '—' },
              { key: 'act', label: '', render: (it) => <button type="button" className="btn btn-danger btn-sm" disabled={busy} aria-label="Remove" onClick={() => remove(it)}><i aria-hidden="true" className="fas fa-trash" /></button> },
            ]} />
        </div>
      </div>
    </>
  );
}

const SCREENS = { dashboard: Dashboard, books: Books, book_form: BookForm, issue: Issue, loans: Loans, reservations: Reservations, borrowers: Borrowers, borrower: Borrower, reading_lists: ReadingLists, reports: Reports, settings: Settings };

export default function LibraryApp({ data }) {
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
