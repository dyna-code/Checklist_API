"""Render a filled checklist DOCX from the official template.

The template keeps its ballot boxes as plain ``☐`` characters inside the table
cells, so filling the checklist is a targeted character replacement per
question row. Nothing else in the template is touched, which keeps the
reviewed wording, sources, gates and version history intact.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from docx import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from .catalog import (
    ANSWERS,
    BOX_EMPTY,
    FIELD_COMPLETED,
    FIELD_NAME,
    FIELD_NOT_ASSESSABLE,
    FIELD_NO_ANSWERS,
    FIELD_RESULT,
    FIELD_SIGN_OFF,
    FIELD_SKIPPED,
    FIELD_STORAGE,
    ID_COL,
    MARK_YES,
    NA,
    NA_COL,
    NO,
    NO_COL,
    QUESTION_HEADER,
    RESULT_ACTION,
    RESULT_LEGAL,
    RESULT_UNCLEAR,
    STEP0_PREFIX,
    STEP0_TOKENS,
    YES,
    YES_COL,
)


class TemplateError(RuntimeError):
    """The template does not look like the reviewed checklist."""


# --------------------------------------------------------------------------
# reading helpers
# --------------------------------------------------------------------------


def cell_text(cell: _Cell) -> str:
    return " ".join(paragraph.text for paragraph in cell.paragraphs).strip()


def is_question_table(table: Table) -> bool:
    if len(table.columns) < 5 or len(table.rows) < 2:
        return False
    header = tuple(cell_text(cell) for cell in table.rows[0].cells[:5])
    return header == QUESTION_HEADER


def iter_question_rows(doc) -> list[tuple[str, object]]:
    """Return ``(question_id, row)`` for every question row in document order."""

    rows: list[tuple[str, object]] = []
    for table in doc.tables:
        if not is_question_table(table):
            continue
        for row in table.rows[1:]:
            question_id = cell_text(row.cells[ID_COL])
            if question_id:
                rows.append((question_id, row))
    return rows


def question_ids(doc) -> tuple[str, ...]:
    return tuple(question_id for question_id, _ in iter_question_rows(doc))


def _completion_table(doc) -> Table | None:
    for table in doc.tables:
        if len(table.columns) == 2 and cell_text(table.rows[0].cells[0]) == "Field":
            return table
    return None


def _step0_paragraph(doc) -> Paragraph | None:
    for paragraph in doc.paragraphs:
        if paragraph.text.strip().startswith(STEP0_PREFIX):
            return paragraph
    return None


# --------------------------------------------------------------------------
# writing helpers
# --------------------------------------------------------------------------


def set_cell_text(cell: _Cell, text: str) -> None:
    """Replace a cell's text, keeping the formatting of its first run."""

    paragraph = cell.paragraphs[0]
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)
    for extra in cell.paragraphs[1:]:
        for run in extra.runs:
            run.text = ""


def _replace_char(paragraph: Paragraph, index: int, replacement: str) -> bool:
    """Replace the character at ``index`` of the paragraph's text."""

    cursor = 0
    for run in paragraph.runs:
        length = len(run.text)
        if cursor <= index < cursor + length:
            offset = index - cursor
            run.text = run.text[:offset] + replacement + run.text[offset + 1 :]
            return True
        cursor += length
    return False


def mark_step0(paragraph: Paragraph, token: str) -> None:
    """Tick one MM-641.48 category box (``AI-2`` and similar)."""

    if token not in STEP0_TOKENS:
        raise ValueError(f"unknown Step 0 category: {token!r}")
    text = paragraph.text
    position = text.find(token)
    if position == -1:
        raise TemplateError(f"Step 0 token {token!r} not found in the paragraph")
    box = text.rfind(BOX_EMPTY, 0, position)
    if box == -1:
        raise TemplateError(f"no ballot box before {token!r} in Step 0")
    if not _replace_char(paragraph, box, MARK_YES):
        raise TemplateError("could not rewrite the Step 0 ballot box")


def _set_completion_result(cell: _Cell, result: str) -> None:
    wanted = {
        RESULT_LEGAL: "[x] " + RESULT_LEGAL,
        RESULT_ACTION: "[x] " + RESULT_ACTION,
        RESULT_UNCLEAR: "[x] " + RESULT_UNCLEAR,
    }
    if result not in wanted:
        raise ValueError(f"unknown result: {result!r}")
    text = " ".join(
        f"[ ] {label}" for label in (RESULT_LEGAL, RESULT_ACTION, RESULT_UNCLEAR)
    )
    for label, marked in wanted.items():
        if label == result:
            text = text.replace(f"[ ] {label}", marked)
    set_cell_text(cell, text)


