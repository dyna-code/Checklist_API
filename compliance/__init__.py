"""Backend support for the China AI compliance checklist.

The flow this package implements: the frontend ticks the "已阅读" (terms
acknowledged) checkbox, the backend flips every checklist question to "Yes"
and writes a filled DOCX that follows the official template.

No pre-filling or skip logic is applied - every question in every active
section is answered "Yes".
"""

from .catalog import MARK_YES, MARK_YES_X, QUESTION_IDS
from .generator import generate_document, verify_document
from .service import ComplianceService

__all__ = [
    "MARK_YES",
    "MARK_YES_X",
    "QUESTION_IDS",
    "ComplianceService",
    "generate_document",
    "verify_document",
]
