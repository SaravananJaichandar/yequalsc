"""
File Watcher for y=c - Auto-detect and ingest LLM conversation exports.

Watches ~/Downloads for:
- conversations.json (Claude exports)
- *.zip containing conversations.json (ChatGPT exports)

When detected:
1. Identifies the source type
2. Moves file to data/raw/
3. Triggers ingestion via API
4. Sends desktop notification
"""
import os
import sys
import time
import json
import shutil
import zipfile
import signal
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
WATCH_DIR = Path.home() / "Downloads"
DATA_RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
API_BASE = "http://localhost:8000"

# Patterns to detect
CLAUDE_PATTERN = "conversations.json"
CHATGPT_PATTERNS = [".zip"]  # Will check if zip contains conversations.json


def send_notification(title: str, message: str):
    """Send macOS desktop notification."""
    try:
        script = f'''
        display notification "{message}" with title "{title}"
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True)
    except Exception as e:
        print(f"Notification error: {e}", file=sys.stderr)


def detect_source_type(file_path: Path) -> str | None:
    """Detect if file is a Claude or ChatGPT export.

    Returns: 'claude', 'chatgpt', or None
    """
    filename = file_path.name.lower()

    # Direct JSON file named conversations.json
    if filename == "conversations.json":
        # Check content to distinguish Claude vs ChatGPT
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Claude format: has 'conversations' key or list with 'chat_messages'
            if isinstance(data, dict) and 'conversations' in data:
                return 'claude'
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if 'chat_messages' in first:
                    return 'claude'
                # ChatGPT format: has 'mapping' key
                if 'mapping' in first:
                    return 'chatgpt'
        except Exception:
            pass
        return None

    # ZIP file - check if it contains conversations.json
    if filename.endswith('.zip'):
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                names = zf.namelist()
                if 'conversations.json' in names:
                    return 'chatgpt'
        except Exception:
            pass

    return None


def trigger_ingestion(source_type: str, file_path: Path) -> dict:
    """Call the y=c API to trigger ingestion."""
    try:
        # First upload the file
        upload_url = f"{API_BASE}/upload/{source_type}"
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f)}
            response = requests.post(upload_url, files=files, timeout=30)

        if response.status_code != 200:
            return {"success": False, "error": f"Upload failed: {response.text}"}

        upload_result = response.json()
        uploaded_path = upload_result.get("file_path")

        # Then trigger ingestion
        ingest_url = f"{API_BASE}/ingest"
        response = requests.post(
            ingest_url,
            json={"source_type": source_type, "file_path": uploaded_path},
            timeout=10
        )

        if response.status_code == 200:
            return {"success": True, "file_path": uploaded_path}
        else:
            return {"success": False, "error": response.text}

    except requests.ConnectionError:
        return {"success": False, "error": "Backend not running. Start with: python backend/yc_server.py"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class ExportHandler(FileSystemEventHandler):
    """Handle file system events for export detection."""

    def __init__(self):
        self.processed_files = set()
        self.debounce_time = {}  # Track last modification time

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def _handle_file(self, file_path: str):
        """Process a potential export file."""
        path = Path(file_path)

        # Skip if already processed
        if str(path) in self.processed_files:
            return

        # Debounce - wait for file to finish writing
        now = time.time()
        last_time = self.debounce_time.get(str(path), 0)
        if now - last_time < 2:  # 2 second debounce
            return
        self.debounce_time[str(path)] = now

        # Wait a moment for file to finish writing
        time.sleep(1)

        # Check if file still exists (might be temp file)
        if not path.exists():
            return

        # Detect source type
        source_type = detect_source_type(path)
        if not source_type:
            return

        print(f"\n[y=c] Detected {source_type} export: {path.name}")
        self.processed_files.add(str(path))

        # Move to data/raw with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{source_type}_{timestamp}_{path.name}"
        dest_path = DATA_RAW_DIR / dest_name

        # Ensure data/raw exists
        DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(path, dest_path)
            print(f"[y=c] Copied to: {dest_path}")
        except Exception as e:
            print(f"[y=c] Error copying file: {e}", file=sys.stderr)
            send_notification("y=c Error", f"Failed to copy {path.name}")
            return

        # Trigger ingestion
        print(f"[y=c] Triggering ingestion...")
        result = trigger_ingestion(source_type, dest_path)

        if result["success"]:
            print(f"[y=c] Ingestion started successfully")
            send_notification(
                "y=c - New Memories",
                f"Ingesting {source_type} export: {path.name}"
            )
        else:
            print(f"[y=c] Ingestion failed: {result['error']}", file=sys.stderr)
            send_notification(
                "y=c Error",
                f"Failed to ingest: {result['error'][:50]}"
            )


def main():
    """Main entry point for the file watcher."""
    print("=" * 50)
    print("y=c File Watcher")
    print("=" * 50)
    print(f"Watching: {WATCH_DIR}")
    print(f"Data dir: {DATA_RAW_DIR}")
    print(f"API: {API_BASE}")
    print()
    print("Detecting:")
    print("  - conversations.json (Claude)")
    print("  - *.zip with conversations.json (ChatGPT)")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 50)

    # Setup handler and observer
    event_handler = ExportHandler()
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_DIR), recursive=False)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n[y=c] Shutting down file watcher...")
        observer.stop()
        observer.join()
        print("[y=c] Stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start watching
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
