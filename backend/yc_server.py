"""
FastAPI server for y=c
Handles file uploads, ingestion, and query endpoints
"""
import os

# Fix PyTorch/OpenMP threading deadlock when using model across threads
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
import json
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.ingest_claude import parse_claude_export
from ingest.ingest_chatgpt import parse_chatgpt_export
from ingest.ingest_mac_notes import import_mac_notes
from ingest.utils import search_memories, get_stats, RAW_DIR, get_embedding_model, purge_memories, set_progress_callback
from backend.goose_dyad import run_dyad_query, get_goose_status, is_goose_available, is_goose_configured
import threading

app = FastAPI(title="y=c API", version="0.1.0")

# Track model download/loading state
model_status = {
    "ready": False,
    "downloading": False,
    "error": None
}

@app.on_event("startup")
async def startup_event():
    """Pre-download and load the embedding model on startup (synchronous to avoid thread issues)."""
    model_status["downloading"] = True
    try:
        get_embedding_model()
        model_status["ready"] = True
        print("✓ Embedding model loaded", flush=True)
    except Exception as e:
        model_status["error"] = str(e)
        print(f"✗ Model load error: {e}", flush=True)
    finally:
        model_status["downloading"] = False


def smart_truncate(text: str, max_length: int = 600) -> str:
    """Truncate text at sentence or word boundary, not mid-word."""
    if len(text) <= max_length:
        return text

    # Try to find a sentence ending before max_length
    truncated = text[:max_length]

    # Look for sentence boundaries
    for ending in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
        last_pos = truncated.rfind(ending)
        if last_pos > max_length // 2:  # Only if we keep at least half
            return truncated[:last_pos + 1].strip()

    # Fall back to word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_length // 2:
        return truncated[:last_space].strip() + "..."

    return truncated.strip() + "..."


def clean_chunk_start(text: str) -> str:
    """Clean up chunks that start mid-word (from overlap chunking)."""
    if not text:
        return text

    # If text starts with lowercase letter, it's likely mid-word
    # Skip to the first complete word/sentence
    if text[0].islower():
        # Find first space or newline
        first_break = -1
        for i, char in enumerate(text[:100]):  # Only check first 100 chars
            if char in ' \n':
                first_break = i
                break
        if first_break > 0 and first_break < 50:
            text = "..." + text[first_break:].lstrip()

    return text

# Enable CORS for Tauri frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track ingestion progress
ingestion_status = {
    "active": False,
    "current_file": "",
    "progress": 0,
    "total_files": 0,
    "completed_files": 0,
    "chunks_added": 0,
    "error": None
}


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    status: str


class IngestionRequest(BaseModel):
    source_type: str  # 'claude', 'chatgpt', 'notes'
    file_path: Optional[str] = None
    force: bool = False  # Force reset if previous ingestion is stuck


# --- Health Check ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/model/status")
async def get_model_status():
    return model_status


