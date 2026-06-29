import React, { useState, useEffect, useRef } from 'react';
import { submitJson } from '../lib/forms';
import { naira } from '../lib/format';
import { useSection, NavCtx, useNav } from '../lib/section';
import { confirm, Banner, PageHeader, Empty, SectionTabs, Autocomplete, SectionShell, Table } from '../components/ui';

const TABS = [
  ['dashboard', 'fa-chart-pie', 'Overview'],
  ['books', 'fa-book', 'Catalogue'],
  ['issue', 'fa-hand-holding', 'Issue'],
  ['loans', 'fa-rotate-left', 'Loans'],
  ['settings', 'fa-gear', 'Settings'],
];
const ACTIVE = { dashboard: 'dashboard', books: 'books', book_form: 'books', issue: 'issue', loans: 'loans', settings: 'settings' };
const Tabs = ({ urls, page }) => { const { go } = useNav(); return <SectionTabs tabs={TABS} urls={urls} active={ACTIVE[page]} go={go} />; };

function statusBadge(l) {
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
        backgroundColor: ['#4e73df', '#1cc88a', '#f6c23e', '#e74a3b', '#7e6cf0', '#11998e', '#fd7e14', '#20c997'], borderWidth: 0 }] },
      options: { maintainAspectRatio: false, cutout: '58%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } } },
    });
    return () => chart.destroy();
  }, [d.cat_chart]);

  const kpis = [
    ['blue', 'fa-book', d.titles, 'Titles'],
    ['green', 'fa-layer-group', `${d.available}/${d.copies}`, 'Available'],
    ['amber', 'fa-hand-holding', d.on_loan, 'On loan'],
    ['red', 'fa-clock', d.overdue, 'Overdue'],
  ];
  return (
    <>
      <PageHeader title="Library" actions={<>
        <a href={d.urls.issue} className="btn btn-primary"><i aria-hidden="true" className="fas fa-hand-holding" /> Issue Book</a>
        <a href={d.urls.add_book} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-plus" /> Add Book</a>
      </>} />
      <Tabs urls={d.urls} page="dashboard" />
      <div className="kpi-row">
        {kpis.map(([c, ic, v, l]) => (
          <div className="kpi" key={l}><div className={'ic ' + c}><i aria-hidden="true" className={'fas ' + ic} /></div>
            <div><div className="v">{v}</div><div className="l">{l}</div></div></div>
        ))}
      </div>

      <div className="widget">
        <div className="wh"><h3><i aria-hidden="true" className="fas fa-shapes" /> By category</h3></div>
        <div className="wb"><div className="chart-box">
          {d.cat_chart.length ? <canvas ref={ref} /> : <Empty icon="fa-book" title="No books yet" />}
        </div></div>
      </div>

      <div className="widget">
        <div className="wh"><h3><i aria-hidden="true" className="fas fa-clock-rotate-left" /> Recent loans</h3><a href={d.urls.loans} className="text-sm">View all</a></div>
        <div className="wb" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.recent}
            empty={<Empty icon="fa-hand-holding" title="No loans yet" />}
            columns={[
              { key: 'book', label: 'Book', render: (l) => l.book },
              { key: 'student', label: 'Student', render: (l) => l.student },
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
  const [availOnly, setAvailOnly] = useState(d.avail === '1');
  const [busy, setBusy] = useState(false);

  const del = async (b) => {
    if (!await confirm(`Remove ${b.title}?`)) return;
    setBusy(true);
    const r = await submitJson(b.delete_url, {});
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not remove the book.');
  };

  const shown = d.books.filter((b) =>
    (!q || (b.title + ' ' + (b.author || '') + ' ' + (b.isbn || '')).toLowerCase().includes(q.toLowerCase()))
    && (!category || b.category === category)
    && (!availOnly || b.copies_available > 0));

  return (
    <>
      <PageHeader title="Catalogue" actions={<>
        <a href={d.urls.export} data-native className="btn btn-secondary"><i aria-hidden="true" className="fas fa-file-csv" /> Export</a>
        <a href={d.urls.add_book} className="btn btn-primary"><i aria-hidden="true" className="fas fa-plus" /> Add Book</a>
      </>} />
      <Tabs urls={d.urls} page="books" />

      <div className="card mb-3"><div className="card-body">
        <div className="filter-form">
          <div className="form-group"><label className="form-label">Search</label>
            <input type="text" className="form-control" value={q} placeholder="Title, author, ISBN" onChange={(e) => setQ(e.target.value)} /></div>
          <div className="form-group"><label className="form-label">Category</label>
            <select className="form-control" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>{d.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <label className="form-check"><input type="checkbox" checked={availOnly} onChange={(e) => setAvailOnly(e.target.checked)} /> Available only</label></div>
        </div>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>{shown.length} title(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(b) => b.id} rows={shown}
            empty={<Empty icon="fa-book" title="No books"><p>Add titles to the catalogue.</p><a href={d.urls.add_book} className="btn btn-primary mt-2">Add Book</a></Empty>}
            columns={[
              { key: 'title', label: 'Title', render: (b) => <><strong>{b.title}</strong>{b.isbn && <div className="text-muted text-sm">{b.isbn}</div>}</> },
              { key: 'author', label: 'Author', render: (b) => b.author || '—' },
              { key: 'category', label: 'Category', render: (b) => b.category ? <span className="badge badge-secondary">{b.category}</span> : '—' },
              { key: 'shelf', label: 'Shelf', render: (b) => b.shelf || '—' },
              { key: 'avail', label: 'Avail/Total', align: 'right', render: (b) => <><span className={'badge ' + (b.copies_available ? 'badge-success' : 'badge-danger')}>{b.copies_available}</span> / {b.copies_total}</> },
              { key: 'act', label: '', render: (b) => (
                <div className="d-flex gap-1 justify-end">
                  {b.copies_available > 0 && <a href={b.issue_url} className="btn btn-primary btn-sm" title="Issue"><i aria-hidden="true" className="fas fa-hand-holding" /></a>}
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
  const [f, setF] = useState({
    title: b.title || '', author: b.author || '', isbn: b.isbn || '', category: b.category || '',
    publisher: b.publisher || '', shelf: b.shelf || '', copies_total: b.copies_total != null ? b.copies_total : 1, notes: b.notes || '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!f.title.trim()) { notify('error', 'Title is required.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, f);
    setBusy(false);
    if (r.ok) nav.go(r.redirect);
    else notify('error', r.error || 'Could not save the book.');
  };

  return (
    <>
      <PageHeader title={editing ? 'Edit Book' : 'Add Book'} />
      <div className="card"><div className="card-body">
        <form onSubmit={submit}>
          <div className="form-group"><label className="form-label">Title <span className="required">*</span></label>
            <input type="text" className="form-control" required value={f.title} onChange={(e) => set('title', e.target.value)} /></div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Author</label>
              <input type="text" className="form-control" value={f.author} onChange={(e) => set('author', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">ISBN</label>
              <input type="text" className="form-control" value={f.isbn} onChange={(e) => set('isbn', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Category</label>
              <input type="text" className="form-control" placeholder="Fiction, Science, Reference…" value={f.category} onChange={(e) => set('category', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Publisher</label>
              <input type="text" className="form-control" value={f.publisher} onChange={(e) => set('publisher', e.target.value)} /></div>
          </div>
          <div className="form-row">
            <div className="form-group"><label className="form-label">Shelf / location</label>
              <input type="text" className="form-control" value={f.shelf} onChange={(e) => set('shelf', e.target.value)} /></div>
            <div className="form-group"><label className="form-label">Total copies</label>
              <input type="number" className="form-control" min="0" value={f.copies_total} onChange={(e) => set('copies_total', e.target.value)} />
              {editing && <span className="form-hint d-block">{b.copies_available} currently available · {b.on_loan} on loan</span>}</div>
          </div>
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
  const [studentId, setStudentId] = useState('');
  const [due, setDue] = useState(d.default_due);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!bookId || !studentId) { notify('error', 'Select a book and a student.'); return; }
    setBusy(true);
    const r = await submitJson(d.submit_url, { book_id: bookId, student_id: studentId, due_date: due });
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
          <Autocomplete label="Book" required url={d.urls.book_search} placeholder="Search title / author / ISBN…"
                        initialText={d.preset ? d.preset.title : ''} onPick={setBookId} />
          <Autocomplete label="Student" required url={d.urls.student_search} placeholder="Search name / student ID…" onPick={setStudentId} />
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
  const ret = async (l) => {
    if (!await confirm(`Mark '${l.book}' as returned?`)) return;
    setBusy(true);
    const r = await submitJson(l.return_url, {});
    setBusy(false);
    if (r.ok) nav.refresh();
    else notify('error', r.error || 'Could not return the book.');
  };
  const onStatus = (v) => { nav.go(d.urls.loans + '?status=' + v); };

  return (
    <>
      <PageHeader title="Loans" actions={<a href={d.urls.issue} className="btn btn-primary"><i aria-hidden="true" className="fas fa-hand-holding" /> Issue Book</a>} />
      <Tabs urls={d.urls} page="loans" />
      <div className="card mb-3"><div className="card-body">
        <div className="filter-form"><div className="form-group"><label className="form-label">Show</label>
          <select className="form-control" value={d.status} onChange={(e) => onStatus(e.target.value)}>
            {['Borrowed', 'Overdue', 'Returned'].map((s) => <option key={s} value={s}>{s}</option>)}
            <option value="all">All</option>
          </select></div></div>
      </div></div>

      <div className="card">
        <div className="card-header"><h3>{d.loans.length} loan(s)</h3></div>
        <div className="card-body" style={{ padding: 0 }}>
          <Table rowKey={(l) => l.id} rows={d.loans}
            empty={<Empty icon="fa-rotate-left" title="No loans"><p>Nothing matches this filter.</p></Empty>}
            columns={[
              { key: 'book', label: 'Book', render: (l) => l.book },
              { key: 'student', label: 'Student', render: (l) => l.student },
              { key: 'borrowed', label: 'Borrowed', render: (l) => l.borrowed },
              { key: 'due', label: 'Due', render: (l) => <>{l.due}{l.is_overdue && <span className="text-danger text-sm"> ({l.days_overdue}d late)</span>}</> },
              { key: 'status', label: 'Status', render: (l) => statusBadge(l) },
              { key: 'fine', label: 'Fine', render: (l) => l.fine ? naira(l.fine) : '—' },
              { key: 'act', label: '', render: (l) => l.status === 'Borrowed'
                ? <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => ret(l)}><i aria-hidden="true" className="fas fa-rotate-left" /> Return</button>
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

const SCREENS = { dashboard: Dashboard, books: Books, book_form: BookForm, issue: Issue, loans: Loans, settings: Settings };

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
