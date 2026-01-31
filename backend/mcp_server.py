"""
MCP (Model Context Protocol) Server for y=c memory tools.
Provides memory search and verification capabilities to Goose.
"""
import json
import sys
from typing import Any

# Add parent directory for imports
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

from ingest.utils import search_memories, embed_query, get_db, get_embedding_model

# Pre-load the embedding model at startup
print("Loading embedding model...", file=sys.stderr)
_model = get_embedding_model()
print("Embedding model ready", file=sys.stderr)


def handle_request(request: dict) -> dict:
    """Handle incoming MCP requests."""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "yc-memory",
                    "version": "0.1.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "search_memories",
                        "description": "Search through personal memories using semantic similarity. Returns relevant conversation snippets, notes, and documents.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query - what to look for in memories"
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Maximum number of results (default: 5)",
                                    "default": 5
                                },
                                "min_score": {
                                    "type": "number",
                                    "description": "Minimum similarity score 0-1 (default: 0.3)",
                                    "default": 0.3
                                }
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "verify_claim",
                        "description": "Verify if a specific claim or statement exists in the memories. Use this to fact-check before responding.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "claim": {
                                    "type": "string",
                                    "description": "The claim or statement to verify"
                                },
                                "context": {
                                    "type": "string",
                                    "description": "Additional context about where this claim came from"
                                }
                            },
                            "required": ["claim"]
                        }
                    },
                    {
                        "name": "get_memory_stats",
                        "description": "Get statistics about the memory vault - total chunks, sources, types.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            result = execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32000,
                    "message": str(e)
                }
            }

    elif method == "notifications/initialized":
        # Client notification, no response needed
        return None

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


def execute_tool(tool_name: str, arguments: dict) -> Any:
    """Execute a tool and return results."""
    if tool_name == "search_memories":
        query = arguments.get("query", "")
        limit = arguments.get("limit", 5)
        min_score = arguments.get("min_score", 0.3)

        results = search_memories(query, limit=limit, min_score=min_score)

        return {
            "query": query,
            "count": len(results),
            "memories": [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "source_type": r["source_type"],
                    "score": round(r["score"], 3),
                    "timestamp": r.get("timestamp", "")
                }
                for r in results
            ]
        }

    elif tool_name == "verify_claim":
        claim = arguments.get("claim", "")
        context = arguments.get("context", "")

        # Search for the claim with stricter threshold
        results = search_memories(claim, limit=3, min_score=0.5)

        if not results:
            return {
                "verified": False,
                "confidence": "LOW",
                "message": "No supporting evidence found in memories",
                "suggestion": "This claim may be ungrounded. Consider revising or removing it."
            }

        # Check if any result strongly supports the claim
        best_match = results[0]
        score = best_match["score"]

        if score >= 0.8:
            return {
                "verified": True,
                "confidence": "HIGH",
                "message": "Strong supporting evidence found",
                "source": best_match["source"],
                "evidence": best_match["text"][:500]
            }
        elif score >= 0.6:
            return {
                "verified": True,
                "confidence": "MEDIUM",
                "message": "Partial supporting evidence found",
                "source": best_match["source"],
                "evidence": best_match["text"][:500],
                "suggestion": "Consider qualifying this claim or adding context"
            }
        else:
            return {
                "verified": False,
                "confidence": "LOW",
                "message": "Weak or tangential evidence only",
                "closest_match": best_match["text"][:300],
                "suggestion": "This claim needs stronger grounding"
            }

    elif tool_name == "get_memory_stats":
        from ingest.utils import get_stats
        stats = get_stats()
        return {
            "total_chunks": stats.get("total", 0),
            "unique_sources": stats.get("sources", 0),
            "by_type": stats.get("by_type", {})
        }

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def main():
    """Main MCP server loop - reads JSON-RPC from stdin, writes to stdout."""
    # Unbuffered output for real-time communication
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    print("y=c MCP Server starting...", file=sys.stderr)

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            request = json.loads(line)
            response = handle_request(request)

            if response is not None:
                print(json.dumps(response), flush=True)

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": str(e)
                }
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()
