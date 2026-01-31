"""
Shared utilities for y=c ingestion pipeline
- Text chunking with overlap
- Embedding generation using sentence-transformers
- LanceDB storage operations
"""
import os

# Must be set before importing sentence_transformers/PyTorch to prevent
# OpenMP threading deadlock when embedding model is used across threads
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from datetime import datetime
from typing import Optional
import lancedb
from sentence_transformers import SentenceTransformer
from rich.console import Console

console = Console()

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
MEMORIES_DIR = os.path.join(DATA_DIR, "memories")
DB_PATH = os.path.join(MEMORIES_DIR, "lancedb")

# Chunking config
CHUNK_SIZE = 1000  # tokens (~4 chars per token)
CHUNK_OVERLAP = 200

# Embedding model (lightweight, runs on CPU)
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Global model instance (lazy loaded)
_embedding_model: Optional[SentenceTransformer] = None

# Progress callback: called with (chunks_added: int) after each add_memories
_progress_callback = None

def set_progress_callback(cb):
    global _progress_callback
    _progress_callback = cb


def get_embedding_model() -> SentenceTransformer:
    """Lazy load the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        console.print("[dim]Loading embedding model...[/dim]")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        console.print("[green]✓[/green] Embedding model loaded")
    return _embedding_model


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks.
    Uses character count as approximation (4 chars ≈ 1 token).
    """
    char_chunk_size = chunk_size * 4
    char_overlap = overlap * 4

    if len(text) <= char_chunk_size:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + char_chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings near the chunk boundary
            for sep in ['. ', '.\n', '! ', '?\n', '\n\n']:
                last_sep = text.rfind(sep, start + char_chunk_size // 2, end)
                if last_sep != -1:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - char_overlap
        if start < 0:
            start = 0

    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    model = get_embedding_model()
    # BGE models work better with instruction prefix for retrieval
    prefixed = [f"Represent this text for retrieval: {t}" for t in texts]
    embeddings = model.encode(prefixed, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def embed_query(query: str) -> list[float]:
    """Generate embedding for a search query."""
    model = get_embedding_model()
    # Different prefix for queries
    prefixed = f"Represent this query for retrieval: {query}"
    embedding = model.encode([prefixed], show_progress_bar=False, normalize_embeddings=True)
    return embedding[0].tolist()


def get_db() -> lancedb.DBConnection:
    """Get or create LanceDB connection."""
    os.makedirs(MEMORIES_DIR, exist_ok=True)
    return lancedb.connect(DB_PATH)


def create_memories_table(db: lancedb.DBConnection):
    """Create the memories table if it doesn't exist."""
    if "memories" not in db.table_names():
        import pyarrow as pa
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 384)),
            pa.field("source", pa.string()),
            pa.field("source_type", pa.string()),
            pa.field("timestamp", pa.string()),
            pa.field("metadata", pa.string()),
        ])
        try:
            db.create_table("memories", schema=schema)
            console.print("[green]✓[/green] Created memories table")
        except Exception:
            # Table may have been created by another thread
            pass


def add_memories(
    chunks: list[str],
    source: str,
    source_type: str,
    timestamp: Optional[str] = None,
    metadata: Optional[dict] = None
) -> int:
    """
    Add memory chunks to LanceDB.
    Returns number of chunks added.
    """
    import json
    import uuid

    if not chunks:
        return 0

    db = get_db()
    create_memories_table(db)

    # Generate embeddings
    console.print(f"[dim]Embedding {len(chunks)} chunks...[/dim]")
    embeddings = embed_texts(chunks)

    # Prepare records
    ts = timestamp or datetime.now().isoformat()
    meta_str = json.dumps(metadata or {})

    records = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        records.append({
            "id": str(uuid.uuid4()),
            "text": chunk,
            "vector": embedding,
            "source": source,
            "source_type": source_type,
            "timestamp": ts,
            "metadata": meta_str,
        })

    # Add to table
    table = db.open_table("memories")
    table.add(records)

    console.print(f"[green]✓[/green] Added {len(records)} memories from [cyan]{source}[/cyan]")
    if _progress_callback:
        _progress_callback(len(records))
    return len(records)


def search_memories(query: str, limit: int = 5, min_score: float = 0.3) -> list[dict]:
    """
    Search memories using vector similarity.
    Returns list of matching memories with scores.
    """
    db = get_db()

    if "memories" not in db.table_names():
        return []

    table = db.open_table("memories")
    query_embedding = embed_query(query)

    results = (
        table.search(query_embedding)
        .limit(limit)
        .to_list()
    )

    # Filter by score and format
    memories = []
    for r in results:
        score = 1 - r.get("_distance", 1)  # Convert distance to similarity
        if score >= min_score:
            memories.append({
                "text": r["text"],
                "source": r["source"],
                "source_type": r["source_type"],
                "timestamp": r["timestamp"],
                "score": score,
            })

    return memories


def purge_memories() -> int:
    """Drop all memories. Returns count of deleted chunks."""
    db = get_db()
    if "memories" not in db.table_names():
        return 0
    table = db.open_table("memories")
    count = table.count_rows()
    db.drop_table("memories")
    console.print(f"[red]✗[/red] Purged {count} memories")
    return count


def get_stats() -> dict:
    """Get statistics about stored memories."""
    db = get_db()

    if "memories" not in db.table_names():
        return {"total": 0, "by_type": {}}

    table = db.open_table("memories")
    df = table.to_pandas()

    return {
        "total": len(df),
        "by_type": df["source_type"].value_counts().to_dict(),
        "sources": df["source"].nunique(),
    }
