"""Dump the block and table structure of a checklist DOCX template.

Usage:
    python backend/tools/inspect_template.py <path-to-docx>
"""

from __future__ import annotations

import sys

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_blocks(doc):
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def cell_text(cell) -> str:
    return " ".join(p.text for p in cell.paragraphs).strip()


def main(path: str) -> None:
    doc = Document(path)
    table_index = 0
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                print(f"[P] style={block.style.name!r} {text[:140]!r}")
            continue
        table_index += 1
        print(f"[TABLE {table_index}] rows={len(block.rows)} cols={len(block.columns)}")
        for row_no, row in enumerate(block.rows):
            cells = [cell_text(cell) for cell in row.cells]
            print(f"   r{row_no}: {cells}")
    print(f"tables={table_index}")


if __name__ == "__main__":
    main(sys.argv[1])
