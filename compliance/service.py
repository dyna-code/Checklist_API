"""Acknowledgement state and document generation.

The service is deliberately small: it owns "has this request acknowledged the
Agent terms?", derives the checklist answers from that flag, and keeps the
generated DOCX on disk next to the request state.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .catalog import MARK_YES, YES, derive_completion
from .generator import completion_metadata, generate_document

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = BACKEND_DIR / "templates" / "China-AI-Compliance-Checklist-IT-Solution-v1.3.docx"
DEFAULT_STORAGE = BACKEND_DIR / "out"

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InvalidRequestId(ValueError):
    """The request id is not safe to use as a directory name."""


class UnknownRequest(KeyError):
    """No acknowledgement state is stored for this request."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ComplianceService:
    """Turn an acknowledgement into a fully answered checklist document."""

    def __init__(
        self,
        *,
        storage_dir: str | Path = DEFAULT_STORAGE,
        template_path: str | Path = DEFAULT_TEMPLATE,
        mark: str = MARK_YES,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.template_path = Path(template_path)
        self.mark = mark
        if not self.template_path.is_file():
            raise FileNotFoundError(f"checklist template not found: {self.template_path}")

    # -- paths ------------------------------------------------------------

    def _request_dir(self, request_id: str) -> Path:
        if not REQUEST_ID_PATTERN.match(request_id):
            raise InvalidRequestId(f"invalid request id: {request_id!r}")
        return self.storage_dir / request_id

    @staticmethod
    def document_name(request_id: str) -> str:
        return f"China-AI-Compliance-Checklist-IT-Solution-{request_id}.docx"

    def document_path(self, request_id: str) -> Path:
        return self._request_dir(request_id) / self.document_name(request_id)

    def _state_path(self, request_id: str) -> Path:
        return self._request_dir(request_id) / "state.json"

    # -- state ------------------------------------------------------------

    def get_state(self, request_id: str) -> dict | None:
        path = self._state_path(request_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def default_state(self, request_id: str) -> dict:
        """State for a request that has never touched the checkbox."""

        self._request_dir(request_id)  # validates the id
        return {
            "requestId": request_id,
            "termsAcknowledged": False,
            "acknowledgedBy": None,
            "acknowledgedAt": None,
            "answers": {},
            "document": None,
        }

    def _write_state(self, request_id: str, state: dict) -> None:
        directory = self._request_dir(request_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._state_path(request_id).write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # -- behaviour --------------------------------------------------------

    def acknowledge(
        self,
        request_id: str,
        *,
        acknowledged: bool = True,
        actor: str | None = None,
        name: str | None = None,
        storage_location: str | None = None,
        sign_off: str | None = None,
        force: bool = False,
    ) -> dict:
        """Apply the "已阅读" checkbox.

        With ``acknowledged=True`` every checklist question becomes ``Yes`` and
        the DOCX is written, with the Completion Record filled in. Calling it
        again is idempotent unless ``force`` is set. With
        ``acknowledged=False`` the flag is cleared and no document is produced
        (an existing document is kept, so nothing is destroyed).

        ``name`` is the IT-solution name for the record and defaults to the
        request id. ``storage_location`` defaults to the folder holding the
        generated document. ``sign_off`` defaults to ``pending`` because only
        the reviewer can sign.
        """

        existing = self.get_state(request_id)
        document = self.document_path(request_id)

        if not acknowledged:
            state = {
                "requestId": request_id,
                "termsAcknowledged": False,
                "acknowledgedBy": actor or (existing or {}).get("acknowledgedBy"),
                "acknowledgedAt": now_iso(),
                "answers": {},
                "completion": None,
                "document": None,
            }
            self._write_state(request_id, state)
            return state

        question_ids = self._question_ids()
        answers = {question_id: YES for question_id in question_ids}
        derived = derive_completion(answers, question_ids)
        instant = datetime.now().astimezone()
        metadata = completion_metadata(
            name=name or request_id,
            completed_by=f"{actor} / {instant:%Y-%m-%d}" if actor else f"{instant:%Y-%m-%d}",
            skipped=derived["skipped"],
            no_answers=derived["no_answers"],
            not_assessable=derived["not_assessable"],
            result=derived["result"],
            storage_location=storage_location or str(document.parent),
            sign_off=sign_off or "pending",
        )

        if (
            not force
            and existing
            and existing.get("termsAcknowledged") is True
            and existing.get("completion") == metadata
            and document.is_file()
        ):
            return existing

        summary = generate_document(
            self.template_path,
            document,
            answers,
            mark=self.mark,
            metadata=metadata,
        )
        state = {
            "requestId": request_id,
            "termsAcknowledged": True,
            "acknowledgedBy": actor,
            "acknowledgedAt": instant.isoformat(timespec="seconds"),
            "answers": answers,
            "completion": metadata,
            "document": {
                "name": document.name,
                "generatedAt": summary["generatedAt"],
                "sha256": summary["sha256"],
                "questionCount": summary["questionCount"],
                "completionFields": summary["completionFields"],
                "problems": summary["problems"],
            },
        }
        self._write_state(request_id, state)
        return state

    def _question_ids(self) -> tuple[str, ...]:
        # Read the ids from the template so a template revision is picked up
        # automatically; fall back to the known catalog if that ever fails.
        from docx import Document

        from .catalog import QUESTION_IDS
        from .generator import question_ids

        discovered = question_ids(Document(str(self.template_path)))
        return discovered or QUESTION_IDS

