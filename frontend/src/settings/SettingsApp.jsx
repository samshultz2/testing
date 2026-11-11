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

export default function SettingsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Index;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
