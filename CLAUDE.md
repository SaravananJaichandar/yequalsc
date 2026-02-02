# CLAUDE.md — Engineering Guidelines for y=c

## Critical: Known Footguns

### PyTorch + Threading = Deadlock
- **NEVER** run `model.encode()` in a `threading.Thread` inside a FastAPI/uvicorn server
- PyTorch/OpenMP will deadlock (process enters `UN` uninterruptible sleep on macOS)
- The fix: run ingestion in a **subprocess** via `backend/ingest_worker.py`
- `OMP_NUM_THREADS=1` must be set in `ingest/utils.py` BEFORE `import sentence_transformers`
- If ingestion appears stuck (chunks_added not increasing), check `ps aux | grep yc_server` for `UN` state

### Stale Processes
- After killing a deadlocked process, the port may stay bound for seconds
- Always verify with `lsof -i :8000` before restarting
- A `kill -9` on a `UN` state process may not release the port immediately — wait and retry
- **Never assume the running process has your latest code changes.** Verify the PID was started AFTER the edit

### Tauri CSP
- `"csp": null` is required for dev mode (Vite dev server on localhost:1420)
- Setting a restrictive CSP will cause the app to launch and immediately exit with no error
- Tighten CSP only for production builds, not during development

### Cargo.toml Package Name
- Package is `yequalsc` (not `app`). Changing this triggers a full recompile (~10-15s)
- The binary name must match what Tauri expects

## Architecture Rules

### Ingestion runs in a subprocess, not a thread
- `backend/ingest_worker.py` is a standalone script that does all embedding work
- It writes progress to `data/.ingest_status.json` (atomic write via tmp + rename)
- `yc_server.py` spawns it via `subprocess.Popen` and polls the status file
- This completely isolates PyTorch from the uvicorn event loop

### Embedding model loading
- Model `BAAI/bge-small-en-v1.5` is loaded synchronously in `startup_event`
- First `model.encode()` call takes 3-6s (PyTorch JIT warmup) — this is normal, not a deadlock
- Model is cached at `~/.cache/huggingface/hub/`

### Frontend progress
- Backend progress caps at 90 during processing, jumps to 100 on completion
- Frontend uses `Math.log2(1 + chunks_added) * 5 + 50` for smooth visual progress
- With large exports (300+ conversations, 6000+ chunks), ingestion takes ~4 minutes

## Stack

- **Frontend**: Tauri v2 + React 19 + Tailwind v4
- **Backend**: FastAPI on port 8000, started via `python -m backend.yc_server`
- **Vector DB**: LanceDB (embedded, at `data/memories/lancedb/`)
- **Embeddings**: `BAAI/bge-small-en-v1.5` via sentence-transformers
- **LLM**: Goose CLI (optional, for Coach-Player dyad)

## Testing Checklist (before saying "it works")

1. Kill ALL python/yc_server processes
2. Purge the database
3. Start backend fresh and verify `curl localhost:8000/health`
4. Trigger ingestion via the **actual UI**, not just curl
5. Wait for `chunks_added` to reach final count AND `active` to become `false`
6. Verify search returns results: `curl -X POST localhost:8000/search -d '{"query":"test"}'`
7. Only then say ingestion works
