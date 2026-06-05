"""
JAMB / Mock JAMB scoring configuration and helpers.

In the JAMB (UTME) format, the English Language paper has 60 questions while
every other subject has 40 questions. Each subject is reported over 100, so a
student's raw number of correct answers must be scaled to a value out of 100
before the four subjects are summed into the final score (out of 400).

This module centralises that domain knowledge so routes, models and templates
all agree on a single source of truth.
"""

# Number of questions per subject in the JAMB/UTME format.
DEFAULT_QUESTION_COUNT = 40
ENGLISH_QUESTION_COUNT = 60

# Subjects (by exact name) that use the 60-question English paper.
ENGLISH_SUBJECTS = {
    'English Language',
    'English',
    'Use of English',
}

# The subject that JAMB makes compulsory and that should be pre-selected.
COMPULSORY_SUBJECT = 'English Language'

# Maximum score for a single subject and for the whole exam.
MAX_SUBJECT_SCORE = 100
MAX_TOTAL_SCORE = 400


def question_count_for(subject):
    """Return how many questions a given subject has in the JAMB format."""
    if subject and subject.strip() in ENGLISH_SUBJECTS:
        return ENGLISH_QUESTION_COUNT
    return DEFAULT_QUESTION_COUNT


def convert_correct_to_100(subject, correct):
    """
    Convert a raw number of correct answers into a score out of 100.

    Example: 30 correct in Mathematics (40 questions) -> round(30/40*100) = 75.
    Returns ``None`` when there is no value to convert so callers can tell the
    difference between "0 correct" and "left blank".
    """
    if correct is None or correct == '':
        return None
    try:
        correct = int(correct)
    except (TypeError, ValueError):
        return None

    questions = question_count_for(subject)
    if questions <= 0:
        return None

    correct = max(0, min(correct, questions))
    return round(correct / questions * MAX_SUBJECT_SCORE)


def question_count_map(subjects):
    """Build a {subject_name: question_count} map for a list of subjects."""
    return {subject: question_count_for(subject) for subject in subjects}
