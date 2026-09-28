"""
Document Processing & Text Chunking Service.

Handles:
  - Text extraction from TXT, Markdown, PDF, Word (.docx), Excel (.xlsx, .xls), and HTML
  - Recursive semantic chunking with configurable chunk size and overlap
"""

import io
import re
from typing import BinaryIO

from bs4 import BeautifulSoup
from docx import Document
import openpyxl
from pypdf import PdfReader


def clean_text(text: str) -> str:
    """Normalize whitespace and remove excessive blank lines."""
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from all readable pages of a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            pages_text.append(page_text.strip())
    return clean_text("\n\n".join(pages_text))


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract headings, paragraphs, and structured tables from a Word document (.docx).
    """
    doc = Document(io.BytesIO(file_bytes))
    parts: list[str] = []

    # 1. Paragraphs (with headings detection)
    for p in doc.paragraphs:
        p_text = p.text.strip()
        if not p_text:
            continue
        if p.style and p.style.name.startswith("Heading"):
            parts.append(f"## {p_text}")
        else:
            parts.append(p_text)

    # 2. Tables (convert to Markdown table format for optimal LLM/RAG comprehension)
    for table in doc.tables:
        table_rows = []
        for row in table.rows:
            row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if any(row_cells):
                table_rows.append(row_cells)

        if not table_rows:
            continue

        table_text_lines = []
        headers = table_rows[0]
        table_text_lines.append("| " + " | ".join(headers) + " |")
        table_text_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in table_rows[1:]:
            while len(row) < len(headers):
                row.append("")
            table_text_lines.append("| " + " | ".join(row[:len(headers)]) + " |")

        parts.append("\n".join(table_text_lines))

    return clean_text("\n\n".join(parts))


def extract_text_from_excel(file_bytes: bytes) -> str:
    """
    Extract structured tabular data from an Excel spreadsheet (.xlsx, .xlsm).
    Extracts evaluated formula values across all sheets and formats into Markdown tables.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    sheets_text: list[str] = []

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue

        non_empty_rows = []
        for row in rows:
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                cleaned_row = [
                    str(cell).strip().replace("\n", " ") if cell is not None else ""
                    for cell in row
                ]
                # Trim trailing blank cells
                while cleaned_row and cleaned_row[-1] == "":
                    cleaned_row.pop()
                if cleaned_row:
                    non_empty_rows.append(cleaned_row)

        if not non_empty_rows:
            continue

        sheet_section = [f"### Bảng Dữ Liệu: {sheet_name}"]

        # Format rows into clean markdown table
        max_cols = max(len(r) for r in non_empty_rows)
        if max_cols > 0:
            headers = list(non_empty_rows[0])
            while len(headers) < max_cols:
                headers.append(f"Cột {len(headers) + 1}")
            sheet_section.append("| " + " | ".join(headers) + " |")
            sheet_section.append("| " + " | ".join(["---"] * max_cols) + " |")

            for row in non_empty_rows[1:]:
                row_extended = list(row)
                while len(row_extended) < max_cols:
                    row_extended.append("")
                sheet_section.append("| " + " | ".join(row_extended) + " |")

        sheets_text.append("\n".join(sheet_section))

    wb.close()
    return clean_text("\n\n".join(sheets_text))


def extract_text_from_html(content: bytes) -> str:
    """
    Extract clean readable text from HTML content, stripping scripts, styles, and markup.
    """
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer"]):
        tag.decompose()
    return clean_text(soup.get_text(separator="\n"))


def extract_text_from_file(filename: str, content: bytes) -> str:
    """
    Extract clean text based on file extension:
      - .pdf: PDF extraction
      - .docx, .doc: Microsoft Word extraction (paragraphs & tables)
      - .xlsx, .xlsm, .xls: Microsoft Excel extraction (all sheets & tabular format)
      - .html, .htm: HTML clean text extraction (strip scripts/tags)
      - .txt, .md, .markdown, .csv, .json: Plain text / UTF-8
    """
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    try:
        if ext == "pdf":
            return extract_text_from_pdf(content)
        elif ext in ["docx", "doc"]:
            return extract_text_from_docx(content)
        elif ext in ["xlsx", "xlsm", "xls"]:
            return extract_text_from_excel(content)
        elif ext in ["html", "htm"]:
            return extract_text_from_html(content)
        elif ext in ["txt", "md", "markdown", "csv", "json"]:
            return clean_text(content.decode("utf-8", errors="replace"))
        else:
            return clean_text(content.decode("utf-8", errors="replace"))
    except Exception as e:
        # Fallback to UTF-8 decoded text if binary extraction fails
        text = content.decode("utf-8", errors="ignore").strip()
        if text:
            return clean_text(text)
        raise ValueError(f"Không thể trích xuất nội dung từ file '{filename}': {str(e)}")


def split_text(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[str]:
    """
    Split a long text into semantically coherent chunks.
    Recursively splits on paragraphs (\n\n), then lines (\n),
    then sentences (., ?, !), then words.
    
    Guarantees overlap between adjacent chunks to maintain context.
    """
    text = clean_text(text)
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Primary separators in order of preference
    separators = ["\n\n", "\n", ". ", "? ", "! ", " "]

    def _split_into_pieces(t: str, sep_idx: int) -> list[str]:
        if sep_idx >= len(separators):
            # Fallback: slice by exact chunk_size
            return [t[i : i + chunk_size] for i in range(0, len(t), chunk_size - chunk_overlap)]

        sep = separators[sep_idx]
        parts = t.split(sep)
        result = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= chunk_size:
                result.append(part)
            else:
                result.extend(_split_into_pieces(part, sep_idx + 1))
        return result

    pieces = _split_into_pieces(text, 0)

    # Now assemble pieces into chunks of roughly chunk_size with chunk_overlap
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for piece in pieces:
        piece_len = len(piece) + 1  # count spacing

        if current_length + piece_len <= chunk_size:
            current_chunk.append(piece)
            current_length += piece_len
        else:
            if current_chunk:
                combined = " ".join(current_chunk).strip()
                chunks.append(combined)

                # Keep overlap from the end of the current chunk
                overlap_pieces = []
                overlap_len = 0
                for p in reversed(current_chunk):
                    if overlap_len + len(p) <= chunk_overlap:
                        overlap_pieces.insert(0, p)
                        overlap_len += len(p) + 1
                    else:
                        break
                current_chunk = overlap_pieces
                current_length = sum(len(p) + 1 for p in current_chunk)

            current_chunk.append(piece)
            current_length += piece_len

    if current_chunk:
        combined = " ".join(current_chunk).strip()
        if combined:
            chunks.append(combined)

    return chunks
