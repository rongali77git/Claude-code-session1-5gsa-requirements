#!/usr/bin/env python3
"""
scripts/ingest_docs.py

CLI tool to ingest a folder of .docx files into the knowledge graph
and vector store.

Usage:
    python scripts/ingest_docs.py --input ./data/docs/
    python scripts/ingest_docs.py --input ./data/docs/ --rebuild
"""
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from ingestion.parser import DocxParser
from ingestion.chunker import SectionAwareChunker
from graph.builder import Neo4jClient, GraphBuilder
from embeddings.vector_store import Embedder, create_vector_store

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Ingest 5G SA .docx files")
    parser.add_argument("--input",   required=True, help="Folder containing .docx files")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop and rebuild graph + vector store from scratch")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        console.print(f"[red]Error: input folder not found: {input_dir}[/red]")
        sys.exit(1)

    doc_files = list(input_dir.glob("**/*.docx"))
    if not doc_files:
        console.print(f"[yellow]No .docx files found in {input_dir}[/yellow]")
        sys.exit(0)

    console.print(f"\n[bold cyan]5G SA Document Ingestion[/bold cyan]")
    console.print(f"Found [bold]{len(doc_files)}[/bold] .docx files\n")

    # Init components
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:

        t = progress.add_task("Loading embedding model...", total=None)
        embedder = Embedder()
        progress.update(t, description=f"[green]✓ Embedding model loaded (dim={embedder.dimension})")

        t2 = progress.add_task("Connecting to Neo4j...", total=None)
        neo4j_client = Neo4jClient()
        neo4j_client.apply_schema()
        progress.update(t2, description="[green]✓ Neo4j connected + schema applied")

        t3 = progress.add_task("Initializing vector store...", total=None)
        vs = create_vector_store(embedder)
        progress.update(t3, description=f"[green]✓ Vector store ready ({settings.vector_store_backend})")

    doc_parser = DocxParser()
    chunker    = SectionAwareChunker(max_tokens=settings.chunk_size,
                                     overlap_tokens=settings.chunk_overlap)
    graph_builder = GraphBuilder(neo4j_client)

    results = []

    for doc_file in doc_files:
        console.print(f"\n[bold]Processing:[/bold] {doc_file.name}")
        try:
            # Parse
            parsed = doc_parser.parse(doc_file)
            console.print(f"  → Detected carrier: [cyan]{parsed.carrier}[/cyan] | "
                           f"type: [cyan]{parsed.doc_type}[/cyan] | "
                           f"sections: {len(parsed.sections)}")

            # Build graph
            graph_builder.ingest_document(parsed)
            console.print(f"  → [green]Knowledge graph updated[/green]")

            # Embed + store
            chunks = chunker.chunk_document_sections(parsed.sections)
            if chunks:
                embed_texts = [c.to_embed_text() for c in chunks]
                with Progress(SpinnerColumn(), TextColumn("  Embedding chunks..."),
                              console=console, transient=True) as p2:
                    p2.add_task("", total=None)
                    embeddings = embedder.embed(embed_texts)
                vs.upsert(chunks, embeddings)
                console.print(f"  → [green]{len(chunks)} chunks embedded and stored[/green]")

            results.append({
                "file":     doc_file.name,
                "carrier":  parsed.carrier,
                "type":     parsed.doc_type,
                "sections": len(parsed.sections),
                "chunks":   len(chunks),
                "status":   "✓ OK",
            })

        except Exception as e:
            console.print(f"  → [red]ERROR: {e}[/red]")
            results.append({"file": doc_file.name, "status": f"✗ {e}",
                             "carrier": "?", "type": "?", "sections": 0, "chunks": 0})

    # Summary table
    console.print("\n[bold cyan]── Ingestion Summary ──[/bold cyan]\n")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("File",     style="dim")
    table.add_column("Carrier")
    table.add_column("Type")
    table.add_column("Sections", justify="right")
    table.add_column("Chunks",   justify="right")
    table.add_column("Status")

    for r in results:
        color = "green" if r["status"].startswith("✓") else "red"
        table.add_row(r["file"], r["carrier"], r["type"],
                      str(r["sections"]), str(r["chunks"]),
                      f"[{color}]{r['status']}[/{color}]")

    console.print(table)
    neo4j_client.close()
    console.print("\n[bold green]Done![/bold green] Start the API with: uvicorn api.main:app --reload\n")


if __name__ == "__main__":
    main()
