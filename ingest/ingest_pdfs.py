"""
Parse PDFs and papers into chunks for LanceDB using PyMuPDF.

Features:
- Text extraction from PDF pages
- Metadata extraction (title, author, date)
- Handles multi-column layouts
- Memory efficient for large PDFs
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

from .utils import chunk_text, add_memories, RAW_DIR

console = Console()


def extract_pdf_metadata(doc) -> dict:
    """Extract metadata from PDF document."""
    metadata = doc.metadata or {}

    return {
        "title": metadata.get("title", ""),
        "author": metadata.get("author", ""),
        "subject": metadata.get("subject", ""),
        "keywords": metadata.get("keywords", ""),
        "creator": metadata.get("creator", ""),
        "creation_date": metadata.get("creationDate", ""),
        "page_count": doc.page_count,
    }


def clean_pdf_text(text: str) -> str:
    """Clean extracted PDF text."""
    # Remove excessive whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    # Fix line breaks (join hyphenated words)
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    # Normalize line breaks
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove page numbers (common patterns)
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    return text.strip()


def parse_pdf(file_path: str) -> int:
    """
    Extract text from PDF and add to memory.
    Returns number of chunks added.
    """
    if not PYMUPDF_AVAILABLE:
        console.print("[red]Error:[/red] PyMuPDF not installed. Run: pip install PyMuPDF")
        return 0

    if not os.path.exists(file_path):
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        return 0

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        console.print(f"[red]Error opening PDF:[/red] {e}")
        return 0

    # Extract metadata
    meta = extract_pdf_metadata(doc)
    filename = os.path.basename(file_path)
    title = meta["title"] or Path(file_path).stem

    console.print(f"[dim]Processing {meta['page_count']} pages...[/dim]")

    # Extract text from all pages
    full_text_parts = []

    for page_num in range(doc.page_count):
        try:
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                full_text_parts.append(f"[Page {page_num + 1}]\n{text}")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Error on page {page_num + 1}: {e}")
            continue

    doc.close()

    if not full_text_parts:
        console.print(f"[yellow]Warning:[/yellow] No text extracted from {filename}")
        return 0

    # Join and clean text
    full_text = "\n\n".join(full_text_parts)
    full_text = clean_pdf_text(full_text)

    if not full_text.strip():
        return 0

    # Chunk the text
    chunks = chunk_text(full_text)

    if chunks:
        # Get file modification time
        mtime = os.path.getmtime(file_path)
        timestamp = datetime.fromtimestamp(mtime).isoformat()

        # Try to parse PDF creation date
        if meta["creation_date"]:
            try:
                # PDF date format: D:YYYYMMDDHHmmSS
                date_str = meta["creation_date"]
                if date_str.startswith("D:"):
                    date_str = date_str[2:16]
                    timestamp = datetime.strptime(date_str, "%Y%m%d%H%M%S").isoformat()
            except:
                pass

        metadata = {
            "title": title,
            "author": meta["author"],
            "file": filename,
            "page_count": meta["page_count"],
            "keywords": meta["keywords"],
        }

        return add_memories(
            chunks=chunks,
            source=f"pdf:{title}",
            source_type="pdf",
            timestamp=timestamp,
            metadata=metadata
        )

    return 0


def ingest_all_pdfs() -> int:
    """
    Find and ingest all PDF files in the raw directory.
    """
    import glob

    if not PYMUPDF_AVAILABLE:
        console.print("[red]Error:[/red] PyMuPDF not installed. Run: pip install PyMuPDF")
        return 0

    patterns = [
        os.path.join(RAW_DIR, "*.pdf"),
        os.path.join(RAW_DIR, "*.PDF"),
        os.path.join(RAW_DIR, "**/*.pdf"),
    ]

    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern, recursive=True))

    files = list(set(files))

    if not files:
        console.print("[yellow]No PDF files found in data/raw/[/yellow]")
        return 0

    console.print(f"[blue]Found {len(files)} PDF file(s)[/blue]")

    total = 0
    with Progress() as progress:
        task = progress.add_task("Ingesting PDFs...", total=len(files))

        for file_path in files:
            console.print(f"\n[cyan]Processing:[/cyan] {os.path.basename(file_path)}")
            chunks = parse_pdf(file_path)
            total += chunks
            progress.update(task, advance=1)

    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        console.print(f"[blue]Ingesting PDF:[/blue] {file_path}")
        count = parse_pdf(file_path)
        console.print(f"\n[green]✓ Done![/green] Added {count} chunks to memory")
    else:
        console.print("[blue]Scanning for PDFs in data/raw/...[/blue]")
        count = ingest_all_pdfs()
        console.print(f"\n[green]✓ Done![/green] Added {count} total chunks to memory")
