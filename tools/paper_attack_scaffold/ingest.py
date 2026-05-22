from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class IngestBundle:
    markdown: str
    structured_paper: dict[str, Any]
    notes_text: str
    input_manifest: dict[str, Any]


def ingest_inputs(
    *,
    paper_text_path: str | None,
    pdf_path: str | None,
    notes_path: str | None,
    paper_url: str | None,
) -> IngestBundle:
    if not paper_text_path and not pdf_path:
        raise ValueError("One of --paper-text-path or --pdf-path is required.")
    if paper_text_path and pdf_path:
        raise ValueError("Use only one of --paper-text-path or --pdf-path at a time.")

    notes_text = _read_optional_text(notes_path)
    manifest: dict[str, Any] = {
        "paper_url": paper_url or "",
        "paper_text_path": paper_text_path or "",
        "pdf_path": pdf_path or "",
        "notes_path": notes_path or "",
        "docling_backend": None,
        "ocr_enabled": False,
    }

    if paper_text_path:
        path = Path(paper_text_path)
        markdown = path.read_text(encoding="utf-8")
        structured = _markdown_to_structured_json(markdown, source_path=str(path))
        manifest["ingest_backend"] = "plaintext"
        return IngestBundle(
            markdown=markdown,
            structured_paper=structured,
            notes_text=notes_text,
            input_manifest=manifest,
        )

    path = Path(pdf_path or "")
    markdown, structured = _convert_pdf_with_docling(path)
    manifest["ingest_backend"] = "docling"
    manifest["docling_backend"] = "python_api"
    manifest["docling_source"] = str(path)
    return IngestBundle(
        markdown=markdown,
        structured_paper=structured,
        notes_text=notes_text,
        input_manifest=manifest,
    )


def _convert_pdf_with_docling(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        from docling.document_converter import DocumentConverter
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Docling is required for --pdf-path. Install it with `pip install docling`."
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(path)
    document = result.document
    markdown = document.export_to_markdown()
    structured = _export_docling_document(document)
    if not isinstance(structured, dict):
        structured = {"docling_document": structured}
    structured.setdefault("source_path", str(path))
    structured.setdefault("export_backend", "docling")
    return markdown, structured


def _export_docling_document(document: Any) -> dict[str, Any]:
    for attr in ("export_to_dict", "model_dump", "dict"):
        method = getattr(document, attr, None)
        if callable(method):
            data = method()
            if isinstance(data, dict):
                return data
    try:
        return json.loads(document.export_to_json())
    except Exception:
        return {"docling_export_unavailable": True}


def _read_optional_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def _markdown_to_structured_json(markdown: str, *, source_path: str) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    current_heading = ""
    paragraph_index = 0
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            current_heading = line.lstrip("#").strip()
            blocks.append(
                {
                    "block_id": f"heading:{len(blocks) + 1}",
                    "type": "heading",
                    "heading_level": len(line) - len(line.lstrip("#")),
                    "text": current_heading,
                }
            )
            continue
        paragraph_index += 1
        blocks.append(
            {
                "block_id": f"paragraph:{paragraph_index}",
                "type": "paragraph",
                "section": current_heading,
                "text": line.strip(),
            }
        )
    return {
        "source_path": source_path,
        "export_backend": "plaintext",
        "blocks": blocks,
    }
