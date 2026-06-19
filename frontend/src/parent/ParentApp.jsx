import React, { useState } from 'react';
import { csrfToken } from '../lib/api';
import { NavCtx, useSection } from '../lib/section';

const money = (n) => '₦' + Math.round(Number(n) || 0).toLocaleString();

function Home({ d, go }) {
  const [flashes, setFlashes] = useState(d.flashes || []);
  const [amount, setAmount] = useState(d.bill ? Math.round(d.bill.balance) : 0);
  const r = d.report;
  const owing = d.bill && d.bill.balance > 0.005;

  const onTerm = (e) => go(`${d.urls.self}?term_id=${e.target.value}`);
  const onChild = (e) => { if (e.target.value) go(e.target.value); };

  return (
    <>
      <div className="top"><div className="wrap">
        <div>
          <h1>{d.student.full_name}</h1>
          <p>{d.student.student_id}{d.student.class_name ? ` · ${d.student.class_name}` : ''}</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem' }}>
          {d.siblings.length > 1 && (
            <select onChange={onChild} value="" style={{ padding: '.4rem', borderRadius: 8, border: 'none' }}>
              {d.siblings.map((s) => (
                <option key={s.id} value={s.is_current ? '' : s.switch_url}>{s.full_name}</option>
              ))}
            </select>
          )}
          <a className="logout" href={d.urls.logout}><i className="fas fa-right-from-bracket" /> Sign out</a>
        </div>
      </div></div>

      <div className="wrap">
        {flashes.map((f, i) => (
          <div key={i} className={`flash flash-${f.category}`} onClick={() => setFlashes(flashes.filter((_, j) => j !== i))}>{f.message}</div>
        ))}

        <div className="termbar">
          <label className="muted" htmlFor="term">Term:</label>
          <select id="term" value={d.term_id || ''} onChange={onTerm}>
            {d.terms.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>

        <div className="cards">
          <div className="card">
            <h3>Fees — Balance</h3>
            {d.bill ? (
              <>
                <div className={`big ${owing ? 'owe' : 'ok'}`}>{money(d.bill.balance)}</div>
                <p className="muted">Billed {money(d.bill.payable)} · Paid {money(d.bill.paid)}</p>
                {d.pay_enabled && owing && (
                  <form method="POST" action={d.urls.pay} style={{ marginTop: '.7rem' }}>
                    <input type="hidden" name="_csrf_token" value={csrfToken()} />
                    <input type="hidden" name="term_id" value={d.term_id || ''} />
                    <input type="number" name="amount" min="100" step="50" value={amount}
                      onChange={(e) => setAmount(e.target.value)} className="form-control" style={{ marginBottom: '.4rem' }} />
                    <button type="submit" className="pay-btn"><i className="fas fa-credit-card" /> Pay online</button>
                  </form>
                )}
              </>
            ) : <p className="muted">No fee record for this term.</p>}
          </div>
          <div className="card">
            <h3>Attendance</h3>
            {d.attendance != null ? <><div className="big">{d.attendance}%</div><p className="muted">This term</p></>
              : <p className="muted">Not available yet.</p>}
          </div>
          {r && (
            <div className="card">
              <h3>Position</h3>
              <div className="big pos">{r.position || '—'}</div>
              <p className="muted">Average {r.average} · {r.overall_grade}</p>
            </div>
          )}
        </div>

        <div className="sec">
          <h2 style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '.5rem', flexWrap: 'wrap' }}>Results
            {r && <a href={d.urls.report_pdf} className="pdf-link"><i className="fas fa-file-pdf" /> Download PDF</a>}
          </h2>
          {r ? (
            <>
              <p className="muted" style={{ fontSize: '.78rem', marginTop: '-.4rem' }}><i className="fas fa-wifi" /> Tip: once opened, this page works offline — and the PDF can be saved to your phone.</p>
              <table>
                <thead><tr><th>Subject</th>{r.assessment_types.map((at) => <th key={at.id}>{at.label}</th>)}<th>Total</th><th>Grade</th><th>Remark</th></tr></thead>
                <tbody>
                  {r.subjects.map((row, i) => (
                    <tr key={i}>
                      <td>{row.name}</td>
                      {r.assessment_types.map((at) => <td key={at.id}>{row.assessments[String(at.id)] != null ? row.assessments[String(at.id)] : '–'}</td>)}
                      <td><strong>{row.total}</strong></td><td>{row.grade}</td><td>{row.remark}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {r.affective.length > 0 && (
                <>
                  <h2 style={{ marginTop: '1.2rem' }}>Behaviour</h2>
                  <table>
                    <thead><tr><th>Trait</th><th>Rating</th></tr></thead>
                    <tbody>
                      {r.affective.map((a, i) => <tr key={i}><td>{a.label}</td><td>{a.rating}/5 · {a.rating_label}</td></tr>)}
                    </tbody>
                  </table>
                </>
              )}
              {(r.teacher_comment || r.principal_comment) && (
                <>
                  <p style={{ marginTop: '.8rem' }}><strong>Form teacher:</strong> {r.teacher_comment || '—'}</p>
                  <p><strong>Principal:</strong> {r.principal_comment || '—'}</p>
                </>
              )}
            </>
          ) : (
            <p className="muted">Results for this term are not yet available. Please check back after the school has released them.</p>
          )}
        </div>

        {d.announcements.length > 0 && (
          <div className="sec">
            <h2>Announcements</h2>
            {d.announcements.map((a, i) => (
              <div className="ann" key={i}>{a.is_pinned && <span className="badge">Pinned</span>} <strong>{a.title}</strong>
                <div className="muted">{a.body}</div></div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default function ParentApp({ data }) {
  const { data: d, go } = useSection(data);
  return (
    <NavCtx.Provider value={{ go, refresh: () => go(window.location.href, { replace: true }) }}>
      <Home d={d} go={go} />
    </NavCtx.Provider>
  );
}
