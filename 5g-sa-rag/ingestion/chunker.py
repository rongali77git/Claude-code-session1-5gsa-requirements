"""
ingestion/chunker.py

Splits DocSection content into LLM-ready chunks.

Strategy:
  1. First tries to keep a full section as one chunk (if within limit)
  2. If section is too long, splits by paragraph boundaries
  3. Always preserves metadata: section heading, doc name, carrier, doc type
  4. Adds table rows as separate chunks with column context
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ingestion.parser import DocSection


@dataclass
class Chunk:
    """A text chunk ready for embedding and storage."""
    chunk_id: str                  # unique: {doc_name}_{section_idx}_{chunk_idx}
    doc_name: str
    doc_type: str
    carrier: str
    heading: str
    section_path: list[str]
    text: str                      # the actual text to embed
    chunk_type: str = "text"       # "text" | "table"
    metadata: dict = field(default_factory=dict)

    def to_embed_text(self) -> str:
        """
        Prepends context to the chunk text so embeddings carry
        document/section context even for short chunks.
        """
        return (
            f"Document: {self.doc_name} | "
            f"Carrier: {self.carrier} | "
            f"Type: {self.doc_type} | "
            f"Section: {' > '.join(self.section_path) or self.heading}\n\n"
            f"{self.text}"
        )


class SectionAwareChunker:
    """
    Chunks DocSection objects into fixed-size overlapping text chunks,
    preserving section metadata.
    """

    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 64,
                 chars_per_token: float = 4.0):
        self.max_chars   = int(max_tokens * chars_per_token)
        self.overlap     = int(overlap_tokens * chars_per_token)

    # ── Public API ────────────────────────────────────────────────────────────

    def chunk_section(self, section: DocSection, section_idx: int) -> list[Chunk]:
        chunks: list[Chunk] = []

        # 1. Text chunks
        for i, text in enumerate(self._split_text(section.content)):
            chunks.append(Chunk(
                chunk_id=f"{section.doc_name}_{section_idx}_{i}",
                doc_name=section.doc_name,
                doc_type=section.doc_type,
                carrier=section.carrier,
                heading=section.heading,
                section_path=section.section_path,
                text=text,
                chunk_type="text",
                metadata={
                    "heading_level": section.heading_level,
                    "page_hint": section.page_hint,
                },
            ))

        # 2. Table chunks (each table becomes its own chunk)
        for t_idx, table in enumerate(section.tables):
            table_text = self._table_to_text(table)
            if table_text.strip():
                chunks.append(Chunk(
                    chunk_id=f"{section.doc_name}_{section_idx}_tbl{t_idx}",
                    doc_name=section.doc_name,
                    doc_type=section.doc_type,
                    carrier=section.carrier,
                    heading=section.heading,
                    section_path=section.section_path,
                    text=table_text,
                    chunk_type="table",
                    metadata={
                        "table_index": t_idx,
                        "rows": len(table),
                        "cols": len(table[0]) if table else 0,
                    },
                ))

        return chunks

    def chunk_document_sections(self, sections: list[DocSection]) -> list[Chunk]:
        all_chunks: list[Chunk] = []
        for idx, section in enumerate(sections):
            all_chunks.extend(self.chunk_section(section, idx))
        return all_chunks

    # ── Internals ─────────────────────────────────────────────────────────────

    def _split_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks, breaking at paragraph boundaries."""
        if not text.strip():
            return []

        if len(text) <= self.max_chars:
            return [text.strip()]

        # Split into paragraphs first
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.max_chars:
                current = (current + "\n\n" + para).strip()
            else:
                if current:
                    chunks.append(current)
                # Start new chunk with overlap from end of previous
                overlap_text = current[-self.overlap:] if current else ""
                current = (overlap_text + "\n\n" + para).strip()

                # If a single paragraph is still too long, hard-split it
                if len(current) > self.max_chars:
                    for hard_chunk in self._hard_split(current):
                        chunks.append(hard_chunk)
                    current = ""

        if current:
            chunks.append(current)

        return chunks

    def _hard_split(self, text: str) -> Iterator[str]:
        """Last resort: split long text at sentence boundaries."""
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text)
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 <= self.max_chars:
                current = (current + " " + sent).strip()
            else:
                if current:
                    yield current
                current = sent
        if current:
            yield current

    def _table_to_text(self, table: list[list[str]]) -> str:
        """Convert a 2D table to readable text with header context."""
        if not table:
            return ""
        lines = []
        headers = table[0]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
        for row in table[1:]:
            # Pad row to match header length
            padded = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(padded[: len(headers)]) + " |")
        return "\n".join(lines)
