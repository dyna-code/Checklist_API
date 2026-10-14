"""Static facts about the checklist template.

The template is the reviewed DOCX
``China-AI-Compliance-Checklist-IT-Solution-v1.3.docx``. Question tables use
the header ``# | Question | Yes | No | Not assessable``; Sections A-I map to
the first nine tables of the document.
"""

from __future__ import annotations

# Ballot-box glyphs used by the template. "Empty" is what the template ships.
BOX_EMPTY = "\u2610"  # ☐
MARK_YES = "\u2611"  # ☑  ballot box with check
MARK_YES_X = "\u2612"  # ☒  ballot box with X

# Answer vocabulary.
YES = "Yes"
NO = "No"
NA = "Not assessable"
ANSWERS = (YES, NO, NA)

# Question-table geometry.
QUESTION_HEADER = ("#", "Question", "Yes", "No", "Not assessable")
ID_COL = 0
QUESTION_COL = 1
YES_COL = 2
NO_COL = 3
NA_COL = 4

# Expected shape of the template (used to fail fast when the template changes).
SECTION_QUESTIONS = {
    "A": 7,
    "B": 3,
    "C": 2,
    "D": 3,
    "E": 3,
    "F": 3,
    "G": 3,
    "H": 1,
    "I": 1,
}

QUESTION_IDS: tuple[str, ...] = tuple(
    f"{section}{index}"
    for section, count in SECTION_QUESTIONS.items()
    for index in range(1, count + 1)
)

# Completion Record field labels, as written in the template.
FIELD_NAME = "IT-Solution / AI system name"
FIELD_COMPLETED = "Completed by / Date"
FIELD_SKIPPED = "Section(s) skipped"
FIELD_NO_ANSWERS = "No answers"
FIELD_NOT_ASSESSABLE = "Not assessable answers (question IDs and missing information)"
FIELD_RESULT = "Result"
FIELD_STORAGE = "Storage location"
FIELD_SIGN_OFF = "Reviewer sign-off"

RESULT_LEGAL = "Legal as described"
RESULT_ACTION = "Action required"
RESULT_UNCLEAR = "Cannot determine"

STEP0_PREFIX = "Step 0"
STEP0_TOKENS = ("AI-1", "AI-2", "AI-3", "AI-4")


def all_yes() -> dict[str, str]:
    """Every known question answered ``Yes``."""
    return {question_id: YES for question_id in QUESTION_IDS}
