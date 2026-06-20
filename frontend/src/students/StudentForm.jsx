import React, { useState } from 'react';
import { postForm } from '../lib/forms';
import { Banner } from '../components/ui';
import { TextField, TextAreaField, SelectField, FormCard } from '../components/Form';

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

export default function StudentForm({ data }) {
  const isEdit = data.mode === 'edit';
  const opt = data.options || {};
  const stu = data.student || {};
  const enrolment = opt.enrolment || null;

  const [f, setF] = useState({
    surname: stu.surname || '', first_name: stu.first_name || '', middle_name: stu.middle_name || '',
    gender: stu.gender || '', date_of_birth: stu.date_of_birth || '', religion: stu.religion || '',
    stream: stu.stream || '', jamb_target: stu.jamb_target === 0 ? '0' : (stu.jamb_target || ''),
    home_address: stu.home_address || '', hobbies: stu.hobbies || '',
  });
  const [contacts, setContacts] = useState(() =>
    (data.contacts && data.contacts.length ? data.contacts : [{ name: '', phone_number: '', relationship: 'Father' }])
      .map((c) => ({ name: c.name || '', phone_number: c.phone_number || '', relationship: c.relationship || 'Father' })));
  const [waec, setWaec] = useState(() => new Set(stu.waec_subjects || []));
  const [jamb, setJamb] = useState(() => new Set(stu.jamb_subjects || []));
  const [enrolId, setEnrolId] = useState(enrolment && enrolment.default_id ? String(enrolment.default_id) : '');
  const [errors, setErrors] = useState({});
  const [contactErrors, setContactErrors] = useState({});
  const [banner, setBanner] = useState(null);
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
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

  const setContact = (i, k, v) => setContacts((cs) => cs.map((c, j) => (j === i ? { ...c, [k]: v } : c)));
  const addContact = () => setContacts((cs) => [...cs, { name: '', phone_number: '', relationship: 'Father' }]);
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
      'contact_name[]': send.map((c) => c.name.trim()),
      'phone_number[]': send.map((c) => c.phone_number.trim()),
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
      if (res.ok && body.ok) { window.location = body.redirect; return; }
      setBanner({ tone: 'error', text: body.error || `Could not save (HTTP ${res.status}).` });
    } catch (err) {
      setBanner({ tone: 'error', text: err.message || 'Network error — please try again.' });
    } finally {
      setSaving(false);
    }
  };

  const urls = data.urls || {};

  return (
    <form onSubmit={submit} noValidate>
      <div className="page-header">
        <div>
          <h1>{isEdit ? 'Edit Student' : 'Add New Student'}</h1>{' '}
          {isEdit && stu.student_id && <span className="badge badge-primary">{stu.student_id}</span>}
        </div>
        {isEdit && (
          <div className="page-header-actions">
            <a href={urls.back} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-arrow-left" /> Back to Profile</a>
            <a href={urls.list} className="btn btn-secondary"><i aria-hidden="true" className="fas fa-users" /> All Students</a>
          </div>
        )}
      </div>

      {banner && <Banner tone={banner.tone} onClose={() => setBanner(null)}>{banner.text}</Banner>}

      <FormCard icon="fa-user" title="Personal Information">
        <div className="sf-row">
          <TextField label="Surname" required value={f.surname} onChange={(v) => set('surname', v)}
                     error={errors.surname} placeholder="Surname" autoComplete="off" />
          <TextField label="First Name" required value={f.first_name} onChange={(v) => set('first_name', v)}
                     error={errors.first_name} placeholder="First name" autoComplete="off" />
        </div>
        <TextField label="Middle Name" value={f.middle_name} onChange={(v) => set('middle_name', v)}
                   placeholder="Middle name (optional)" autoComplete="off" />
        <div className="sf-row">
          <SelectField label="Gender" required value={f.gender} onChange={(v) => set('gender', v)}
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

      <FormCard icon="fa-phone" title="Parent/Guardian Contacts">
        {contacts.map((c, i) => (
          <div className="sf-contact" key={i}>
            <TextField label="Name" value={c.name} onChange={(v) => setContact(i, 'name', v)} placeholder="e.g., Mr. John" autoComplete="off" />
            <TextField label="Phone" required value={c.phone_number} onChange={(v) => setContact(i, 'phone_number', v)}
                       type="tel" placeholder="08012345678" error={contactErrors[i]} autoComplete="off" />
            <SelectField label="Relationship" value={c.relationship} onChange={(v) => setContact(i, 'relationship', v)} options={relationships} />
            <button type="button" className="btn btn-danger btn-sm sf-remove" aria-label={`Remove contact ${i + 1}`}
                    disabled={contacts.length === 1} onClick={() => removeContact(i)}>
              <i aria-hidden="true" className="fas fa-times" />
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-secondary btn-sm" onClick={addContact}>
          <i aria-hidden="true" className="fas fa-plus" /> Add Contact
        </button>
      </FormCard>

      {!isEdit && enrolment && (
        <FormCard icon="fa-chalkboard" title="Class Enrolment" note={`(${enrolment.term_label})`}>
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

      <FormCard icon="fa-file-signature" title="External Exam Subjects" note="(optional)">
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
        <button type="submit" className="btn btn-primary btn-lg" disabled={saving}>
          <i aria-hidden="true" className={'fas ' + (saving ? 'fa-spinner fa-spin' : 'fa-save')} /> {saving ? 'Saving…' : (isEdit ? 'Save Changes' : 'Save Student')}
        </button>
        <a href={urls.cancel} className={'btn btn-secondary btn-lg' + (saving ? ' disabled' : '')}
           onClick={(e) => saving && e.preventDefault()}>Cancel</a>
      </div>
    </form>
  );
}
