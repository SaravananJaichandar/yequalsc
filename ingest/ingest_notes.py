"""
Parse notes from various formats into chunks for LanceDB.

Supported formats:
- Markdown files (.md)
- Obsidian vaults (folders with .md files)
- Apple Notes export (HTML or text)
- Plain text files (.txt)
"""
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress

from .utils import chunk_text, add_memories, RAW_DIR

console = Console()


def clean_markdown(text: str) -> str:
    """Remove markdown formatting for cleaner text."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Remove images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Convert links to just text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_title_from_markdown(content: str, filename: str) -> str:
    """Extract title from markdown content or use filename."""
    # Try to find H1 heading
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Try YAML frontmatter title
    frontmatter_match = re.search(r'^---\s*\n.*?title:\s*["\']?([^"\'\n]+)["\']?.*?\n---', content, re.DOTALL)
    if frontmatter_match:
        return frontmatter_match.group(1).strip()

    # Use filename without extension
    return Path(filename).stem


def parse_markdown_file(file_path: str) -> int:
    """Parse a single markdown file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            console.print(f"[red]Error reading {file_path}:[/red] {e}")
            return 0

    if not content.strip():
        return 0

    title = extract_title_from_markdown(content, file_path)
    cleaned = clean_markdown(content)

    if not cleaned.strip():
        return 0

    chunks = chunk_text(cleaned)

    if chunks:
        # Get file modification time as timestamp
        mtime = os.path.getmtime(file_path)
        timestamp = datetime.fromtimestamp(mtime).isoformat()

        metadata = {
            "title": title,
            "file": os.path.basename(file_path),
            "path": file_path,
        }

        return add_memories(
            chunks=chunks,
            source=f"note:{title}",
            source_type="notes",
            timestamp=timestamp,
            metadata=metadata
        )

    return 0


def parse_obsidian_vault(vault_path: str) -> int:
    """Parse an Obsidian vault (folder of markdown files)."""
    if not os.path.isdir(vault_path):
        console.print(f"[red]Error:[/red] Not a directory: {vault_path}")
        return 0

    total_chunks = 0
    md_files = list(Path(vault_path).rglob("*.md"))

    if not md_files:
        console.print(f"[yellow]Warning:[/yellow] No markdown files found in {vault_path}")
        return 0

    console.print(f"[blue]Found {len(md_files)} markdown files in vault[/blue]")

    with Progress() as progress:
        task = progress.add_task("Processing vault...", total=len(md_files))

        for md_file in md_files:
            # Skip hidden files and folders
            if any(part.startswith('.') for part in md_file.parts):
                progress.update(task, advance=1)
                continue

            chunks = parse_markdown_file(str(md_file))
            total_chunks += chunks
            progress.update(task, advance=1)

    return total_chunks


def parse_text_file(file_path: str) -> int:
    """Parse a plain text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            console.print(f"[red]Error reading {file_path}:[/red] {e}")
            return 0

    if not content.strip():
        return 0

    title = Path(file_path).stem
    chunks = chunk_text(content)

    if chunks:
        mtime = os.path.getmtime(file_path)
        timestamp = datetime.fromtimestamp(mtime).isoformat()

        metadata = {
            "title": title,
            "file": os.path.basename(file_path),
        }

        return add_memories(
            chunks=chunks,
            source=f"note:{title}",
            source_type="notes",
            timestamp=timestamp,
            metadata=metadata
        )

    return 0


def parse_apple_notes_zip(zip_path: str) -> int:
    """Parse Apple Notes export ZIP."""
    total_chunks = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                # Process HTML or text files
                if name.endswith(('.html', '.htm', '.txt', '.md')):
                    try:
                        with zf.open(name) as f:
                            content = f.read().decode('utf-8')

                        # Strip HTML if needed
                        if name.endswith(('.html', '.htm')):
                            content = re.sub(r'<[^>]+>', ' ', content)
                            content = re.sub(r'\s+', ' ', content)

                        if content.strip():
                            title = Path(name).stem
                            chunks = chunk_text(content.strip())

                            if chunks:
                                metadata = {
                                    "title": title,
                                    "file": name,
                                    "archive": os.path.basename(zip_path),
                                }

                                added = add_memories(
                                    chunks=chunks,
                                    source=f"note:{title}",
                                    source_type="notes",
                                    timestamp=datetime.now().isoformat(),
                                    metadata=metadata
                                )
                                total_chunks += added

                    except Exception as e:
                        console.print(f"[yellow]Warning:[/yellow] Error processing {name}: {e}")
                        continue

    except zipfile.BadZipFile:
        console.print(f"[red]Error:[/red] Invalid ZIP file: {zip_path}")
        return 0

    return total_chunks


def parse_notes(path: str) -> int:
    """
    Parse notes from various formats.
    Automatically detects format based on path.
    """
    if not os.path.exists(path):
        console.print(f"[red]Error:[/red] Path not found: {path}")
        return 0

    # Directory = Obsidian vault or folder of notes
    if os.path.isdir(path):
        return parse_obsidian_vault(path)

    # ZIP file = Apple Notes export
    if path.endswith('.zip'):
        return parse_apple_notes_zip(path)

    # Markdown file
    if path.endswith('.md'):
        return parse_markdown_file(path)

    # Text file
    if path.endswith('.txt'):
        return parse_text_file(path)

    console.print(f"[yellow]Warning:[/yellow] Unsupported format: {path}")
    return 0


def ingest_all_notes() -> int:
    """
    Find and ingest all notes in the raw directory.
    """
    import glob

    total = 0

    # Find markdown files
    md_patterns = [
        os.path.join(RAW_DIR, "*.md"),
        os.path.join(RAW_DIR, "**/*.md"),
    ]
    md_files = []
    for pattern in md_patterns:
        md_files.extend(glob.glob(pattern, recursive=True))
    md_files = list(set(md_files))

    if md_files:
        console.print(f"[blue]Found {len(md_files)} markdown files[/blue]")
        for f in md_files:
            total += parse_markdown_file(f)

    # Find text files
    txt_files = glob.glob(os.path.join(RAW_DIR, "*.txt"))
    if txt_files:
        console.print(f"[blue]Found {len(txt_files)} text files[/blue]")
        for f in txt_files:
            total += parse_text_file(f)

    # Find Obsidian vaults (directories with .obsidian folder)
    for item in os.listdir(RAW_DIR):
        item_path = os.path.join(RAW_DIR, item)
        if os.path.isdir(item_path):
            obsidian_marker = os.path.join(item_path, ".obsidian")
            if os.path.exists(obsidian_marker):
                console.print(f"[blue]Found Obsidian vault:[/blue] {item}")
                total += parse_obsidian_vault(item_path)

    # Find Apple Notes ZIP exports
    notes_zips = glob.glob(os.path.join(RAW_DIR, "*notes*.zip"))
    for zip_file in notes_zips:
        console.print(f"[blue]Found notes archive:[/blue] {os.path.basename(zip_file)}")
        total += parse_apple_notes_zip(zip_file)

    if total == 0:
        console.print("[yellow]No notes found in data/raw/[/yellow]")
        console.print("[dim]Supported: .md, .txt, Obsidian vaults, *notes*.zip[/dim]")

    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
        console.print(f"[blue]Ingesting notes:[/blue] {path}")
        count = parse_notes(path)
        console.print(f"\n[green]✓ Done![/green] Added {count} chunks to memory")
    else:
        console.print("[blue]Scanning for notes in data/raw/...[/blue]")
        count = ingest_all_notes()
        console.print(f"\n[green]✓ Done![/green] Added {count} total chunks to memory")
