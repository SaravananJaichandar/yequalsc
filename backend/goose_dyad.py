"""
Goose Dyad integration for y=c.
Runs adversarial cooperation workflow for grounded memory recall.

The Coach-Player dyad prevents hallucination:
- Player: Creatively synthesizes from retrieved memories
- Coach: Verifies every claim has a source
- Output: Grounded answer + confidence (HIGH/MEDIUM/LOW)
"""
import json
import subprocess
import os
from pathlib import Path

# Add parent directory for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import search_memories


def format_search_results(results: list) -> str:
    """Format search results for inclusion in the prompt."""
    formatted = []
    for i, r in enumerate(results, 1):
        text = r.get("text", "")[:800]  # Limit text length
        source = r.get("source", "Unknown")
        score = r.get("score", 0)

        # Clean up source name
        clean_source = source.replace("chatgpt:", "").replace("claude:", "").strip()

        formatted.append(f"""
--- Memory {i} (from "{clean_source}", relevance: {score:.2f}) ---
{text}
""")

    return "\n".join(formatted)


def run_dyad_query(query: str, timeout: int = 60) -> dict:
    """
    Run a query through the Goose dyad with pre-fetched search results.

    This uses the simple/direct approach which:
    1. Pre-fetches relevant memories from LanceDB
    2. Sends them to Goose with dyad instructions
    3. Returns grounded response with sources and confidence

    Args:
        query: The user's question
        timeout: Max seconds to wait for response (default 60s)

    Returns:
        dict with 'answer', 'sources', and 'confidence'
    """
    # Check if goose is available
    goose_path = os.path.expanduser("~/.local/bin/goose")
    if not os.path.exists(goose_path):
        goose_path = "goose"  # Try system PATH

    try:
        # Pre-fetch search results from memory vault
        search_results = search_memories(query, limit=5, min_score=0.3)

        if not search_results:
            return {
                "answer": "I couldn't find any relevant memories for that query.",
                "sources": [],
                "confidence": "LOW"
            }

        # Format search results for the prompt
        results_text = format_search_results(search_results)

        # Build the dyad prompt - natural second brain recall
        full_prompt = f"""You ARE the user's memory. Not a search engine. Not an assistant. Their actual memory speaking back to them.

When someone asks their memory "what was I thinking about X?", the memory doesn't say "Based on 5 results..." - it just recalls naturally.

EXAMPLES OF GOOD RESPONSES:
"You were really diving deep into MEV arbitrage bots - exploring how to detect profitable opportunities on Ethereum DEXs. Your main approach was..."

"Remember your farm design project? You were inspired by Bill Mollison's permaculture principles and wanted to create a 7-acre model integrating aquaculture with..."

"You spent a lot of time thinking about LiDAR and camera fusion for autonomous vehicles. The core challenge you identified was..."

EXAMPLES OF BAD RESPONSES (NEVER DO THIS):
- "Based on the search results..."
- "Memory 1 shows..."
- "According to relevance score 0.58..."
- Bullet points listing "sources"
- Any mention of "confidence" mid-response

The user is asking: {query}

Here are fragments from their past thinking:
{results_text}

Now respond AS THEIR MEMORY - weave these fragments into a natural recall of what they were thinking about. Write 2-3 flowing paragraphs. At the very end, on its own line, write only: Confidence: HIGH or Confidence: MEDIUM or Confidence: LOW"""

        cmd = [
            goose_path,
            "run",
            "-t", full_prompt,
            "--no-session"
        ]

        # Run goose in headless mode
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent.parent)
        )

        if result.returncode != 0:
            # Log error but return a clean message
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            print(f"Goose error: {error_msg}", file=sys.stderr)
            return {
                "answer": "I had trouble processing that query. Please try again.",
                "sources": [],
                "confidence": "ERROR"
            }

        # Parse the output
        output = result.stdout.strip()
        return parse_dyad_response(output, search_results)

    except subprocess.TimeoutExpired:
        return {
            "answer": "Query timed out. Please try a simpler question.",
            "sources": [],
            "confidence": "ERROR"
        }
    except FileNotFoundError:
        return {
            "answer": "Goose CLI not found. Install: curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash",
            "sources": [],
            "confidence": "ERROR"
        }
    except Exception as e:
        print(f"Dyad error: {e}", file=sys.stderr)
        return {
            "answer": "An error occurred while processing your query.",
            "sources": [],
            "confidence": "ERROR"
        }


