"""
Parse Claude conversation exports into chunks for LanceDB.

Claude exports come as JSON with structure:
{
  "conversations": [
    {
      "uuid": "...",
      "name": "Conversation Title",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z",
      "chat_messages": [
        {
          "uuid": "...",
          "text": "message content",
          "sender": "human" | "assistant",
          "created_at": "..."
        }
      ]
    }
  ]
}
"""
import json
import os
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.progress import Progress, TaskID

from .utils import chunk_text, add_memories, RAW_DIR
from .logger import log_structure, log_conversation_sample, log_raw_file

console = Console()

# Enable logging for debugging
LOG_ENABLED = True


def parse_claude_export(file_path: str, progress: Optional[Progress] = None, task: Optional[TaskID] = None, log: bool = True) -> int:
    """
    Parse Claude conversation export JSON.
    Returns number of chunks added to database.
    """
    if not os.path.exists(file_path):
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        return 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON: {e}")
        return 0

    # Log raw structure for debugging
    if log and LOG_ENABLED:
        console.print("[cyan]Logging Claude export structure...[/cyan]")
        log_raw_file("claude", file_path, data)

    # Handle different Claude export formats:
    # 1. New format: list of conversations directly
    # 2. Old format: {"conversations": [...]}
    # 3. Single conversation: {"chat_messages": [...]}
    if isinstance(data, list):
        # New format - list of conversations
        conversations = data
    elif isinstance(data, dict):
        conversations = data.get("conversations", [])
        if not conversations:
            # Maybe it's a single conversation format
            if "chat_messages" in data:
                conversations = [data]
    else:
        console.print("[yellow]Warning:[/yellow] Unexpected data format in export")
        return 0

    if not conversations:
        console.print("[yellow]Warning:[/yellow] No conversations found in export")
        return 0

    # Log conversation structure
    if log and LOG_ENABLED and conversations:
        log_conversation_sample("claude", conversations, messages_key="chat_messages")

    total_chunks = 0
    filename = os.path.basename(file_path)

    for i, conv in enumerate(conversations):
        if progress and task:
            progress.update(task, advance=1, description=f"Processing conversation {i+1}/{len(conversations)}")

        conv_name = conv.get("name", f"Conversation {i+1}")
        conv_date = conv.get("created_at", datetime.now().isoformat())
        messages = conv.get("chat_messages", [])

        if not messages:
            continue

        # Build conversation text with speaker labels
        conv_text_parts = []
        for msg in messages:
            sender = msg.get("sender", "unknown")
            text = msg.get("text", "").strip()
            if text:
                # Format: [Human]: message or [Claude]: message
                label = "Human" if sender == "human" else "Claude"
                conv_text_parts.append(f"[{label}]: {text}")

        if not conv_text_parts:
            continue

        # Join all messages into one conversation text
        full_text = "\n\n".join(conv_text_parts)

        # Chunk the conversation
        chunks = chunk_text(full_text)

        if chunks:
            # Add metadata about the conversation
            metadata = {
                "conversation_name": conv_name,
                "message_count": len(messages),
                "file": filename,
            }

            added = add_memories(
                chunks=chunks,
                source=f"claude:{conv_name}",
                source_type="claude",
                timestamp=conv_date,
                metadata=metadata
            )
            total_chunks += added

    return total_chunks


def ingest_all_claude_exports() -> int:
    """
    Find and ingest all Claude export files in the raw directory.
    Looks for files matching claude*.json pattern.
    """
    import glob

    patterns = [
        os.path.join(RAW_DIR, "claude*.json"),
        os.path.join(RAW_DIR, "Claude*.json"),
        os.path.join(RAW_DIR, "**/claude*.json"),
    ]

    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern, recursive=True))

    files = list(set(files))  # Remove duplicates

    if not files:
        console.print("[yellow]No Claude export files found in data/raw/[/yellow]")
        console.print("[dim]Expected files matching: claude*.json[/dim]")
        return 0

    console.print(f"[blue]Found {len(files)} Claude export file(s)[/blue]")

    total = 0
    with Progress() as progress:
        main_task = progress.add_task("Ingesting Claude exports...", total=len(files))

        for file_path in files:
            console.print(f"\n[cyan]Processing:[/cyan] {os.path.basename(file_path)}")
            chunks = parse_claude_export(file_path)
            total += chunks
            progress.update(main_task, advance=1)

    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Process specific file
        file_path = sys.argv[1]
        console.print(f"[blue]Ingesting Claude export:[/blue] {file_path}")
        count = parse_claude_export(file_path)
        console.print(f"\n[green]✓ Done![/green] Added {count} chunks to memory")
    else:
        # Process all Claude exports in raw directory
        console.print("[blue]Scanning for Claude exports in data/raw/...[/blue]")
        count = ingest_all_claude_exports()
        console.print(f"\n[green]✓ Done![/green] Added {count} total chunks to memory")
