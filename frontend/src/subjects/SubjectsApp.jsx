import React, { useState } from 'react';
import { submitJson } from '../lib/forms';
import { useSection, NavCtx, useNav, navParams } from '../lib/section';
import { confirm, Banner, SectionShell, Empty } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Workflow, Scores, BulkEntry, Broadsheet, Affective, Comments, PrintAll } from './results';
import { Analytics, Institution, Teacher, SubjectScorecard } from './analytics';
import { List, SubjectForm, BulkAdd, ClassSubjects, Assign, EditClassSubject } from './catalog';
import { Explore } from './explore';
import { Combine } from './combine';

// Whole numbers print without a trailing .0 (34, not 34.0); genuine decimals to
// two places (34.3 -> 34.30). Non-numeric / blank values pass through.
function fmtNum(v) {
  if (v == null || v === '') return v;
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}



const SCREENS = { list: List, add: SubjectForm, edit: SubjectForm, bulk_add: BulkAdd,
  class_subjects: ClassSubjects, assign: Assign, edit_class_subject: EditClassSubject,
  scores: Scores, workflow: Workflow, bulk_entry: BulkEntry, broadsheet: Broadsheet,
  affective: Affective, comments: Comments, print_all: PrintAll, analytics: Analytics, institution: Institution,
  teacher: Teacher, subject: SubjectScorecard, explore: Explore, combine: Combine };

export default function SubjectsApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || List;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
