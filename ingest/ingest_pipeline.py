"""
Master ingestion pipeline for y=c
Runs all parsers and indexes into LanceDB

Usage:
    python -m ingest.ingest_pipeline          # Run full pipeline
    python -m ingest.ingest_pipeline --stats  # Show database stats
    python -m ingest.ingest_pipeline --search "query"  # Test search
"""
import argparse
import os
import sys
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.ingest_claude import ingest_all_claude_exports
from ingest.ingest_chatgpt import ingest_all_chatgpt_exports
from ingest.ingest_notes import ingest_all_notes
from ingest.ingest_pdfs import ingest_all_pdfs
from ingest.utils import get_stats, search_memories, RAW_DIR, MEMORIES_DIR

console = Console()


def print_banner():
    """Print y=c banner."""
    banner = """
    ╦ ╦ ═ ╔═╗
    ╚═╝   ║
          ╚═╝
    Private Memory Vault
    """
    console.print(Panel(banner, title="[bold blue]y=c Ingestion Pipeline[/bold blue]", border_style="blue"))


def run_pipeline(verbose: bool = True) -> dict:
    """
    Run all ingestion scripts and index to LanceDB.
    Returns dict with counts by source type.
    """
    print_banner()

    # Check raw directory exists
    if not os.path.exists(RAW_DIR):
        os.makedirs(RAW_DIR, exist_ok=True)
        console.print(f"[yellow]Created data/raw/ directory[/yellow]")
        console.print(f"[dim]Drop your exports here and run again:[/dim]")
        console.print(f"  • Claude: claude_export.json")
        console.print(f"  • ChatGPT: conversations.json or export.zip")
        console.print(f"  • Notes: .md, .txt, or Obsidian vault folder")
        console.print(f"  • PDFs: .pdf files")
        return {"total": 0}

    results = {
        "claude": 0,
        "chatgpt": 0,
        "notes": 0,
        "pdf": 0,
        "total": 0,
        "start_time": datetime.now().isoformat(),
    }

    # Run each ingestion module
    console.print("\n[bold]Phase 1: Claude Exports[/bold]")
    console.print("─" * 40)
    results["claude"] = ingest_all_claude_exports()

    console.print("\n[bold]Phase 2: ChatGPT Exports[/bold]")
    console.print("─" * 40)
    results["chatgpt"] = ingest_all_chatgpt_exports()

    console.print("\n[bold]Phase 3: Notes & Markdown[/bold]")
    console.print("─" * 40)
    results["notes"] = ingest_all_notes()

    console.print("\n[bold]Phase 4: PDFs & Papers[/bold]")
    console.print("─" * 40)
    results["pdf"] = ingest_all_pdfs()

    # Calculate total
    results["total"] = sum([
        results["claude"],
        results["chatgpt"],
        results["notes"],
        results["pdf"]
    ])

    results["end_time"] = datetime.now().isoformat()

    # Print summary
    print_summary(results)

    return results


def print_summary(results: dict):
    """Print ingestion summary."""
    console.print("\n")

    table = Table(title="Ingestion Summary", border_style="blue")
    table.add_column("Source", style="cyan")
    table.add_column("Chunks Added", justify="right", style="green")

    table.add_row("Claude Exports", str(results.get("claude", 0)))
    table.add_row("ChatGPT Exports", str(results.get("chatgpt", 0)))
    table.add_row("Notes & Markdown", str(results.get("notes", 0)))
    table.add_row("PDFs & Papers", str(results.get("pdf", 0)))
    table.add_row("─" * 15, "─" * 10)
    table.add_row("[bold]Total[/bold]", f"[bold]{results.get('total', 0)}[/bold]")

    console.print(table)

    if results.get("total", 0) > 0:
        console.print(f"\n[green]✓ Memories stored in:[/green] {MEMORIES_DIR}")
    else:
        console.print(f"\n[yellow]No files found to ingest.[/yellow]")
        console.print(f"[dim]Add files to {RAW_DIR} and run again.[/dim]")


def show_stats():
    """Show database statistics."""
    print_banner()

    stats = get_stats()

    if stats["total"] == 0:
        console.print("[yellow]No memories in database yet.[/yellow]")
        console.print("[dim]Run the ingestion pipeline first.[/dim]")
        return

    console.print(f"\n[bold]Memory Database Statistics[/bold]")
    console.print("─" * 40)

    table = Table(border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")

    table.add_row("Total Chunks", str(stats["total"]))
    table.add_row("Unique Sources", str(stats.get("sources", 0)))

    console.print(table)

    if stats.get("by_type"):
        console.print("\n[bold]By Source Type:[/bold]")
        type_table = Table(border_style="dim")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Chunks", justify="right")

        for source_type, count in stats["by_type"].items():
            type_table.add_row(source_type, str(count))

        console.print(type_table)


def test_search(query: str, limit: int = 5):
    """Test search functionality."""
    print_banner()

    console.print(f"\n[bold]Searching for:[/bold] {query}")
    console.print("─" * 40)

    results = search_memories(query, limit=limit)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, r in enumerate(results, 1):
        score_pct = int(r["score"] * 100)
        console.print(f"\n[bold cyan]Result {i}[/bold cyan] (Score: {score_pct}%)")
        console.print(f"[dim]Source:[/dim] {r['source']}")
        console.print(f"[dim]Type:[/dim] {r['source_type']}")

        # Truncate text for display
        text = r["text"]
        if len(text) > 300:
            text = text[:300] + "..."
        console.print(Panel(text, border_style="dim"))


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="y=c Ingestion Pipeline - Index your memories into LanceDB"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )
    parser.add_argument(
        "--search",
        type=str,
        metavar="QUERY",
        help="Test search with a query"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of search results (default: 5)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Minimal output"
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.search:
        test_search(args.search, limit=args.limit)
    else:
        run_pipeline(verbose=not args.quiet)


if __name__ == "__main__":
    main()
