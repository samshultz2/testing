import React from 'react';

// Attendance rosters are shown split by gender — boys first, then girls, each
// group alphabetical by surname. The server already returns students in that
// order (see utils.calculations.roster_order); these helpers draw the
// "Boys"/"Girls" group header at each boundary so the React register matches
// the server-rendered pages.

export function genderLabel(gender) {
  const g = (gender || '').trim().toLowerCase();
  if (g.startsWith('m')) return 'Boys';
  if (g.startsWith('f')) return 'Girls';
  return gender || 'Other';
}

// Walk a gender-ordered student list and emit a group header before each new
// gender block. `renderHead(gender, first, key)` and `renderRow(student, i)`
// return React nodes; the result is a flat array ready to drop into a <tbody>,
// <ul>, or grid container.
export function withGroups(students, renderHead, renderRow) {
  const out = [];
  (students || []).forEach((s, i) => {
    const first = i === 0;
    if (first || students[i - 1].gender !== s.gender) {
      out.push(renderHead(s.gender, first, `rg-${i}`));
    }
    out.push(renderRow(s, i));
  });
  return out;
}

// Shared inline style for a group-header label (used across screens).
export const groupHeadStyle = {
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '.03em',
  fontSize: 'var(--text-sm)',
  color: 'var(--text-muted)',
  borderBottom: '2px solid var(--border-color)',
};

// A full-width group-header row for tables, with a blank spacer above every
// group after the first so boys and girls read as clearly separate blocks.
export function GroupHeadRow({ gender, first, colSpan }) {
  return (
    <React.Fragment>
      {!first && (
        <tr className="att-group-gap" aria-hidden="true">
          <td colSpan={colSpan} style={{ height: 14, border: 'none', padding: 0 }} />
        </tr>
      )}
      <tr className="att-group-head">
        <td colSpan={colSpan} style={groupHeadStyle}>{genderLabel(gender)}</td>
      </tr>
    </React.Fragment>
  );
}
