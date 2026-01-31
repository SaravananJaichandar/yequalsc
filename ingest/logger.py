"""
Logging utilities for y=c ingestion pipeline.
Logs conversation structures and data for debugging.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from rich.console import Console

console = Console()

# Log directory
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_log_file(source_type: str) -> Path:
    """Get log file path for a source type."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOG_DIR / f"{source_type}_{timestamp}.log"


def log_structure(source_type: str, data: dict | list, sample_size: int = 2):
    """
    Log the structure of imported data for debugging.
    Saves to logs/ directory with timestamp.
    """
    log_file = get_log_file(source_type)

    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {source_type.upper()} STRUCTURE LOG ===\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"{'=' * 50}\n\n")

        if isinstance(data, list):
            f.write(f"Type: List with {len(data)} items\n\n")

            # Log structure of first few items
            for i, item in enumerate(data[:sample_size]):
                f.write(f"--- Item {i + 1} ---\n")
                log_item_structure(f, item, indent=0)
                f.write("\n")

            # Log full sample as JSON
            f.write(f"\n{'=' * 50}\n")
            f.write("FULL SAMPLE (first item as JSON):\n")
            f.write(f"{'=' * 50}\n")
            if data:
                f.write(json.dumps(data[0], indent=2, default=str, ensure_ascii=False))

        elif isinstance(data, dict):
            f.write("Type: Dictionary\n\n")
            log_item_structure(f, data, indent=0)

            f.write(f"\n{'=' * 50}\n")
            f.write("FULL STRUCTURE (as JSON):\n")
            f.write(f"{'=' * 50}\n")
            # Truncate large values for readability
            truncated = truncate_values(data)
            f.write(json.dumps(truncated, indent=2, default=str, ensure_ascii=False))

    console.print(f"[dim]Structure logged to: {log_file}[/dim]")
    return log_file


def log_item_structure(f, item, indent: int = 0):
    """Recursively log the structure of an item."""
    prefix = "  " * indent

    if isinstance(item, dict):
        for key, value in item.items():
            value_type = type(value).__name__
            if isinstance(value, str):
                preview = value[:100].replace('\n', '\\n') + "..." if len(value) > 100 else value.replace('\n', '\\n')
                f.write(f"{prefix}{key}: ({value_type}, len={len(value)}) \"{preview}\"\n")
            elif isinstance(value, (list, dict)):
                if isinstance(value, list):
                    f.write(f"{prefix}{key}: ({value_type}, len={len(value)})\n")
                    if value and len(value) > 0:
                        f.write(f"{prefix}  [0]: \n")
                        log_item_structure(f, value[0], indent + 2)
                else:
                    f.write(f"{prefix}{key}: ({value_type})\n")
                    log_item_structure(f, value, indent + 1)
            else:
                f.write(f"{prefix}{key}: ({value_type}) {value}\n")
    elif isinstance(item, list):
        f.write(f"{prefix}List with {len(item)} items\n")
        if item:
            f.write(f"{prefix}[0]: \n")
            log_item_structure(f, item[0], indent + 1)
    else:
        f.write(f"{prefix}{type(item).__name__}: {item}\n")


def truncate_values(data, max_length: int = 200) -> dict | list:
    """Truncate long string values for logging."""
    if isinstance(data, dict):
        return {
            k: truncate_values(v, max_length) if isinstance(v, (dict, list))
            else (v[:max_length] + "..." if isinstance(v, str) and len(v) > max_length else v)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [truncate_values(item, max_length) for item in data[:5]]  # Only first 5 items
    return data


def log_conversation_sample(source_type: str, conversations: list, messages_key: str = "messages"):
    """
    Log a sample conversation structure.
    Useful for understanding Claude/ChatGPT export formats.
    """
    log_file = get_log_file(f"{source_type}_conversations")

    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {source_type.upper()} CONVERSATION STRUCTURE ===\n")
        f.write(f"Total conversations: {len(conversations)}\n")
        f.write(f"{'=' * 50}\n\n")

        if not conversations:
            f.write("No conversations found.\n")
            return log_file

        # Analyze first conversation
        conv = conversations[0]
        f.write("FIRST CONVERSATION KEYS:\n")
        for key in conv.keys():
            value = conv[key]
            if isinstance(value, str):
                f.write(f"  {key}: str (len={len(value)})\n")
            elif isinstance(value, list):
                f.write(f"  {key}: list (len={len(value)})\n")
            elif isinstance(value, dict):
                f.write(f"  {key}: dict (keys={list(value.keys())[:5]})\n")
            else:
                f.write(f"  {key}: {type(value).__name__} = {value}\n")

        # Log messages structure if available
        messages = conv.get(messages_key, conv.get("chat_messages", []))
        if messages:
            f.write(f"\nMESSAGES STRUCTURE:\n")
            # Handle both list (Claude) and dict (ChatGPT mapping) formats
            if isinstance(messages, list) and messages:
                msg = messages[0]
                f.write(f"  Format: list (first message):\n")
                for key, value in msg.items():
                    if isinstance(value, str):
                        preview = value[:100].replace('\n', '\\n')
                        f.write(f"    {key}: \"{preview}...\"\n" if len(value) > 100 else f"    {key}: \"{preview}\"\n")
                    else:
                        f.write(f"    {key}: {type(value).__name__} = {value}\n")
            elif isinstance(messages, dict):
                f.write(f"  Format: dict with {len(messages)} keys (ChatGPT mapping)\n")
                # Get first message node
                first_key = next(iter(messages.keys()), None)
                if first_key:
                    f.write(f"  First key: {first_key}\n")
                    node = messages[first_key]
                    if isinstance(node, dict):
                        f.write(f"  Node keys: {list(node.keys())}\n")

        # Full JSON of first conversation
        f.write(f"\n{'=' * 50}\n")
        f.write("FULL FIRST CONVERSATION (JSON):\n")
        f.write(f"{'=' * 50}\n")
        truncated_conv = truncate_values(conv, max_length=500)
        f.write(json.dumps(truncated_conv, indent=2, default=str, ensure_ascii=False))

    console.print(f"[dim]Conversation structure logged to: {log_file}[/dim]")
    return log_file


def log_raw_file(source_type: str, file_path: str, data: dict | list):
    """Log the raw structure of an imported file."""
    log_file = get_log_file(f"{source_type}_raw")

    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== RAW FILE STRUCTURE: {file_path} ===\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"{'=' * 50}\n\n")

        if isinstance(data, list):
            f.write(f"Root type: List with {len(data)} items\n\n")
        elif isinstance(data, dict):
            f.write(f"Root type: Dict with keys: {list(data.keys())}\n\n")

        # Write full structure
        f.write("FULL STRUCTURE:\n")
        f.write(json.dumps(data, indent=2, default=str, ensure_ascii=False)[:50000])  # Limit to 50KB

    console.print(f"[dim]Raw file logged to: {log_file}[/dim]")
    return log_file