def _fill_completion(doc, values: Mapping[str, str]) -> list[str]:
    table = _completion_table(doc)
    if table is None:
        raise TemplateError("completion record table not found")
    filled: list[str] = []
    for row in table.rows[1:]:
        field = cell_text(row.cells[0])
        if field not in values:
            continue
        value = values[field]
        if field == FIELD_RESULT:
            _set_completion_result(row.cells[1], value)
        else:
            set_cell_text(row.cells[1], value)
        filled.append(field)
    return filled


def _mark_answers(doc, answers: Mapping[str, str], mark: str) -> list[str]:
    marked: list[str] = []
    for question_id, row in iter_question_rows(doc):
        answer = answers.get(question_id)
        if answer is None:
            raise ValueError(f"no answer supplied for question {question_id}")
        if answer not in ANSWERS:
            raise ValueError(f"invalid answer {answer!r} for question {question_id}")
        desired = {
            YES_COL: mark if answer == YES else BOX_EMPTY,
            NO_COL: mark if answer == NO else BOX_EMPTY,
            NA_COL: mark if answer == NA else BOX_EMPTY,
        }
        for column, value in desired.items():
            cell = row.cells[column]
            # Skip no-op writes so a generated file differs from the template
            # only where an answer actually changed.
            if cell_text(cell) != value:
                set_cell_text(cell, value)
        marked.append(question_id)
    return marked


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def verify_document(path: str | Path, mark: str = MARK_YES) -> list[str]:
    """Return a list of problems; empty means every question is answered Yes."""

    doc = Document(str(path))
    problems: list[str] = []
    rows = iter_question_rows(doc)
    if not rows:
        return ["no question tables found"]
    for question_id, row in rows:
        yes = cell_text(row.cells[YES_COL])
        if yes != mark:
            problems.append(f"{question_id}: Yes is {yes!r}")
        for label, column in (("No", NO_COL), ("Not assessable", NA_COL)):
            value = cell_text(row.cells[column])
            if value != BOX_EMPTY:
                problems.append(f"{question_id}: {label} is {value!r}")
    return problems


def generate_document(
    template_path: str | Path,
    output_path: str | Path,
    answers: Mapping[str, str] | None = None,
    *,
    mark: str = MARK_YES,
    metadata: Mapping[str, str] | None = None,
    step0: str | None = None,
) -> dict:
    """Write a filled checklist DOCX and return a summary of what was written.

    ``answers`` defaults to "every question answered Yes", which is the
    behaviour driven by the frontend acknowledgement checkbox.
    """

    template_path = Path(template_path)
    output_path = Path(output_path)
    doc = Document(str(template_path))

    available = question_ids(doc)
    if not available:
        raise TemplateError(f"{template_path.name} has no question tables")
    if answers is None:
        answers = {question_id: YES for question_id in available}

    unknown = sorted(set(answers) - set(available))
    if unknown:
        raise ValueError(f"answers contain unknown questions: {', '.join(unknown)}")

    marked = _mark_answers(doc, answers, mark)
    if step0:
        paragraph = _step0_paragraph(doc)
        if paragraph is None:
            raise TemplateError("Step 0 paragraph not found")
        mark_step0(paragraph, step0)

    filled_fields = _fill_completion(doc, metadata) if metadata else []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))

    payload = output_path.read_bytes()
    return {
        "template": str(template_path),
        "output": str(output_path),
        "mark": mark,
        "questionCount": len(marked),
        "questionIds": marked,
        "completionFields": filled_fields,
        "step0": step0,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "problems": verify_document(output_path, mark),
    }


def completion_metadata(
    *,
    name: str | None = None,
    completed_by: str | None = None,
    skipped: Iterable[str] = (),
    no_answers: Iterable[str] = (),
    not_assessable: str = "none",
    result: str | None = None,
    storage_location: str | None = None,
    sign_off: str | None = None,
) -> dict[str, str]:
    """Build the ``metadata`` mapping used by :func:`generate_document`."""

    values: dict[str, str] = {}
    if name is not None:
        values[FIELD_NAME] = name
    if completed_by is not None:
        values[FIELD_COMPLETED] = completed_by
    skipped_list = list(skipped)
    values[FIELD_SKIPPED] = ", ".join(skipped_list) if skipped_list else "none"
    no_answer_list = list(no_answers)
    values[FIELD_NO_ANSWERS] = ", ".join(no_answer_list) if no_answer_list else "none"
    values[FIELD_NOT_ASSESSABLE] = not_assessable
    if result is not None:
        values[FIELD_RESULT] = result
    if storage_location is not None:
        values[FIELD_STORAGE] = storage_location
    if sign_off is not None:
        values[FIELD_SIGN_OFF] = sign_off
    return values
