#!/usr/bin/env python3
"""Import each subject's bundled coded syllabus (if not already imported) and
AI-retag its untagged bank questions against it -- the batch version of what
Bank -> Coded Syllabus Manager does one subject at a time, for every subject
that has a matching bundled syllabus in data/jamb_syllabi/.

Safe/idempotent: importing an already-imported syllabus just reconciles it
(matches on stable node codes, never duplicates); the default --mode=untagged
only ever tags questions that have no code yet -- it never re-tags or
overwrites an existing code. --dry-run reports what would happen and makes no
network calls, so it costs nothing.

Needs the school's own Anthropic API key configured under
Settings -> AI Vision OCR -- this is read from that school's own database at
run time, not from this machine's environment.

    # single-school deployment (MULTI_TENANT off, the common case): run this
    # directly on that school's own server/container, using its own env/DB.
    python scripts/retag_remaining_subjects.py --dry-run
    python scripts/retag_remaining_subjects.py --apply

    # central multi-tenant ops (MULTI_TENANT on): target one or every school
    # from the control plane.
    python scripts/retag_remaining_subjects.py --subdomain myschool --dry-run
    python scripts/retag_remaining_subjects.py --all --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

_SYLLABI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'data', 'jamb_syllabi')


def _bundled_syllabi():
    """{slug: absolute path} for every bundled syllabus JSON shipped in the repo."""
    out = {}
    try:
        for fn in sorted(os.listdir(_SYLLABI_DIR)):
            if fn.endswith('.json'):
                out[fn[:-5]] = os.path.join(_SYLLABI_DIR, fn)
    except OSError:
        pass
    return out


def _process(dry_run, mode):
    """Runs inside an active app context. Returns a list of report lines."""
    from models import db, Subject, MockJAMBSyllabus, MockJAMBQuestion
    from utils.jamb_blueprint import norm_subject
    from utils.jamb_syllabus_import import import_syllabus, parse, SyllabusImportError
    from utils.mock_bank_coded_retag import coded_retag

    report = []
    parsed_by_slug = {}
    for slug, path in _bundled_syllabi().items():
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        try:
            declared = parse(text, fmt='json').get('subject')
        except SyllabusImportError:
            declared = None
        parsed_by_slug[slug] = (text, declared)

    # Only subjects that actually have bank questions are worth touching.
    subj_ids = [sid for (sid,) in db.session.query(MockJAMBQuestion.subject_id)
                .filter(MockJAMBQuestion.mock_exam_id.is_(None)).distinct().all()]
    subjects = Subject.query.filter(Subject.id.in_(subj_ids)).all() if subj_ids else []
    if not subjects:
        return ['No bank questions found for any subject -- nothing to do.']

    for subject in sorted(subjects, key=lambda s: s.name.lower()):
        key = norm_subject(subject.name)
        has_syllabus = MockJAMBSyllabus.query.filter_by(subject_id=subject.id).first() is not None

        if not has_syllabus:
            match = next(((slug, text) for slug, (text, declared) in parsed_by_slug.items()
                         if declared and norm_subject(declared) == key), None)
            if not match:
                report.append(f'{subject.name}: no bundled syllabus available -- skipped')
                continue
            slug, text = match
            if dry_run:
                report.append(f'{subject.name}: would import bundled syllabus "{slug}"')
            else:
                try:
                    diff = import_syllabus(subject, text, fmt='json')
                    report.append(f'{subject.name}: imported "{slug}" '
                                  f'({diff["sections"]} sections, {diff["topics"]} topics, '
                                  f'{diff["items"]} items)')
                except SyllabusImportError as e:
                    report.append(f'{subject.name}: syllabus import FAILED: {e}')
                    continue

        if dry_run:
            report.append(f'{subject.name}: would retag (mode={mode})')
            continue

        res = coded_retag(subject, mode=mode)
        err = res.get('error')
        if err == 'no_key':
            report.append(f'{subject.name}: no Anthropic API key configured -- skipped')
        elif err == 'not_installed':
            report.append(f'{subject.name}: "anthropic" package not installed on this server -- skipped')
        elif err == 'no_syllabus':
            report.append(f'{subject.name}: no syllabus to retag against -- skipped')
        else:
            more = ' (capped -- run again to continue)' if res.get('capped') else ''
            report.append(f'{subject.name}: tagged {res["tagged"]}/{res["scanned"]} '
                          f'(outside syllabus: {res["outside"]}, still untagged: '
                          f'{res["still_untagged"]}){more}')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--subdomain', help='One school to process (multi-tenant control plane).')
    ap.add_argument('--all', action='store_true',
                    help='Process every active school (multi-tenant control plane).')
    ap.add_argument('--mode', choices=['untagged', 'all'], default='untagged',
                    help='untagged (default): only tag questions with no code yet. '
                         'all: re-tag every question, even already-coded ones.')
    ap.add_argument('--dry-run', action='store_true', default=True,
                    help='Report what would happen; import/tag nothing, spend nothing. Default.')
    ap.add_argument('--apply', dest='dry_run', action='store_false',
                    help='Actually import syllabi and call the AI retagger (spends API credits).')
    args = ap.parse_args()

    if args.subdomain or args.all:
        from utils import tenancy, tenant_admin
        tenancy.init_control_plane()
        if args.subdomain:
            t = tenancy.get_tenant(args.subdomain)
            if not t or t.status != 'active' or not t.database_url:
                print(f'No active school "{args.subdomain}".')
                return 1
            targets = [t]
        else:
            targets = tenant_admin.active_tenants()
        if not targets:
            print('No active schools to process.')
            return 0
        for t in targets:
            print(f'\n=== {t.subdomain} ===')
            app = tenant_admin.tenant_app(t.database_url)
            try:
                with app.app_context():
                    for line in _process(args.dry_run, args.mode):
                        print(' ', line)
            except Exception as e:
                print(f'  ERROR: {e}')
    else:
        # Single-school deployment: whatever DATABASE_URL/env this process
        # is already configured with (run this on the school's own server).
        from app import create_app
        app = create_app()
        with app.app_context():
            for line in _process(args.dry_run, args.mode):
                print(line)

    if args.dry_run:
        print('\n(dry run -- nothing was imported or tagged; re-run with --apply to do it for real)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
