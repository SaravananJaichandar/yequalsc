"""
Direct import from Mac Notes app using AppleScript/JXA.

This allows importing notes directly without manual export.
Requires Notes app permissions when first run.

Usage:
    python -m ingest.ingest_mac_notes           # Import all notes
    python -m ingest.ingest_mac_notes --folder "Work"  # Import specific folder
"""
import json
import os
import subprocess
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.progress import Progress

from .utils import chunk_text, add_memories, console

console = Console()

# AppleScript to fetch all notes
APPLESCRIPT_GET_NOTES = '''
tell application "Notes"
    set noteList to {}
    repeat with aNote in notes
        set noteData to {|id|:id of aNote, |name|:name of aNote, |body|:body of aNote, |creationDate|:(creation date of aNote) as string, |modificationDate|:(modification date of aNote) as string, |folder|:name of container of aNote}
        set end of noteList to noteData
    end repeat
    return noteList
end tell
'''

# AppleScript to fetch notes from specific folder
APPLESCRIPT_GET_FOLDER_NOTES = '''
tell application "Notes"
    set noteList to {}
    set targetFolder to folder "{folder_name}"
    repeat with aNote in notes of targetFolder
        set noteData to {{|id|:id of aNote, |name|:name of aNote, |body|:body of aNote, |creationDate|:(creation date of aNote) as string, |modificationDate|:(modification date of aNote) as string, |folder|:name of container of aNote}}
        set end of noteList to noteData
    end repeat
    return noteList
end tell
'''

# JXA (JavaScript for Automation) - more reliable for complex data
JXA_GET_NOTES = '''
const Notes = Application('Notes');
Notes.includeStandardAdditions = true;

const allNotes = [];
const notes = Notes.notes();

for (let i = 0; i < notes.length; i++) {
    try {
        const note = notes[i];
        allNotes.push({
            id: note.id(),
            name: note.name(),
            body: note.body(),  // HTML content
            plaintext: note.plaintext ? note.plaintext() : '',
            creationDate: note.creationDate().toISOString(),
            modificationDate: note.modificationDate().toISOString(),
            folder: note.container().name()
        });
    } catch(e) {
        // Skip notes that can't be read
    }
}

JSON.stringify(allNotes);
'''


def run_jxa_script(script: str) -> Optional[str]:
    """Run a JXA script and return output."""
    try:
        result = subprocess.run(
            ['osascript', '-l', 'JavaScript', '-e', script],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout for large note collections
        )
        if result.returncode != 0:
            console.print(f"[red]AppleScript error:[/red] {result.stderr}")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Script timed out. You may have too many notes.")
        return None
    except Exception as e:
        console.print(f"[red]Error running script:[/red] {e}")
        return None


def run_applescript(script: str) -> Optional[str]:
    """Run an AppleScript and return output."""
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            console.print(f"[red]AppleScript error:[/red] {result.stderr}")
            return None
        return result.stdout.strip()
    except Exception as e:
        console.print(f"[red]Error running AppleScript:[/red] {e}")
        return None


def strip_html(html: str) -> str:
    """Remove HTML tags from note content."""
    import re
    # Remove style and script tags with content
    text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fetch_mac_notes(folder: Optional[str] = None, log_structure: bool = False) -> list[dict]:
    """
    Fetch notes directly from Mac Notes app.
    Returns list of note dicts with id, name, body, dates, folder.
    """
    console.print("[blue]Connecting to Mac Notes app...[/blue]")
    console.print("[dim]You may be prompted to grant access permissions.[/dim]")

    # Try JXA first (more reliable JSON output)
    output = run_jxa_script(JXA_GET_NOTES)

    if not output:
        console.print("[yellow]JXA failed, trying AppleScript...[/yellow]")
        # Fallback to AppleScript (less reliable for complex data)
        return []

    try:
        notes = json.loads(output)

        # Log structure if requested
        if log_structure and notes:
            console.print("\n[bold cyan]Mac Notes Structure (first note):[/bold cyan]")
            sample = notes[0]
            for key, value in sample.items():
                if key == 'body':
                    console.print(f"  {key}: [HTML content, {len(value)} chars]")
                else:
                    display_val = str(value)[:100] + "..." if len(str(value)) > 100 else value
                    console.print(f"  {key}: {display_val}")

        # Filter by folder if specified
        if folder:
            notes = [n for n in notes if n.get('folder', '').lower() == folder.lower()]
            console.print(f"[dim]Filtered to folder '{folder}': {len(notes)} notes[/dim]")

        return notes

    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing notes:[/red] {e}")
        console.print(f"[dim]Raw output: {output[:500]}...[/dim]")
        return []


def import_mac_notes(folder: Optional[str] = None, log_structure: bool = False) -> int:
    """
    Import notes from Mac Notes app into LanceDB.
    Returns number of chunks added.
    """
    notes = fetch_mac_notes(folder=folder, log_structure=log_structure)

    if not notes:
        console.print("[yellow]No notes found or unable to access Notes app.[/yellow]")
        return 0

    console.print(f"[green]Found {len(notes)} notes[/green]")

    total_chunks = 0

    with Progress() as progress:
        task = progress.add_task("Importing notes...", total=len(notes))

        for note in notes:
            note_id = note.get('id', '')
            name = note.get('name', 'Untitled')
            body = note.get('body', '')
            folder_name = note.get('folder', 'Notes')
            creation_date = note.get('creationDate', datetime.now().isoformat())

            # Strip HTML from body
            text = strip_html(body)

            if not text.strip():
                progress.update(task, advance=1)
                continue

            # Chunk the note
            chunks = chunk_text(text)

            if chunks:
                metadata = {
                    "note_id": note_id,
                    "title": name,
                    "folder": folder_name,
                    "source_app": "mac_notes",
                }

                added = add_memories(
                    chunks=chunks,
                    source=f"mac_notes:{name}",
                    source_type="mac_notes",
                    timestamp=creation_date,
                    metadata=metadata
                )
                total_chunks += added

            progress.update(task, advance=1)

    return total_chunks


def list_note_folders() -> list[str]:
    """List all folders in Mac Notes."""
    script = '''
    const Notes = Application('Notes');
    const folders = Notes.folders();
    const names = folders.map(f => f.name());
    JSON.stringify(names);
    '''
    output = run_jxa_script(script)
    if output:
        try:
            return json.loads(output)
        except:
            return []
    return []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import notes from Mac Notes app")
    parser.add_argument("--folder", type=str, help="Import only from specific folder")
    parser.add_argument("--list-folders", action="store_true", help="List available folders")
    parser.add_argument("--log-structure", action="store_true", help="Log note structure for debugging")

    args = parser.parse_args()

    if args.list_folders:
        console.print("[blue]Available folders in Mac Notes:[/blue]")
        folders = list_note_folders()
        for f in folders:
            console.print(f"  • {f}")
    else:
        console.print("[blue]Importing from Mac Notes...[/blue]")
        count = import_mac_notes(folder=args.folder, log_structure=args.log_structure)
        console.print(f"\n[green]✓ Done![/green] Added {count} chunks to memory")
