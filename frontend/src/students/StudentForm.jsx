import React, { useState, useEffect, useRef } from 'react';
import { postForm } from '../lib/forms';
import { useDraft } from '../lib/draft';
import { Banner } from '../components/ui';
import { TextField, TextAreaField, SelectField, FormCard } from '../components/Form';

const REL_SEQUENCE = ['Father', 'Mother', 'Guardian'];

const RELATIONSHIP_FALLBACK = ['Father', 'Mother', 'Guardian', 'Sibling', 'Other'];

// One WAEC/JAMB subject picker (checkbox grid) with a Clear shortcut.
function SubjectChecks({ legendIcon, legend, all, selected, onToggle, onClear, name }) {
  return (
    <div className="exam-subjects-group" style={{ marginTop: '.25rem' }}>
      <div className="exam-subjects-head">
        <strong><i className={'fas ' + legendIcon} aria-hidden="true" /> {legend}</strong>
        <button type="button" className="exam-subjects-clear" onClick={onClear}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
          Clear
        </button>
      </div>
      <div className="subject-checks" role="group" aria-label={legend}>
        {all.map((subj) => (
          <label key={subj} className="subject-check">
            <input type="checkbox" name={name} value={subj}
                   checked={selected.has(subj)} onChange={() => onToggle(subj)} />
            <span>{subj}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

// A lightweight searchable dropdown (combobox) over a provided list of
// { id, label } items. Filters client-side; picks by mouse or clears with ×.
function Combo({ items, initialLabel, placeholder, onPick }) {
  const [q, setQ] = useState(initialLabel || '');
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  const ql = q.trim().toLowerCase();
  const list = (!ql ? items : items.filter((it) => (it.label || '').toLowerCase().includes(ql))).slice(0, 40);
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <div style={{ position: 'relative' }}>
        <input type="text" value={q} placeholder={placeholder} autoComplete="off"
               onChange={(e) => { setQ(e.target.value); setOpen(true); if (!e.target.value.trim()) onPick(null); }}
               onFocus={() => setOpen(true)}
               style={{ width: '100%', padding: '.55rem .75rem', paddingRight: '1.8rem',
                        border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md, 8px)',
                        background: 'var(--bg-input, var(--bg-card))', color: 'inherit' }} />
        {q && <button type="button" aria-label="Clear" onClick={() => { setQ(''); onPick(null); }}
                      style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
                               background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '1.1rem' }}>×</button>}
      </div>
      {open && list.length > 0 && (
        <ul role="listbox" style={{ position: 'absolute', zIndex: 30, left: 0, right: 0, top: '100%', margin: '.2rem 0 0',
                     listStyle: 'none', padding: '.25rem', maxHeight: 240, overflowY: 'auto',
                     background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                     borderRadius: 'var(--radius-md, 8px)', boxShadow: 'var(--shadow-md, 0 10px 30px -12px rgba(0,0,0,.3))' }}>
          {list.map((it) => (
            <li key={it.id} role="option"
                onMouseDown={() => { setQ(it.label); setOpen(false); onPick(it); }}
                style={{ padding: '.45rem .6rem', cursor: 'pointer', borderRadius: 6, fontSize: '.9rem' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--gray-100)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}>
              {it.label}{it.department ? <span style={{ color: 'var(--text-muted)', fontSize: '.8rem' }}> · {it.department}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function StudentForm({ data }) {
  const isEdit = data.mode === 'edit';
  const opt = data.options || {};
  const stu = data.student || {};
  const enrolment = opt.enrolment || null;

  // Draft recovery: a half-typed registration survives an accidental nav / reload /
  // crash. Tied to the server baseline (on edit) so a stale draft never blanks
  // authoritative data; cleared on a successful submit.
  const draftKey = 'student-' + (isEdit ? 'edit-' + (stu.id || stu.student_id || '') : 'add');
  const draftSig = isEdit ? JSON.stringify([stu.surname, stu.first_name, stu.middle_name, stu.gender,
    stu.date_of_birth, stu.religion, stu.stream, stu.jamb_target, stu.home_address, stu.hobbies]) : undefined;
  const [f, setF, clearFDraft] = useDraft(draftKey, {
    surname: stu.surname || '', first_name: stu.first_name || '', middle_name: stu.middle_name || '',
    gender: stu.gender || '', date_of_birth: stu.date_of_birth || '', religion: stu.religion || '',
    stream: stu.stream || '', jamb_target: stu.jamb_target === 0 ? '0' : (stu.jamb_target || ''),
    target_university_id: stu.target_university_id ? String(stu.target_university_id) : '',
    target_course_id: stu.target_course_id ? String(stu.target_course_id) : '',
    target_department: stu.target_department || '',
    target2_university_id: stu.target2_university_id ? String(stu.target2_university_id) : '',
    target2_course_id: stu.target2_course_id ? String(stu.target2_course_id) : '',
    career_goal: stu.career_goal || '',
    admission_status: stu.admission_status || '',
    admitted_university_id: stu.admitted_university_id ? String(stu.admitted_university_id) : '',
    admitted_course_id: stu.admitted_course_id ? String(stu.admitted_course_id) : '',
    home_address: stu.home_address || '', hobbies: stu.hobbies || '',
    house: stu.house || '', boarding_status: stu.boarding_status || '',
    nin: stu.nin || '', jamb_reg_number: stu.jamb_reg_number || '', jamb_profile_code: stu.jamb_profile_code || '',
    waec_reg_number: stu.waec_reg_number || '', serial_number: stu.serial_number || '',
    waec_epin: stu.waec_epin || '',
    photo: stu.photo_url || '',
    blood_group: stu.blood_group || '', genotype: stu.genotype || '', allergies: stu.allergies || '',
    medical_conditions: stu.medical_conditions || '', disabilities: stu.disabilities || '',
    medications: stu.medications || '', medical_notes: stu.medical_notes || '', emergency_medical: stu.emergency_medical || '',
  }, { signature: draftSig });
  // Contacts stay on plain state (useDraft serialises objects, not arrays).
  const [contacts, setContacts] = useState(() =>
    (data.contacts && data.contacts.length ? data.contacts : [{ name: '', phone_number: '', email: '', relationship: 'Father' }])
      .map((c) => ({ name: c.name || '', phone_number: c.phone_number || '', email: c.email || '', relationship: c.relationship || 'Father' })));
  const [waec, setWaec] = useState(() => new Set(stu.waec_subjects || []));
  const [jamb, setJamb] = useState(() => new Set(stu.jamb_subjects || []));
  const [scholarships, setScholarships] = useState(() =>
    (stu.scholarships || []).map((s) => ({ name: s.name || '', provider: s.provider || '',
      amount: s.amount != null ? String(s.amount) : '', status: s.status || '' })));
  const [recs, setRecs] = useState([]);
  const [enrolId, setEnrolId] = useState(enrolment && enrolment.default_id ? String(enrolment.default_id) : '');
  const [errors, setErrors] = useState({});
  const [contactErrors, setContactErrors] = useState({});
  const [banner, setBanner] = useState(null);
  const [saving, setSaving] = useState(false);
  // Autosave affirmation: useDraft already persists every change to
  // sessionStorage — surface a quiet "Draft saved" once the user has typed, so
  // they trust they can leave without losing the half-filled registration.
  const [draftSaved, setDraftSaved] = useState(false);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return undefined; }
    const t = setTimeout(() => setDraftSaved(true), 700);
    return () => clearTimeout(t);
  }, [f, contacts]);

  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  // Inline on-blur validation for required fields — surfaces the error as the user
  // leaves the field (and clears it once fixed), instead of only on submit.
  const blurRequired = (key, label) => () =>
    setErrors((e) => ({ ...e, [key]: String(f[key] || '').trim() ? undefined : `${label} is required.` }));
  const relationships = opt.relationships || RELATIONSHIP_FALLBACK;
  const allSubjects = opt.waec_subjects || [];

  // Selecting a stream fills the WAEC subjects from its default set (matches
  // the classic page: change overwrites the WAEC selection).
  const onStream = (v) => {
    set('stream', v);
    const subs = (opt.stream_waec || {})[v];
    if (subs) setWaec(new Set(subs));
  };
  const toggle = (setter) => (subj) => setter((prev) => {
    const next = new Set(prev); next.has(subj) ? next.delete(subj) : next.add(subj); return next;
  });

  // University aspiration: picking a course auto-fills the department, the JAMB
  // target (the course's competitive cut-off at the chosen university) and the
  // JAMB/WAEC subject requirements. Picking a university refreshes the target.
  const [aspirationNote, setAspirationNote] = useState('');
  const reqUrl = (opt.aspiration_urls || {}).requirements;
  const fetchRequirements = async (universityId, courseId, { fillSubjects }) => {
    if (!reqUrl || !courseId) return;
    try {
      const url = reqUrl + '?course_id=' + courseId + (universityId ? '&university_id=' + universityId : '');
      const res = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!res.ok) return;
      const r = await res.json();
      setF((x) => ({ ...x, jamb_target: r.jamb_target != null ? String(r.jamb_target) : x.jamb_target,
                     target_department: r.department || x.target_department }));
      // Only the JAMB subjects + target are auto-filled from the course; WAEC
      // subjects are left exactly as the user set them.
      if (fillSubjects && Array.isArray(r.jamb_subjects)) setJamb(new Set(r.jamb_subjects));
      setAspirationNote('JAMB target set to ' + r.jamb_target + ' and JAMB subjects filled from the course.');
    } catch (_e) { /* leave fields as-is on a network hiccup */ }
  };
  const pickUniversity = (item) => {
    const id = item ? String(item.id) : '';
    set('target_university_id', id);
    if (id && f.target_course_id) fetchRequirements(id, f.target_course_id, { fillSubjects: false });
    if (recUrl) loadRecs(id);
  };
  const pickCourse = (item) => {
    const id = item ? String(item.id) : '';
    setF((x) => ({ ...x, target_course_id: id, target_department: item ? (item.department || x.target_department) : x.target_department }));
    if (id) fetchRequirements(f.target_university_id, id, { fillSubjects: true });
    else setAspirationNote('');
  };

  // Course recommender (edit only): courses the student is projected to be
  // competitive for, refreshed when their target university changes.
  const recUrl = data.urls && data.urls.recommend;
  const loadRecs = async (universityId) => {
    if (!recUrl) return;
    try {
      const res = await fetch(recUrl + (universityId ? '?university_id=' + universityId : ''),
        { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (res.ok) { const j = await res.json(); setRecs(j.recommendations || []); }
    } catch (_e) { /* ignore */ }
  };
  useEffect(() => { if (recUrl) loadRecs(f.target_university_id); }, []); // eslint-disable-line
  const pickUniversity2 = (item) => set('target2_university_id', item ? String(item.id) : '');
  const pickCourse2 = (item) => set('target2_course_id', item ? String(item.id) : '');
  const pickAdmittedUni = (item) => set('admitted_university_id', item ? String(item.id) : '');
  const pickAdmittedCourse = (item) => set('admitted_course_id', item ? String(item.id) : '');
  const applyRec = (rec) => {
    setF((x) => ({ ...x, target_course_id: String(rec.course_id), target_department: rec.department || x.target_department }));
    fetchRequirements(f.target_university_id, rec.course_id, { fillSubjects: true });
  };
  const setSch = (i, k, v) => setScholarships((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));
  const addSch = () => setScholarships((cs) => [...cs, { name: '', provider: '', amount: '', status: '' }]);
  const removeSch = (i) => setScholarships((cs) => cs.filter((_, j) => j !== i));

  const setContact = (i, k, v) => setContacts((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));
  // Smarter default: 1st contact = Father, 2nd = Mother, then Guardian.
  const addContact = () => setContacts((cs) =>
    [...cs, { name: '', phone_number: '', email: '', relationship: REL_SEQUENCE[cs.length] || 'Guardian' }]);
  const removeContact = (i) => setContacts((cs) => (cs.length > 1 ? cs.filter((_, j) => j !== i) : cs));

  const validate = () => {
    const e = {};
    if (!f.surname.trim()) e.surname = 'Surname is required.';
    if (!f.first_name.trim()) e.first_name = 'First name is required.';
    if (!f.gender) e.gender = 'Select a gender.';
    if (f.jamb_target !== '') {
      const n = Number(f.jamb_target);
      if (!Number.isInteger(n) || n < 0 || n > 400) e.jamb_target = 'Enter a score between 0 and 400.';
    }
    const ce = {};
    contacts.forEach((c, i) => {
      if (c.name.trim() && !c.phone_number.trim()) ce[i] = 'Phone is required for this contact.';
    });
    setErrors(e); setContactErrors(ce);
    return Object.keys(e).length === 0 && Object.keys(ce).length === 0;
  };

  const submit = async (ev) => {
    ev.preventDefault();
    setBanner(null);
    if (!validate()) {
      setBanner({ tone: 'error', text: 'Please fix the highlighted fields.' });
      return;
    }
    const send = contacts.filter((c) => c.phone_number.trim());
    const fields = {
      surname: f.surname.trim(), first_name: f.first_name.trim(), middle_name: f.middle_name.trim(),
      gender: f.gender, date_of_birth: f.date_of_birth, religion: f.religion, stream: f.stream,
      jamb_target: f.jamb_target, home_address: f.home_address, hobbies: f.hobbies,
      target_university_id: f.target_university_id, target_course_id: f.target_course_id,
      target_department: f.target_department,
      target2_university_id: f.target2_university_id, target2_course_id: f.target2_course_id,
      career_goal: f.career_goal, admission_status: f.admission_status,
      admitted_university_id: f.admitted_university_id, admitted_course_id: f.admitted_course_id,
      'scholarship_name[]': scholarships.map((s) => (s.name || '').trim()),
      'scholarship_provider[]': scholarships.map((s) => (s.provider || '').trim()),
      'scholarship_amount[]': scholarships.map((s) => (s.amount || '').trim()),
      'scholarship_status[]': scholarships.map((s) => (s.status || '').trim()),
      house: f.house, boarding_status: f.boarding_status,
      nin: f.nin, jamb_reg_number: f.jamb_reg_number, jamb_profile_code: f.jamb_profile_code,
      waec_reg_number: f.waec_reg_number, serial_number: f.serial_number, waec_epin: f.waec_epin, photo: f.photo,
      blood_group: f.blood_group, genotype: f.genotype, allergies: f.allergies,
      medical_conditions: f.medical_conditions, disabilities: f.disabilities,
      medications: f.medications, medical_notes: f.medical_notes, emergency_medical: f.emergency_medical,
      'contact_name[]': send.map((c) => c.name.trim()),
      'phone_number[]': send.map((c) => c.phone_number.trim()),
      'email[]': send.map((c) => (c.email || '').trim()),
      'relationship[]': send.map((c) => c.relationship),
      'waec_subjects[]': [...waec],
      'jamb_subjects[]': [...jamb],
    };
    if (isEdit) { fields.form_complete = '1'; fields.return_to = data.return_to || ''; }
    else if (enrolId) { fields.class_arm_assignment_id = enrolId; }

    setSaving(true);
    try {
      const res = await postForm(data.urls.submit, fields);
      let body = {};
      try { body = await res.json(); } catch (_) { /* non-JSON */ }
      if (res.ok && body.ok) { clearFDraft(); window.location = body.redirect; return; }
      setBanner({ tone: 'error', text: body.error || `Could not save (HTTP ${res.status}).` });
    } catch (err) {
      setBanner({ tone: 'error', text: err.message || 'Network error — please try again.' });
    } finally {
      setSaving(false);
    }
  };

  const urls = data.urls || {};

  const onPhotoFile = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';                       // allow re-picking the same file
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setBanner({ tone: 'error', text: 'That image is too large (max 8 MB).' });
      return;
    }
    const rd = new FileReader();
    rd.onload = () => set('photo', String(rd.result || ''));
    rd.onerror = () => setBanner({ tone: 'error', text: 'Could not read that image.' });
    rd.readAsDataURL(file);
  };

  return (
    <form onSubmit={submit} noValidate>
      <div className="page-header">
        <div>
          <h1>{isEdit ? 'Edit Student' : 'Add New Student'}</h1>{' '}
          {isEdit && stu.student_id && <span className="badge badge-primary">{stu.student_id}</span>}
        </div>
        {isEdit && (
          <div className="page-header-actions">
            <a href={urls.back} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Profile</a>
            <a href={urls.list} className="sp-btn sp-btn-sm"><i aria-hidden="true" className="fas fa-users" /> All Students</a>
          </div>
        )}
      </div>

      {banner && <Banner tone={banner.tone} onClose={() => setBanner(null)}>{banner.text}</Banner>}

      <FormCard icon="fa-user" title="Personal Information">
        <div className="sf-row">
          <TextField label="Surname" required value={f.surname} onChange={(v) => set('surname', v)}
                     onBlur={blurRequired('surname', 'Surname')}
                     error={errors.surname} placeholder="Surname" autoComplete="off" />
          <TextField label="First Name" required value={f.first_name} onChange={(v) => set('first_name', v)}
                     onBlur={blurRequired('first_name', 'First name')}
                     error={errors.first_name} placeholder="First name" autoComplete="off" />
        </div>
        <TextField label="Middle Name" value={f.middle_name} onChange={(v) => set('middle_name', v)}
                   placeholder="Middle name (optional)" autoComplete="off" />
        <div className="sf-row">
          <SelectField label="Gender" required value={f.gender} onChange={(v) => set('gender', v)}
                       onBlur={blurRequired('gender', 'Gender')}
                       placeholder="Select Gender" options={opt.genders || ['Male', 'Female']} error={errors.gender} />
          <TextField label="Date of Birth" type="date" value={f.date_of_birth} onChange={(v) => set('date_of_birth', v)} />
        </div>
        <div className="sf-row">
          <SelectField label="Religion" value={f.religion} onChange={(v) => set('religion', v)}
                       placeholder="Select Religion" options={opt.religions || []} />
          <SelectField label="Stream / Track" value={f.stream} onChange={onStream}
                       placeholder="Select Stream" options={opt.streams || []}
                       hint="Science, Arts or Commercial — drives WAEC subject defaults" />
        </div>
        <TextField label="JAMB Target Score" type="number" min="0" max="400" value={f.jamb_target}
                   onChange={(v) => set('jamb_target', v)} error={errors.jamb_target} placeholder="e.g. 250"
                   hint="Optional — used to track Mock JAMB progress against a goal" />
        <TextAreaField label="Home Address" value={f.home_address} onChange={(v) => set('home_address', v)} placeholder="Full address" />
        <TextField label="Hobbies" value={f.hobbies} onChange={(v) => set('hobbies', v)}
                   placeholder="e.g., Football, Reading" hint="Separate with commas" />
      </FormCard>

      <FormCard icon="fa-graduation-cap" title="University Aspiration" collapsible defaultOpen={isEdit}>
        <p className="text-muted" style={{ fontSize: '.85rem', marginTop: 0 }}>
          Where the student wants to study. Picking a course auto-fills the department, the JAMB
          target (the course's competitive cut-off for the chosen university) and the JAMB subject
          requirements below — all editable. WAEC subjects are left as you set them.
        </p>
        <div className="sf-row">
          <div className="form-group">
            <label className="form-label">University</label>
            <Combo items={opt.universities || []} initialLabel={stu.target_university_label || ''}
                   placeholder="Search universities…" onPick={pickUniversity} />
          </div>
          <div className="form-group">
            <label className="form-label">Course</label>
            <Combo items={opt.courses || []} initialLabel={stu.target_course_label || ''}
                   placeholder="Search courses…" onPick={pickCourse} />
          </div>
        </div>
        <TextField label="Department / Faculty" value={f.target_department}
                   onChange={(v) => set('target_department', v)} placeholder="Auto-filled from the course" />
        {aspirationNote && (
          <p className="text-muted" style={{ fontSize: '.8rem', marginTop: '.35rem' }}>
            <i className="fas fa-circle-info" aria-hidden="true" /> {aspirationNote}
          </p>
        )}
        {recs.length > 0 && (
          <div style={{ marginTop: '.75rem' }}>
            <label className="form-label" style={{ marginBottom: '.35rem' }}>
              <i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Suggested courses
              <span className="text-muted" style={{ fontWeight: 400 }}> — projected competitive at this university</span>
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem' }}>
              {recs.map((rec) => (
                <button type="button" key={rec.course_id} className="sp-btn sp-btn-sm"
                        onClick={() => applyRec(rec)} title={'Cut-off ' + rec.cutoff + ' · +' + rec.margin + ' projected margin'}>
                  {rec.subject_fit && <i className="fas fa-check" aria-hidden="true" style={{ color: 'var(--success)' }} />} {rec.course}
                  <span className="text-muted" style={{ fontSize: '.75rem' }}> +{rec.margin}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="sf-row" style={{ marginTop: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Second-choice University <span className="text-muted">(optional)</span></label>
            <Combo items={opt.universities || []} initialLabel={stu.target2_university_label || ''}
                   placeholder="Search universities…" onPick={pickUniversity2} />
          </div>
          <div className="form-group">
            <label className="form-label">Second-choice Course <span className="text-muted">(optional)</span></label>
            <Combo items={opt.courses || []} initialLabel={stu.target2_course_label || ''}
                   placeholder="Search courses…" onPick={pickCourse2} />
          </div>
        </div>
        <TextField label="Career goal" value={f.career_goal} onChange={(v) => set('career_goal', v)}
                   placeholder="e.g. Medical doctor, Software engineer"
                   hint="What the student ultimately wants to become — helps align course choice" />
      </FormCard>

      <FormCard icon="fa-award" title="Admission & Scholarships" note="(optional)" collapsible
                defaultOpen={isEdit && !!(stu.admission_status || (stu.scholarships && stu.scholarships.length))}>
        <div className="sf-row">
          <SelectField label="Admission status" value={f.admission_status} onChange={(v) => set('admission_status', v)}
                       placeholder="—" options={opt.admission_statuses || []}
                       hint="Where the student is in the admission cycle" />
        </div>
        <div className="sf-row">
          <div className="form-group">
            <label className="form-label">Admitted University <span className="text-muted">(if offered)</span></label>
            <Combo items={opt.universities || []} initialLabel={stu.admitted_university_label || ''}
                   placeholder="Search universities…" onPick={pickAdmittedUni} />
          </div>
          <div className="form-group">
            <label className="form-label">Admitted Course <span className="text-muted">(if offered)</span></label>
            <Combo items={opt.courses || []} initialLabel={stu.admitted_course_label || ''}
                   placeholder="Search courses…" onPick={pickAdmittedCourse} />
          </div>
        </div>
        <label className="form-label" style={{ marginTop: '.5rem' }}>Scholarships</label>
        {scholarships.length === 0 && (
          <p className="text-muted" style={{ fontSize: '.85rem', marginTop: 0 }}>No scholarships recorded.</p>
        )}
        {scholarships.map((s, i) => (
          <div className="sf-contact" key={i}>
            <TextField label="Name" value={s.name} onChange={(v) => setSch(i, 'name', v)} placeholder="e.g. NNPC/SNEPCo" autoComplete="off" />
            <TextField label="Provider" value={s.provider} onChange={(v) => setSch(i, 'provider', v)} placeholder="Sponsor" autoComplete="off" />
            <TextField label="Amount (₦)" value={s.amount} onChange={(v) => setSch(i, 'amount', v)} type="number" placeholder="0" autoComplete="off" />
            <SelectField label="Status" value={s.status} onChange={(v) => setSch(i, 'status', v)}
                         placeholder="—" options={opt.scholarship_statuses || []} />
            <button type="button" className="sp-btn sp-btn-sm sp-btn-danger sf-remove" aria-label={`Remove scholarship ${i + 1}`}
                    onClick={() => removeSch(i)}>
              <i aria-hidden="true" className="fas fa-times" />
            </button>
          </div>
        ))}
        <button type="button" className="sp-btn sp-btn-sm" onClick={addSch}>
          <i aria-hidden="true" className="fas fa-plus" /> Add Scholarship
        </button>
      </FormCard>

      <FormCard icon="fa-phone" title="Parent/Guardian Contacts" collapsible defaultOpen={isEdit}>
        {contacts.map((c, i) => (
          <div className="sf-contact" key={i}>
            <TextField label="Name" value={c.name} onChange={(v) => setContact(i, 'name', v)} placeholder="e.g., Mr. John" autoComplete="off" />
            <TextField label="Phone" required value={c.phone_number} onChange={(v) => setContact(i, 'phone_number', v)}
                       type="tel" placeholder="08012345678" error={contactErrors[i]} autoComplete="off" />
            <TextField label="Email (optional)" value={c.email} onChange={(v) => setContact(i, 'email', v)}
                       type="email" placeholder="parent@example.com" autoComplete="off" />
            <SelectField label="Relationship" value={c.relationship} onChange={(v) => setContact(i, 'relationship', v)} options={relationships} />
            <button type="button" className="sp-btn sp-btn-sm sp-btn-danger sf-remove" aria-label={`Remove contact ${i + 1}`}
                    disabled={contacts.length === 1} onClick={() => removeContact(i)}>
              <i aria-hidden="true" className="fas fa-times" />
            </button>
          </div>
        ))}
        <button type="button" className="sp-btn sp-btn-sm" onClick={addContact}>
          <i aria-hidden="true" className="fas fa-plus" /> Add Contact
        </button>
      </FormCard>

      {!isEdit && enrolment && (
        <FormCard icon="fa-chalkboard" title="Class Enrolment" note={`(${enrolment.term_label})`} collapsible defaultOpen={!!(enrolment && enrolment.default_id)}>
          {enrolment.has_classes ? (
            <SelectField label="Enrol into class & arm" value={enrolId} onChange={setEnrolId}
                         placeholder="— Don't enrol yet —"
                         options={enrolment.classes.map((c) => ({ value: String(c.id), label: c.label }))}
                         hint={enrolment.default_id
                           ? 'Your form class is selected — the student will be added there.'
                           : 'Pick the class to place this student in now, or leave blank and enrol later.'} />
          ) : (
            <p className="text-muted"><i aria-hidden="true" className="fas fa-info-circle" /> No classes are set up for this term yet, or none are assigned to you. You can enrol the student into a class later.</p>
          )}
        </FormCard>
      )}

      <FormCard icon="fa-id-card" title="Identity &amp; Pastoral" note="(optional)" collapsible
                defaultOpen={isEdit && !!(stu.nin || stu.jamb_reg_number || stu.house || stu.boarding_status || stu.photo_url)}>
        <div className="sf-row" style={{ alignItems: 'flex-start' }}>
          <div className="form-group" style={{ flex: '1 1 100%' }}>
            <label className="form-label">Passport photo <span className="text-muted">(optional)</span></label>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              {f.photo
                ? <img src={f.photo} alt="Student" style={{ width: 64, height: 80, objectFit: 'cover', borderRadius: 6, border: '1px solid var(--border-color,#cbd5e1)' }} />
                : <div style={{ width: 64, height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--gray-50,#f1f5f9)', border: '1px dashed #cbd5e1', borderRadius: 6, fontSize: '.6rem', color: '#94a3b8', textAlign: 'center' }}>No photo</div>}
              <div>
                <label className="sp-btn sp-btn-sm" style={{ cursor: 'pointer', margin: 0 }}>
                  <i aria-hidden="true" className="fas fa-camera" /> {f.photo ? 'Change' : 'Upload'}
                  <input type="file" accept="image/png,image/jpeg,image/webp" onChange={onPhotoFile} style={{ display: 'none' }} />
                </label>
                {f.photo && <button type="button" className="sp-btn sp-btn-sm" style={{ marginLeft: '.4rem' }} onClick={() => set('photo', '')}><i aria-hidden="true" className="fas fa-times" /> Remove</button>}
                <div className="text-muted" style={{ fontSize: '.75rem', marginTop: '.35rem' }}>JPG/PNG, up to 8 MB — auto-cropped to a passport photo and shown on the ID card.</div>
              </div>
            </div>
          </div>
        </div>
        <div className="sf-row">
          <TextField label="NIN" value={f.nin} onChange={(v) => set('nin', v)} placeholder="National Identification Number" autoComplete="off" />
          <SelectField label="Boarding status" value={f.boarding_status} onChange={(v) => set('boarding_status', v)}
                       placeholder="—" options={['Day', 'Boarding']} />
        </div>
        <div className="sf-row">
          <TextField label="JAMB Reg. Number" value={f.jamb_reg_number} onChange={(v) => set('jamb_reg_number', v)} placeholder="JAMB registration number" autoComplete="off" />
          <TextField label="JAMB Profile Code" value={f.jamb_profile_code} onChange={(v) => set('jamb_profile_code', v)} placeholder="JAMB profile code" autoComplete="off" />
        </div>
        <div className="sf-row">
          <TextField label="WAEC Reg. Number" value={f.waec_reg_number} onChange={(v) => set('waec_reg_number', v)} placeholder="WAEC/NECO examination number" autoComplete="off" />
          <TextField label="Serial Number" value={f.serial_number} onChange={(v) => set('serial_number', v)} placeholder="Candidate serial number" autoComplete="off" />
          <TextField label="WAEC e-PIN" value={f.waec_epin} onChange={(v) => set('waec_epin', v)} placeholder="WAEC e-PIN" autoComplete="off" />
        </div>
        <TextField label="House" value={f.house} onChange={(v) => set('house', v)} placeholder="e.g. Red House / Zik House" autoComplete="off" />
      </FormCard>

      <FormCard icon="fa-notes-medical" title="Medical Information" note="(optional, confidential)" collapsible
                defaultOpen={isEdit && !!(stu.blood_group || stu.allergies || stu.medical_conditions || stu.medical_notes)}>
        <div className="sf-row">
          <SelectField label="Blood group" value={f.blood_group} onChange={(v) => set('blood_group', v)}
                       placeholder="—" options={['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']} />
          <SelectField label="Genotype" value={f.genotype} onChange={(v) => set('genotype', v)}
                       placeholder="—" options={['AA', 'AS', 'SS', 'AC', 'SC']} />
        </div>
        <TextField label="Allergies" value={f.allergies} onChange={(v) => set('allergies', v)} placeholder="e.g. Penicillin, peanuts" />
        <TextField label="Existing conditions" value={f.medical_conditions} onChange={(v) => set('medical_conditions', v)} placeholder="e.g. Asthma" />
        <TextField label="Disabilities" value={f.disabilities} onChange={(v) => set('disabilities', v)} placeholder="Any disabilities to note" />
        <TextField label="Current medications" value={f.medications} onChange={(v) => set('medications', v)} placeholder="Regular medications" />
        <TextAreaField label="Medical notes" value={f.medical_notes} onChange={(v) => set('medical_notes', v)} placeholder="Confidential notes (encrypted at rest)" />
        <TextAreaField label="Emergency medical instructions" value={f.emergency_medical} onChange={(v) => set('emergency_medical', v)} placeholder="What to do in an emergency" />
      </FormCard>

      <FormCard icon="fa-file-signature" title="External Exam Subjects" note="(optional)" collapsible defaultOpen={isEdit && (waec.size > 0 || jamb.size > 0)}>
        <p className="text-muted text-sm mb-3">
          Select the subjects this student is registered for. These pre-fill the WAEC and JAMB
          result-entry pages. You can skip this and set it later.
        </p>
        <SubjectChecks legendIcon="fa-file-alt" legend="WAEC Subjects" all={allSubjects} name="waec_subjects[]"
                       selected={waec} onToggle={toggle(setWaec)} onClear={() => setWaec(new Set())} />
        <SubjectChecks legendIcon="fa-file-contract" legend="JAMB Subjects" all={allSubjects} name="jamb_subjects[]"
                       selected={jamb} onToggle={toggle(setJamb)} onClear={() => setJamb(new Set())} />
      </FormCard>

      <div className="page-header-actions">
        <button type="submit" className="sp-btn sp-btn-fill sp-btn-lg" disabled={saving}>
          <i aria-hidden="true" className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-save')} /> {saving ? 'Saving…' : (isEdit ? 'Save Changes' : 'Save Student')}
        </button>
        <a href={urls.cancel} className={'sp-btn sp-btn-lg' + (saving ? ' disabled' : '')}
           onClick={(e) => saving && e.preventDefault()}>Cancel</a>
        {draftSaved && !saving && (
          <span className="draft-saved" role="status">
            <i aria-hidden="true" className="fas fa-circle-check" /> Draft saved — we’ll keep your progress
          </span>
        )}
      </div>
    </form>
  );
}
