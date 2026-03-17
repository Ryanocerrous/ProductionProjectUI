from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Iterable

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None

try:
    from pdf2image import convert_from_path
except Exception:  # pragma: no cover - optional dependency
    convert_from_path = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None


CATEGORY_KEYS = ("documents", "messages", "photos", "video")
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".log",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".rtf",
    ".eml",
    ".msg",
}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".txt",
    ".md",
    ".csv",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}
MESSAGE_EXTENSIONS = {
    ".sms",
    ".mms",
    ".chat",
    ".log",
    ".json",
    ".xml",
    ".eml",
    ".msg",
    ".db",
    ".sqlite",
}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".3gp", ".webm", ".m4v"}
MESSAGE_FILENAME_HINTS = ("message", "messages", "sms", "mms", "chat", "whatsapp", "telegram", "signal", "imessage")

MAX_TEXT_BYTES = 5 * 1024 * 1024
MAX_RESULTS = 300


@dataclass(slots=True)
class ForensicHit:
    category: str
    file_path: str
    keyword: str
    location: str
    snippet: str
    source: str


@dataclass(slots=True)
class ForensicSearchResult:
    selected_categories: list[str]
    keywords: list[str]
    files_scanned: int = 0
    hits: list[ForensicHit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ForensicLlmTriage:
    hit: ForensicHit
    category: str
    suspicion_score: int
    rationale: str
    raw_output: str
    error: str = ""


def parse_keywords(raw: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"[,\n]+", raw)]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = part.lower()
        if not part or token in seen:
            continue
        seen.add(token)
        deduped.append(part)
    return deduped


def run_forensic_keyword_search(root_dir: Path, keywords: list[str], categories: Iterable[str]) -> ForensicSearchResult:
    normalized_categories = _normalize_categories(categories)
    result = ForensicSearchResult(selected_categories=sorted(normalized_categories), keywords=keywords)
    if not keywords:
        result.warnings.append("No keywords provided.")
        return result
    if not root_dir.exists() or not root_dir.is_dir():
        result.warnings.append(f"Search root does not exist or is not a directory: {root_dir}")
        return result

    compiled = {kw: re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords}
    for path in root_dir.rglob("*"):
        if not path.is_file():
            continue
        category = _classify_file(path)
        if category is None or category not in normalized_categories:
            continue
        if len(result.hits) >= MAX_RESULTS:
            result.warnings.append(f"Result limit ({MAX_RESULTS}) reached; refine keywords or scope.")
            break

        result.files_scanned += 1
        try:
            file_hits, file_warnings = _search_file(path, category, compiled)
        except Exception as exc:  # pragma: no cover - defensive guard
            result.warnings.append(f"Skipped {path}: {exc}")
            continue
        result.hits.extend(file_hits)
        for warning in file_warnings:
            if warning not in result.warnings:
                result.warnings.append(warning)
        if len(result.hits) >= MAX_RESULTS:
            result.hits = result.hits[:MAX_RESULTS]
            result.warnings.append(f"Result limit ({MAX_RESULTS}) reached; refine keywords or scope.")
            break
    return result


def triage_hits_with_llm(
    result: ForensicSearchResult,
    cfg: dict[str, Any],
    max_items: int = 5,
) -> list[ForensicLlmTriage]:
    """Run local LLM triage on search-hit snippets.

    This is intentionally opt-in and called by higher-level workflows only.
    """
    llm_cfg = dict((cfg.get("llm") or {}))
    if not bool(llm_cfg.get("enabled", False)):
        return []

    try:
        from logic.local_llm import classify_text_with_llama
    except Exception as exc:
        raise RuntimeError(f"LLM module import failed: {exc}") from exc

    triaged: list[ForensicLlmTriage] = []
    limit = max(0, int(max_items))
    for hit in result.hits[:limit]:
        chunk = (
            f"Category: {hit.category}\n"
            f"Keyword: {hit.keyword}\n"
            f"File: {hit.file_path}\n"
            f"Location: {hit.location}\n"
            f"Source: {hit.source}\n"
            f"Snippet: {hit.snippet}\n"
        )
        try:
            cls = classify_text_with_llama(chunk, cfg)
            triaged.append(
                ForensicLlmTriage(
                    hit=hit,
                    category=cls.category,
                    suspicion_score=cls.suspicion_score,
                    rationale=cls.rationale,
                    raw_output=cls.raw_output,
                )
            )
        except Exception as exc:
            triaged.append(
                ForensicLlmTriage(
                    hit=hit,
                    category="unknown",
                    suspicion_score=0,
                    rationale="",
                    raw_output="",
                    error=str(exc),
                )
            )
    return triaged


def _normalize_categories(categories: Iterable[str]) -> set[str]:
    selected = {c.strip().lower() for c in categories if c and c.strip()}
    if "all" in selected:
        return set(CATEGORY_KEYS)
    normalized = selected.intersection(CATEGORY_KEYS)
    return normalized or set(CATEGORY_KEYS)


def _classify_file(path: Path) -> str | None:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return "photos"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in MESSAGE_EXTENSIONS or any(hint in name for hint in MESSAGE_FILENAME_HINTS):
        return "messages"
    if suffix in DOCUMENT_EXTENSIONS:
        return "documents"
    return None