@app.post("/purge")
async def purge():
    """Delete all memories from the vector database."""
    try:
        count = purge_memories()
        return {"status": "ok", "deleted": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Stats ---
@app.get("/stats")
async def stats():
    """Get database statistics."""
    try:
        db_stats = get_stats()
        # Transform to match frontend expected format
        return {
            "status": "ok",
            "stats": {
                "total_chunks": db_stats.get("total", 0),
                "sources": list(db_stats.get("by_type", {}).keys()),
                "by_type": db_stats.get("by_type", {}),
                "source_count": db_stats.get("sources", 0)
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "stats": {"total_chunks": 0, "sources": []}
        }


# --- File Upload ---
@app.post("/upload/{source_type}")
async def upload_file(source_type: str, file: UploadFile = File(...)):
    """
    Upload a file for ingestion.
    source_type: 'claude' or 'chatgpt'
    """
    if source_type not in ['claude', 'chatgpt']:
        raise HTTPException(status_code=400, detail=f"Invalid source type: {source_type}")

    # Ensure raw directory exists
    os.makedirs(RAW_DIR, exist_ok=True)

    # Save file to raw directory
    file_path = os.path.join(RAW_DIR, file.filename)

    try:
        contents = await file.read()
        with open(file_path, 'wb') as f:
            f.write(contents)

        return {
            "status": "ok",
            "message": f"File uploaded: {file.filename}",
            "file_path": file_path,
            "source_type": source_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# --- Ingestion ---
@app.post("/ingest")
async def ingest(request: IngestionRequest):
    """
    Start ingestion for a specific source.
    """
    global ingestion_status

    if ingestion_status["active"] and not request.force:
        raise HTTPException(status_code=409, detail="Ingestion already in progress")

    # Reset status (force reset if requested or starting fresh)
    ingestion_status = {
        "active": True,
        "current_file": request.file_path or request.source_type,
        "progress": 0,
        "total_files": 1,
        "completed_files": 0,
        "chunks_added": 0,
        "error": None
    }

    # Run ingestion in separate process (avoids PyTorch threading deadlocks)
    run_ingestion_in_subprocess(request.source_type, request.file_path)

    return {
        "status": "started",
        "source_type": request.source_type,
        "file_path": request.file_path
    }


def run_ingestion_sync(source_type: str, file_path: Optional[str]):
    """Synchronous background task to run ingestion."""
    global ingestion_status
    import glob

    try:
        chunks = 0
        import sys as _sys
        print(f"[Ingestion] Starting for source_type={source_type}, file_path={file_path}", flush=True)

        # Set up real-time progress callback
        def on_chunks_added(count):
            ingestion_status["chunks_added"] = ingestion_status.get("chunks_added", 0) + count
            c = ingestion_status["chunks_added"]
            ingestion_status["progress"] = min(90, 10 + int(c * 0.5))
            print(f"[Ingestion] Progress: {c} chunks added, progress={ingestion_status['progress']}", flush=True)
        set_progress_callback(on_chunks_added)

        if source_type == 'claude':
            if file_path:
                print(f"[Ingestion] Processing Claude file: {file_path}", flush=True)
                ingestion_status["total_files"] = 1
                ingestion_status["current_file"] = os.path.basename(file_path)
                ingestion_status["progress"] = 10
                chunks = parse_claude_export(file_path, log=False)
                ingestion_status["completed_files"] = 1
            else:
                files = glob.glob(os.path.join(RAW_DIR, "claude*.json"))
                files.extend(glob.glob(os.path.join(RAW_DIR, "Claude*.json")))
                files = list(set(files))
                print(f"[Ingestion] Found {len(files)} Claude files")

                ingestion_status["total_files"] = len(files)

                for i, fp in enumerate(files):
                    ingestion_status["current_file"] = os.path.basename(fp)
                    ingestion_status["progress"] = int((i / len(files)) * 100) if files else 0
                    chunks += parse_claude_export(fp, log=True)
                    ingestion_status["completed_files"] = i + 1

        elif source_type == 'chatgpt':
            if file_path:
                print(f"[Ingestion] Processing ChatGPT file: {file_path}")
                ingestion_status["total_files"] = 1
                ingestion_status["current_file"] = os.path.basename(file_path)
                ingestion_status["progress"] = 10
                chunks = parse_chatgpt_export(file_path, log=False)
                ingestion_status["completed_files"] = 1
            else:
                patterns = [
                    os.path.join(RAW_DIR, "*.zip"),
                    os.path.join(RAW_DIR, "chatgpt*.json"),
                    os.path.join(RAW_DIR, "conversations.json"),
                ]
                files = []
                for pattern in patterns:
                    files.extend(glob.glob(pattern))
                files = list(set(files))
                print(f"[Ingestion] Found {len(files)} ChatGPT files: {files}")

                ingestion_status["total_files"] = len(files)

                for i, fp in enumerate(files):
                    print(f"[Ingestion] Processing file {i+1}/{len(files)}: {fp}")
                    ingestion_status["current_file"] = os.path.basename(fp)
                    ingestion_status["progress"] = int(((i + 0.5) / len(files)) * 100) if files else 0
                    file_chunks = parse_chatgpt_export(fp, log=False)
                    chunks += file_chunks
                    print(f"[Ingestion] Added {file_chunks} chunks from {fp}")
                    ingestion_status["completed_files"] = i + 1
                    ingestion_status["progress"] = int(((i + 1) / len(files)) * 100) if files else 100

        elif source_type == 'notes':
            print("[Ingestion] Processing Mac Notes")
            ingestion_status["total_files"] = 1
            ingestion_status["current_file"] = "Mac Notes"
            ingestion_status["progress"] = 10
            chunks = import_mac_notes(log_structure=False)
            ingestion_status["completed_files"] = 1

        ingestion_status["chunks_added"] = chunks
        ingestion_status["progress"] = 100
        print(f"[Ingestion] Complete! Total chunks: {chunks}", flush=True)

    except Exception as e:
        import traceback
        print(f"[Ingestion] Error: {e}", flush=True)
        traceback.print_exc()
        _sys.stdout.flush()
        _sys.stderr.flush()
        ingestion_status["error"] = str(e)
    finally:
        set_progress_callback(None)
        ingestion_status["active"] = False


def run_ingestion_in_subprocess(source_type: str, file_path: Optional[str]):
    """Run ingestion in a separate process to avoid PyTorch threading deadlocks."""
    import subprocess
    import threading

    STATUS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', '.ingest_status.json')

    def monitor():
        global ingestion_status
        cmd = [
            sys.executable, '-m', 'backend.ingest_worker',
            '--source', source_type,
            '--status-file', STATUS_FILE,
        ]
        if file_path:
            cmd.extend(['--file', file_path])

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Poll status file for progress
        while proc.poll() is None:
            import time
            time.sleep(1)
            try:
                with open(STATUS_FILE, 'r') as f:
                    status_data = json.load(f)
                ingestion_status.update(status_data)
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        # Final read
        try:
            with open(STATUS_FILE, 'r') as f:
                status_data = json.load(f)
            ingestion_status.update(status_data)
        except:
            pass

        ingestion_status["active"] = False
        try:
            os.remove(STATUS_FILE)
        except:
            pass

    t = threading.Thread(target=monitor, daemon=True)
    t.start()


@app.get("/ingest/status")
async def ingest_status():
    """Get current ingestion status."""
    return ingestion_status


@app.post("/ingest/reset")
async def ingest_reset():
    """Reset ingestion status (use if stuck)."""
    global ingestion_status
    ingestion_status = {
        "active": False,
        "current_file": "",
        "progress": 0,
        "total_files": 0,
        "completed_files": 0,
        "chunks_added": 0,
        "error": None
    }
    return {"status": "ok", "message": "Ingestion status reset"}


@app.get("/ingest/progress")
async def ingest_progress_stream():
    """Stream ingestion progress via Server-Sent Events."""
    async def event_generator():
        while ingestion_status["active"]:
            yield f"data: {json.dumps(ingestion_status)}\n\n"
            await asyncio.sleep(0.5)
        # Send final status
        yield f"data: {json.dumps(ingestion_status)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# --- Search ---
@app.post("/search", response_model=QueryResponse)
async def search_endpoint(request: QueryRequest):
    """Search memories and return results."""
    try:
        results = search_memories(request.query, limit=request.top_k * 2)

        # Deduplicate
        seen_texts = set()
        unique_results = []
        for r in results:
            text = r.get("text", "")
            fingerprint = text[:100].lower().strip()
            if fingerprint not in seen_texts:
                seen_texts.add(fingerprint)
                unique_results.append(r)
            if len(unique_results) >= request.top_k:
                break

        sources = []
        for r in unique_results:
            cleaned_text = clean_chunk_start(r.get("text", ""))
            sources.append({
                "text": smart_truncate(cleaned_text, max_length=500),
                "source": r.get("source", ""),
                "source_type": r.get("source_type", ""),
                "score": r.get("_distance", 0) if "_distance" in r else r.get("score", 0)
            })

        return QueryResponse(
            answer=f"Found {len(unique_results)} relevant memories",
            sources=sources,
            status="ok"
        )
    except Exception as e:
        return QueryResponse(
            answer=f"Search failed: {str(e)}",
            sources=[],
            status="error"
        )


# --- Goose Status ---
@app.get("/goose/status")
async def goose_status():
    """Get Goose CLI installation and configuration status."""
    return get_goose_status()


# --- Query with Goose Dyad ---
@app.post("/ask", response_model=QueryResponse)
async def ask(request: QueryRequest):
    """
    Run adversarial dyad on query and return grounded response.
    Uses Goose with Coach-Player dyad for verified recall.
    Falls back to simple search if Goose is not available.
    """
    # Check if Goose is available and configured
    if is_goose_available() and is_goose_configured():
        try:
            # Run through Goose dyad
            dyad_result = run_dyad_query(request.query, timeout=180)

            if dyad_result.get("confidence") == "ERROR":
                # Goose failed, fall back to simple search
                print(f"[Goose] Error, falling back to search: {dyad_result.get('answer')}")
            else:
                # Format sources from dyad
                sources = []
                for source_name in dyad_result.get("sources", []):
                    sources.append({
                        "text": "",
                        "source": source_name,
                        "source_type": "dyad",
                        "score": 1.0
                    })

                answer = dyad_result.get("answer", "")

                return QueryResponse(
                    answer=answer,
                    sources=sources,
                    status="ok"
                )
        except Exception as e:
            print(f"[Goose] Exception: {e}")

    # Fallback: Simple search-based response
    results = search_memories(request.query, limit=request.top_k * 2)  # Get extra for deduplication

    if not results:
        return QueryResponse(
            answer="I couldn't find any relevant memories for that query. Try different keywords or check if your conversations have been ingested.",
            sources=[],
            status="ok"
        )

    # Deduplicate results based on text similarity
    seen_texts = set()
    unique_results = []
    for r in results:
        text = r.get("text", "")
        # Create a fingerprint from first 100 chars to detect duplicates
        fingerprint = text[:100].lower().strip()
        if fingerprint not in seen_texts:
            seen_texts.add(fingerprint)
            unique_results.append(r)
        if len(unique_results) >= request.top_k:
            break

    # Build a natural second-brain recall response
    memories_text = []
    sources = []

    for i, r in enumerate(unique_results[:3], 1):
        text = r.get("text", "")
        source_name = r.get("source", "Unknown")
        source_type = r.get("source_type", "")

        # Clean up source name
        clean_source = source_name.replace("chatgpt:", "").replace("claude:", "").strip()
        if not clean_source:
            clean_source = f"a past conversation"

        # Clean up chunk start and apply smart truncation
        display_text = clean_chunk_start(text)
        display_text = smart_truncate(display_text, max_length=600)

        # Format as natural memory recall
        memories_text.append(f"From *{clean_source}*:\n\n{display_text}")

        sources.append({
            "text": display_text,
            "source": source_name,
            "source_type": source_type,
            "score": r.get("score", 0)
        })

    # Natural intro - like your own mind recalling
    intro = "Let me recall what you were thinking about...\n\n"
    context_text = "\n\n---\n\n".join(memories_text)

    return QueryResponse(
        answer=f"{intro}{context_text}",
        sources=sources,
        status="ok"
    )


if __name__ == "__main__":
    print("Starting y=c API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
