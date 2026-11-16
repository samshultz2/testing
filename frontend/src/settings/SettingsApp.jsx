import React, { useState } from 'react';
import { submitJson, postFile, useSave } from '../lib/forms';
import { csrfToken } from '../lib/api';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty, FileUpload } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Index, Branches, Backup, Audit, School, Academic, Grades, Traits, Assessments, TimetableSlots, Ocr } from './Hub';

// Small helpers ---------------------------------------------------------------
function Actions({ children }) {
  return <div className="page-header-actions">{children}</div>;
}

const SCREENS = {
  index: Index, school: School, academic: Academic, grades: Grades, traits: Traits,
  assessments: Assessments, timetable_slots: TimetableSlots, backup: Backup,
  branches: Branches,
  audit: Audit, ocr: Ocr,
};

// Native-app style back button on every settings page below the hub. Goes back
// in history when we came from inside the app, else to the Settings hub.
function BackBar() {
  const nav = useNav();
  const back = () => {
    const st = window.history.state;
    let sameSite = false;
    try { sameSite = !!document.referrer && new URL(document.referrer).origin === window.location.origin; } catch (e) { /* ignore */ }
    if ((st && st.spa) || sameSite) window.history.back();
    else nav.go('/settings/');
  };
  return (
    <button type="button" className="nav-back" onClick={back} aria-label="Back to Settings">
      <i className="fas fa-chevron-left" aria-hidden="true" /><span>Settings</span>
    </button>
  );
}

export default function SettingsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {d.page !== 'index' && <BackBar />}
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