def parse_dyad_response(output: str, search_results: list = None) -> dict:
    """Parse the dyad's text output into structured response.

    Args:
        output: Raw output from Goose CLI
        search_results: Original search results for source extraction fallback
    """
    import re

    answer = output
    sources = []
    confidence = "MEDIUM"

    # Strip Goose session noise - both header and inline
    # First pass: strip any JSON blocks (Goose subagent noise)
    # Matches { ... } blocks that contain "name", "parameters", "task_ids", etc.
    output = re.sub(r'\{[^{}]*"(?:name|parameters|task_ids|execution_mode|subagent)[^{}]*\}', '', output, flags=re.DOTALL)
    # Also strip multi-line JSON with nested braces
    output = re.sub(r'"name"\s*:\s*"subagent__\w+".*?\n\s*\}', '', output, flags=re.DOTALL)
    # Strip any remaining orphaned JSON fragments
    output = re.sub(r'^\s*"[a-z_]+":\s*[\[\{"].*$', '', output, flags=re.MULTILINE)
    output = re.sub(r'^\s*[\[\]\{\}]\s*$', '', output, flags=re.MULTILINE)

    lines = output.split('\n')
    clean_lines = []

    # Known noise patterns to skip
    noise_prefixes = (
        'starting session', 'session id:', 'working directory:',
        '─', '-32', 'execution_mode:', 'task_ids:',
        'task_parameters:', 'extensions:', 'instructions:', 'settings:',
        'Direct quote:', 'Inference:',
        'Based on the search results',
    )

    for line in lines:
        stripped = line.strip()

        if stripped == '' or stripped == '-':
            continue

        # Skip known noise
        if any(stripped.startswith(prefix) for prefix in noise_prefixes):
            continue

        clean_lines.append(line)

    answer = '\n'.join(clean_lines).strip()

    # Remove code fences that Goose sometimes adds
    answer = re.sub(r'^```\w*\n?', '', answer, flags=re.MULTILINE).strip()
    answer = re.sub(r'\n?```$', '', answer, flags=re.MULTILINE).strip()

    # Extract confidence first (check various formats)
    confidence_patterns = [
        r'confidence:\s*(HIGH|MEDIUM|LOW)',
        r'\*\*Confidence\*\*[:\s]*(HIGH|MEDIUM|LOW)',
        r'Confidence[:\s]*(HIGH|MEDIUM|LOW)',
    ]
    for pattern in confidence_patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            confidence = match.group(1).upper()
            break

    # Remove confidence section from answer (various formats)
    answer = re.sub(r'##\s*\*?\*?Confidence\*?\*?.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*Confidence:\s*(HIGH|MEDIUM|LOW).*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*confidence:\s*(HIGH|MEDIUM|LOW).*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # Try to extract sources section from LLM output
    sources_patterns = [
        r'##\s*\*?\*?Sources\*?\*?\s*\n(.*?)(?=##|\Z)',
        r'Sources:\s*\n(.*?)(?=##|Confidence|\Z)',
    ]
    for pattern in sources_patterns:
        match = re.search(pattern, answer, re.IGNORECASE | re.DOTALL)
        if match:
            sources_text = match.group(1).strip()
            # Parse source lines
            for line in sources_text.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("•") or line.startswith("*"):
                    source = line.lstrip("-•*").strip()
                    # Extract just the source name from patterns like "Memory 1 (from "Source Name", relevance: 0.5)"
                    name_match = re.search(r'from\s*["\']([^"\']+)["\']', source)
                    if name_match:
                        sources.append(name_match.group(1))
                    elif source and "Confidence" not in source and "relevance" not in source.lower():
                        sources.append(source)
            # Remove sources section from answer
            answer = re.sub(pattern, '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
            break

    # Clean up the answer - remove markdown headers like "## **Response**"
    answer = re.sub(r'^##\s*\*?\*?Response\*?\*?\s*\n?', '', answer, flags=re.IGNORECASE | re.MULTILINE).strip()

    # Remove any remaining sources/confidence sections with various headers
    # Aggressive patterns to catch all variations
    answer = re.sub(r'\n*\*\*Sources\*\*.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*\*\*Confidence\*\*.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*\*\*Confidence:\*\*.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*#\s*Sources\s*\n.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*#\s*Confidence\s*\n.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*Sources:\s*\n.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*Sources\s*\n-.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # Remove Goose extension manager noise and other irrelevant text
    answer = re.sub(r'\n*\*?\*?Additional Info\*?\*?\s*\n.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'\n*Please enable the Extension Manager.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # Remove search-engine patterns that leak through
    # Remove search-engine patterns aggressively
    answer = re.sub(r'- Memory \d+ \(from "[^"]+", relevance: [\d.]+\)', '', answer).strip()
    answer = re.sub(r'"[^"]+" - Memory \d+ \(from "[^"]+", relevance: [\d.]+\)', '', answer).strip()
    answer = re.sub(r'\* Memory \d+ \(from "[^"]+"\)', '', answer).strip()
    answer = re.sub(r'Direct quote:.*?\n', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'Inference:.*?\n', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'Based on the search results,?\s*', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'Based on the provided search results,?\s*', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'From the search results provided,?\s*', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'^It appears that\s+', '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r'^It seems that\s+', '', answer, flags=re.IGNORECASE).strip()
    # Convert "I have been" to "You were" for second-brain voice
    answer = re.sub(r'^I have been\s+', 'You were ', answer, flags=re.IGNORECASE)
    answer = re.sub(r'^I was\s+', 'You were ', answer, flags=re.IGNORECASE)
    # Remove meta-commentary about recalling
    answer = re.sub(r"^My user's thoughts\.{3}\s*Let me see\.{3}\n*", '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r"Let me see\.{3}\n*", '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r"As I weave through the conversations\.{3}\s*\n*", '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r"Let's bring all the thoughts together\.{3}\s*", '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r"And one more thing -\s*", '', answer, flags=re.IGNORECASE).strip()
    answer = re.sub(r"\n---$", '', answer).strip()
    answer = re.sub(r'Note:.*$', '', answer, flags=re.IGNORECASE | re.MULTILINE).strip()

    # Remove trailing quoted text that looks like source citations
    answer = re.sub(r'\n*\*"[^"]+"\*\s*$', '', answer, flags=re.MULTILINE).strip()
    answer = re.sub(r'\n*- (HIGH|MEDIUM|LOW):.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()
    answer = re.sub(r'HIGH - Direct Quote.*$', '', answer, flags=re.IGNORECASE | re.DOTALL).strip()

    # Clean up any orphaned bullet points or empty lines
    answer = re.sub(r'\n\s*\*\s*\n', '\n', answer).strip()
    answer = re.sub(r'\n{3,}', '\n\n', answer).strip()

    # Fallback: if no sources extracted, use the search results
    if not sources and search_results:
        for r in search_results[:3]:  # Top 3 sources
            source_name = r.get("source", "").replace("chatgpt:", "").replace("claude:", "").strip()
            if source_name:
                sources.append(source_name)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence
    }


def is_goose_available() -> bool:
    """Check if Goose CLI is installed and configured."""
    try:
        goose_path = os.path.expanduser("~/.local/bin/goose")
        if not os.path.exists(goose_path):
            result = subprocess.run(["which", "goose"], capture_output=True)
            if result.returncode != 0:
                return False
        return True
    except Exception:
        return False


def is_goose_configured() -> bool:
    """Check if Goose has a provider configured."""
    config_path = Path.home() / ".config" / "goose" / "config.yaml"
    if not config_path.exists():
        return False

    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        # Check if provider is actually configured (not empty dict)
        return bool(config.get("GOOSE_PROVIDER") or config.get("provider") or len(config) > 0)
    except Exception:
        return False


def get_goose_status() -> dict:
    """Get Goose installation and configuration status."""
    goose_available = is_goose_available()

    if not goose_available:
        return {
            "available": False,
            "installed": False,
            "configured": False,
            "message": "Goose CLI not installed. Install: curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash"
        }

    # Check if configured (has provider set in config)
    configured = is_goose_configured()

    return {
        "available": True,
        "installed": True,
        "configured": configured,
        "message": "Goose ready" if configured else "Goose needs provider configuration. Run: goose configure"
    }


if __name__ == "__main__":
    # Test the dyad
    print("Goose status:", get_goose_status())

    if is_goose_available():
        test_query = "What do you know about farm design?"
        print(f"\nTesting query: {test_query}")
        result = run_dyad_query(test_query)
        print(json.dumps(result, indent=2))
