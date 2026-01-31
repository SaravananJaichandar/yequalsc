"""
Ingestion worker — runs in its own process to avoid PyTorch/OpenMP threading deadlocks.
Writes progress to a JSON status file that the server reads.
"""
import os
import sys
import json
import argparse
import glob

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ingest.ingest_claude import parse_claude_export
from ingest.ingest_chatgpt import parse_chatgpt_export
from ingest.ingest_mac_notes import import_mac_notes
from ingest.utils import set_progress_callback, RAW_DIR


def write_status(status_file, data):
    tmp = status_file + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, status_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--file', default=None)
    parser.add_argument('--status-file', required=True)
    args = parser.parse_args()

    status = {
        "active": True,
        "current_file": os.path.basename(args.file) if args.file else args.source,
        "progress": 10,
        "total_files": 1,
        "completed_files": 0,
        "chunks_added": 0,
        "error": None,
    }
    write_status(args.status_file, status)

    def on_chunks_added(count):
        status["chunks_added"] += count
        c = status["chunks_added"]
        status["progress"] = min(90, 10 + int(c * 0.5))
        write_status(args.status_file, status)

    set_progress_callback(on_chunks_added)

    try:
        chunks = 0

        if args.source == 'claude':
            if args.file:
                chunks = parse_claude_export(args.file, log=False)
            else:
                files = list(set(
                    glob.glob(os.path.join(RAW_DIR, "claude*.json")) +
                    glob.glob(os.path.join(RAW_DIR, "Claude*.json"))
                ))
                status["total_files"] = len(files)
                for i, fp in enumerate(files):
                    status["current_file"] = os.path.basename(fp)
                    write_status(args.status_file, status)
                    chunks += parse_claude_export(fp, log=False)
                    status["completed_files"] = i + 1

        elif args.source == 'chatgpt':
            if args.file:
                chunks = parse_chatgpt_export(args.file, log=False)
            else:
                patterns = [
                    os.path.join(RAW_DIR, "*.zip"),
                    os.path.join(RAW_DIR, "chatgpt*.json"),
                    os.path.join(RAW_DIR, "conversations.json"),
                ]
                files = list(set(f for p in patterns for f in glob.glob(p)))
                status["total_files"] = len(files)
                for i, fp in enumerate(files):
                    status["current_file"] = os.path.basename(fp)
                    write_status(args.status_file, status)
                    chunks += parse_chatgpt_export(fp, log=False)
                    status["completed_files"] = i + 1

        elif args.source == 'notes':
            status["current_file"] = "Mac Notes"
            write_status(args.status_file, status)
            chunks = import_mac_notes(log_structure=False)

        status["chunks_added"] = chunks
        status["progress"] = 100
        status["completed_files"] = status["total_files"]
        status["active"] = False
        write_status(args.status_file, status)

    except Exception as e:
        import traceback
        traceback.print_exc()
        status["error"] = str(e)
        status["active"] = False
        write_status(args.status_file, status)

    finally:
        set_progress_callback(None)


if __name__ == '__main__':
    main()