def _search_file(path: Path, category: str, keywords: dict[str, re.Pattern[str]]) -> tuple[list[ForensicHit], list[str]]:
    warnings: list[str] = []
    hits = _search_filename(path, category, keywords)
    suffix = path.suffix.lower()

    if category == "documents" and suffix == ".pdf":
        pdf_hits, pdf_warnings = _search_pdf(path, category, keywords)
        hits.extend(pdf_hits)
        warnings.extend(pdf_warnings)
        return hits, warnings

    if category in {"documents", "messages"}:
        if suffix not in TEXT_EXTENSIONS:
            return hits, warnings
        text = _read_text_file(path)
        if text:
            hits.extend(_hits_for_text(path, category, "content", text, keywords, location_label="file"))
        return hits, warnings

    if category == "photos":
        if pytesseract is None or Image is None:
            warnings.append("Photo OCR unavailable (install Pillow and pytesseract).")
            return hits, warnings
        image_text = _ocr_image(path)
        if image_text:
            hits.extend(_hits_for_text(path, category, "ocr", image_text, keywords, location_label="image"))
        return hits, warnings

    # Video and unsupported binary formats fall back to filename-only matching.
    return hits, warnings


def _search_filename(path: Path, category: str, keywords: dict[str, re.Pattern[str]]) -> list[ForensicHit]:
    lowered_name = path.name.lower()
    hits: list[ForensicHit] = []
    for keyword in keywords:
        if keyword.lower() in lowered_name:
            hits.append(
                ForensicHit(
                    category=category,
                    file_path=str(path),
                    keyword=keyword,
                    location="filename",
                    snippet=path.name,
                    source="filename",
                )
            )
    return hits


def _read_text_file(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return ""
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def _search_pdf(path: Path, category: str, keywords: dict[str, re.Pattern[str]]) -> tuple[list[ForensicHit], list[str]]:
    hits: list[ForensicHit] = []
    warnings: list[str] = []
    pages = _extract_pdf_pages_text(path)
    if PdfReader is None and pdfplumber is None:
        warnings.append("PDF text extraction unavailable (install pypdf or pdfplumber).")
    if not pages or not any(text.strip() for _, text, _ in pages):
        if pytesseract is None:
            warnings.append("PDF OCR fallback unavailable (install pytesseract and pdf2image).")
        else:
            ocr_pages = _extract_pdf_pages_ocr(path)
            pages = ocr_pages if ocr_pages else pages

    for page_no, text, source in pages:
        if not text.strip():
            continue
        hits.extend(
            _hits_for_text(
                path,
                category,
                source,
                text,
                keywords,
                location_label=f"page {page_no}",
            )
        )
    return hits, warnings


def _extract_pdf_pages_text(path: Path) -> list[tuple[int, str, str]]:
    pages: list[tuple[int, str, str]] = []
    if PdfReader is not None:
        reader = PdfReader(str(path))
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append((index, text, "pdf_text"))
        return pages
    if pdfplumber is not None:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append((index, text, "pdf_text"))
        return pages
    return pages


def _extract_pdf_pages_ocr(path: Path) -> list[tuple[int, str, str]]:
    if pytesseract is None:
        return []
    if convert_from_path is not None:
        images = convert_from_path(str(path), dpi=200)
        pages: list[tuple[int, str, str]] = []
        for index, image in enumerate(images, start=1):
            text = pytesseract.image_to_string(image) or ""
            pages.append((index, text, "pdf_ocr"))
        return pages
    return _extract_pdf_pages_ocr_via_tesseract_cli(path)


def _extract_pdf_pages_ocr_via_tesseract_cli(path: Path) -> list[tuple[int, str, str]]:
    with TemporaryDirectory(prefix="bb_pdf_ocr_") as tmp_dir:
        base = Path(tmp_dir) / "ocr"
        cmd = ["tesseract", str(path), str(base), "--dpi", "200", "txt"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return []
        text_path = base.with_suffix(".txt")
        if not text_path.exists():
            return []
        text = text_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            return []
        return [(1, text, "pdf_ocr")]


def _ocr_image(path: Path) -> str:
    if pytesseract is None or Image is None:
        return ""
    with Image.open(path) as image:
        return pytesseract.image_to_string(image) or ""


def _hits_for_text(
    path: Path,
    category: str,
    source: str,
    text: str,
    keywords: dict[str, re.Pattern[str]],
    location_label: str,
) -> list[ForensicHit]:
    hits: list[ForensicHit] = []
    normalized_text = _normalize_whitespace(text)
    for keyword, pattern in keywords.items():
        match = pattern.search(normalized_text)
        if not match:
            continue
        hits.append(
            ForensicHit(
                category=category,
                file_path=str(path),
                keyword=keyword,
                location=location_label,
                snippet=_snippet(normalized_text, match.start(), match.end()),
                source=source,
            )
        )
    return hits


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _snippet(value: str, start: int, end: int, radius: int = 70) -> str:
    left = max(start - radius, 0)
    right = min(end + radius, len(value))
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(value) else ""
    return f"{prefix}{value[left:right]}{suffix}"
