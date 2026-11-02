"""Turn uploaded bytes into text sections. Parsers only read data; nothing in a document is executed."""

import csv
import io
import re
from dataclasses import dataclass

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}


class ExtractionError(Exception):
    pass


@dataclass
class Section:
    text: str
    page: int | None = None
    section: str | None = None


def file_ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def validate_bytes(filename: str, data: bytes) -> str:
    """Check extension against actual content. Returns the canonical content type."""
    ext = file_ext(filename)
    if ext not in ALLOWED:
        raise ExtractionError(f"Unsupported file type '{ext or filename}'. Allowed: {', '.join(ALLOWED)}")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise ExtractionError("File is not a valid PDF")
    if ext in (".docx", ".xlsx") and not data.startswith(b"PK"):
        raise ExtractionError(f"File is not a valid {ext} document")
    if ext in (".txt", ".md", ".csv"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ExtractionError("Text files must be UTF-8 encoded") from None
    return ALLOWED[ext]


def _clean(s: str) -> str:
    s = s.replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def extract(filename: str, data: bytes) -> list[Section]:
    ext = file_ext(filename)
    try:
        sections = _EXTRACTORS[ext](data)
    except ExtractionError:
        raise
    except Exception as e:  # parser libraries raise many types on malformed input
        raise ExtractionError(f"Could not read {ext} file: {type(e).__name__}") from e
    sections = [Section(_clean(s.text), s.page, s.section) for s in sections]
    sections = [s for s in sections if s.text]
    if not sections:
        raise ExtractionError("No extractable text found (scanned PDFs need OCR, which is not supported yet)")
    return sections


def _pdf(data: bytes) -> list[Section]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ExtractionError("Encrypted PDFs are not supported")
    return [Section(p.extract_text() or "", page=i + 1) for i, p in enumerate(reader.pages)]


def _docx(data: bytes) -> list[Section]:
    import docx

    d = docx.Document(io.BytesIO(data))
    out, heading, buf = [], None, []
    for p in d.paragraphs:
        if p.style is not None and p.style.name.lower().startswith("heading") and p.text.strip():
            if buf:
                out.append(Section("\n".join(buf), section=heading))
            heading, buf = p.text.strip()[:300], []
        else:
            buf.append(p.text)
    if buf:
        out.append(Section("\n".join(buf), section=heading))
    for i, t in enumerate(d.tables):
        rows = [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
        out.append(Section("\n".join(rows), section=f"Table {i + 1}"))
    return out


def _markdown(data: bytes) -> list[Section]:
    out, heading, buf = [], None, []
    for line in data.decode("utf-8").splitlines():
        if m := re.match(r"^#{1,6}\s+(.*)", line):
            if buf:
                out.append(Section("\n".join(buf), section=heading))
            heading, buf = m.group(1).strip()[:300], [line]
        else:
            buf.append(line)
    if buf:
        out.append(Section("\n".join(buf), section=heading))
    return out


def _txt(data: bytes) -> list[Section]:
    return [Section(data.decode("utf-8"))]


def _csv(data: bytes) -> list[Section]:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    if not rows:
        return []
    header = rows[0]
    # one line per row with header labels so each chunk stays self-describing
    lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, r, strict=False) if v) for r in rows[1:]]
    return [Section("\n".join(lines), section="CSV")]


def _xlsx(data: bytes) -> list[Section]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [[("" if c is None else str(c)) for c in r] for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        header = rows[0]
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, r, strict=False) if v) for r in rows[1:]]
        out.append(Section("\n".join(lines), section=f"Sheet: {ws.title}"))
    return out


_EXTRACTORS = {".pdf": _pdf, ".docx": _docx, ".md": _markdown, ".txt": _txt, ".csv": _csv, ".xlsx": _xlsx}
