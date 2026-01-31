"""
Parse ChatGPT/OpenAI conversation exports into chunks for LanceDB.

ChatGPT exports come as a ZIP containing conversations.json with structure:
[
  {
    "title": "Conversation Title",
    "create_time": 1234567890.123,
    "update_time": 1234567890.123,
    "mapping": {
      "message-id": {
        "id": "...",
        "message": {
          "author": {"role": "user" | "assistant" | "system"},
          "content": {"parts": ["message text"]},
          "create_time": 1234567890.123
        },
        "parent": "parent-message-id",
        "children": ["child-message-id"]
      }
    }
  }
]
"""
import json
import os
import zipfile
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.progress import Progress

from .utils import chunk_text, add_memories, RAW_DIR
from .logger import log_structure, log_conversation_sample, log_raw_file

console = Console()

# Enable logging for debugging
LOG_ENABLED = True


def extract_messages_from_mapping(mapping: dict) -> list[dict]:
    """
    Extract messages from ChatGPT's nested mapping structure.
    Returns messages in chronological order.
    """
    messages = []

    for msg_id, node in mapping.items():
        msg_data = node.get("message")
        if not msg_data:
            continue

        author = msg_data.get("author", {}).get("role", "unknown")
        content = msg_data.get("content", {})

        # Content can be in different formats
        text = ""
        if isinstance(content, dict):
            parts = content.get("parts", [])
            if parts:
                text = "\n".join(str(p) for p in parts if isinstance(p, str))
        elif isinstance(content, str):
            text = content

        if text.strip() and author in ("user", "assistant"):
            create_time = msg_data.get("create_time", 0)
            messages.append({
                "role": author,
                "text": text.strip(),
                "timestamp": create_time,
            })

    # Sort by timestamp
    messages.sort(key=lambda m: m.get("timestamp", 0))
    return messages


def parse_chatgpt_export(file_path: str, log: bool = True) -> int:
    """
    Parse ChatGPT conversation export (JSON or ZIP).
    Returns number of chunks added to database.
    """
    if not os.path.exists(file_path):
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        return 0

    # Handle ZIP files (standard ChatGPT export format)
    if file_path.endswith('.zip'):
        return parse_chatgpt_zip(file_path, log=log)

    # Handle direct JSON files
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON: {e}")
        return 0

    # Log raw structure for debugging
    if log and LOG_ENABLED:
        console.print("[cyan]Logging ChatGPT export structure...[/cyan]")
        log_raw_file("chatgpt", file_path, data)

    return process_chatgpt_conversations(data, os.path.basename(file_path), log=log)


def parse_chatgpt_zip(zip_path: str, log: bool = True) -> int:
    """Extract and parse ChatGPT ZIP export."""
    total_chunks = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Look for conversations.json
            for name in zf.namelist():
                if name.endswith('conversations.json'):
                    with zf.open(name) as f:
                        data = json.load(f)
                        # Log structure
                        if log and LOG_ENABLED:
                            console.print("[cyan]Logging ChatGPT ZIP structure...[/cyan]")
                            log_raw_file("chatgpt_zip", zip_path, data)
                        total_chunks += process_chatgpt_conversations(
                            data, os.path.basename(zip_path), log=log
                        )
                    break
            else:
                console.print("[yellow]Warning:[/yellow] No conversations.json found in ZIP")
    except zipfile.BadZipFile:
        console.print(f"[red]Error:[/red] Invalid ZIP file: {zip_path}")
        return 0

    return total_chunks


def process_chatgpt_conversations(data: list | dict, source_file: str, log: bool = True) -> int:
    """Process ChatGPT conversation data."""
    # Handle both list and single conversation
    if isinstance(data, dict):
        conversations = [data]
    else:
        conversations = data

    if not conversations:
        console.print("[yellow]Warning:[/yellow] No conversations found")
        return 0

    # Log conversation structure
    if log and LOG_ENABLED:
        log_conversation_sample("chatgpt", conversations, messages_key="mapping")

    total_chunks = 0

    for conv in conversations:
        title = conv.get("title", "Untitled Conversation")
        create_time = conv.get("create_time", 0)
        mapping = conv.get("mapping", {})

        if not mapping:
            continue

        # Extract messages from mapping
        messages = extract_messages_from_mapping(mapping)

        if not messages:
            continue

        # Build conversation text
        conv_text_parts = []
        for msg in messages:
            role = msg["role"]
            text = msg["text"]
            label = "Human" if role == "user" else "ChatGPT"
            conv_text_parts.append(f"[{label}]: {text}")

        if not conv_text_parts:
            continue

        full_text = "\n\n".join(conv_text_parts)
        chunks = chunk_text(full_text)

        if chunks:
            # Convert timestamp
            if create_time:
                timestamp = datetime.fromtimestamp(create_time).isoformat()
            else:
                timestamp = datetime.now().isoformat()

            metadata = {
                "conversation_title": title,
                "message_count": len(messages),
                "file": source_file,
            }

            added = add_memories(
                chunks=chunks,
                source=f"chatgpt:{title}",
                source_type="chatgpt",
                timestamp=timestamp,
                metadata=metadata
            )
            total_chunks += added

    return total_chunks


def ingest_all_chatgpt_exports() -> int:
    """
    Find and ingest all ChatGPT export files in the raw directory.
    Looks for ZIP files and conversations.json.
    """
    import glob

    patterns = [
        os.path.join(RAW_DIR, "*.zip"),
        os.path.join(RAW_DIR, "chatgpt*.json"),
        os.path.join(RAW_DIR, "conversations.json"),
        os.path.join(RAW_DIR, "**/conversations.json"),
    ]

    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern, recursive=True))

    files = list(set(files))

    if not files:
        console.print("[yellow]No ChatGPT export files found in data/raw/[/yellow]")
        console.print("[dim]Expected: ZIP export or conversations.json[/dim]")
        return 0

    console.print(f"[blue]Found {len(files)} potential ChatGPT export file(s)[/blue]")

    total = 0
    with Progress() as progress:
        task = progress.add_task("Ingesting ChatGPT exports...", total=len(files))

        for file_path in files:
            console.print(f"\n[cyan]Processing:[/cyan] {os.path.basename(file_path)}")
            chunks = parse_chatgpt_export(file_path)
            total += chunks
            progress.update(task, advance=1)

    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        console.print(f"[blue]Ingesting ChatGPT export:[/blue] {file_path}")
        count = parse_chatgpt_export(file_path)
        console.print(f"\n[green]✓ Done![/green] Added {count} chunks to memory")
    else:
        console.print("[blue]Scanning for ChatGPT exports in data/raw/...[/blue]")
        count = ingest_all_chatgpt_exports()
        console.print(f"\n[green]✓ Done![/green] Added {count} total chunks to memory")
