"""
embeddings/embedder.py  +  embeddings/vector_store.py

Local BGE embedding model + pluggable vector store (Chroma or pgvector).
No data leaves your network — embeddings run entirely on-premise.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod

import structlog
from sentence_transformers import SentenceTransformer

from config.settings import settings
from ingestion.chunker import Chunk

log = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
#  Embedder
# ─────────────────────────────────────────────────────────────────────────────

class Embedder:
    """
    Wraps a local SentenceTransformer model.
    Default: BAAI/bge-large-en-v1.5  (strong on technical/domain text)
    """

    def __init__(self):
        log.info("loading_embedding_model", model=settings.embedding_model)
        self.model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        self.dimension = self.model.get_sentence_embedding_dimension()
        log.info("embedding_model_ready", dim=self.dimension)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings. Returns list of float vectors."""
        return self.model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            show_progress_bar=len(texts) > 50,
            normalize_embeddings=True,  # cosine similarity ready
        ).tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Abstract vector store interface
# ─────────────────────────────────────────────────────────────────────────────

class VectorStore(ABC):
    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int = 8,
               filter: dict | None = None) -> list[dict]: ...

    @abstractmethod
    def delete_by_doc(self, doc_name: str) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
#  ChromaDB implementation  (easiest to get started)
# ─────────────────────────────────────────────────────────────────────────────

class ChromaVectorStore(VectorStore):
    def __init__(self):
        import chromadb
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._col = self._client.get_or_create_collection(
            name="5gsa_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        log.info("chroma_store_ready", path=settings.chroma_persist_dir)

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        ids        = [c.chunk_id for c in chunks]
        documents  = [c.text for c in chunks]
        metadatas  = [
            {
                "doc_name":     c.doc_name,
                "doc_type":     c.doc_type,
                "carrier":      c.carrier,
                "heading":      c.heading,
                "chunk_type":   c.chunk_type,
                "section_path": " > ".join(c.section_path),
            }
            for c in chunks
        ]
        self._col.upsert(ids=ids, documents=documents,
                         embeddings=embeddings, metadatas=metadatas)

    def search(self, query_embedding: list[float], top_k: int = 8,
               filter: dict | None = None) -> list[dict]:
        kwargs: dict = {"query_embeddings": [query_embedding], "n_results": top_k,
                        "include": ["documents", "metadatas", "distances"]}
        if filter:
            kwargs["where"] = filter

        results = self._col.query(**kwargs)
        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text":     doc,
                "metadata": results["metadatas"][0][i],
                "score":    1 - results["distances"][0][i],  # cosine → similarity
            })
        return output

    def delete_by_doc(self, doc_name: str) -> None:
        self._col.delete(where={"doc_name": doc_name})


# ─────────────────────────────────────────────────────────────────────────────
#  pgvector implementation  (for production / enterprise)
# ─────────────────────────────────────────────────────────────────────────────

class PgVectorStore(VectorStore):
    def __init__(self, dimension: int):
        import psycopg2
        from psycopg2.extras import execute_values

        self._conn = psycopg2.connect(
            host=settings.postgres_host, port=settings.postgres_port,
            dbname=settings.postgres_db, user=settings.postgres_user,
            password=settings.postgres_password,
        )
        self._execute_values = execute_values
        self._dim = dimension
        self._init_table()
        log.info("pgvector_store_ready")

    def _init_table(self):
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id    TEXT PRIMARY KEY,
                    doc_name    TEXT,
                    doc_type    TEXT,
                    carrier     TEXT,
                    heading     TEXT,
                    chunk_type  TEXT,
                    section_path TEXT,
                    text        TEXT,
                    metadata    JSONB,
                    embedding   vector({self._dim})
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops)")
            cur.execute("CREATE INDEX IF NOT EXISTS chunks_carrier_idx ON chunks (carrier)")
            cur.execute("CREATE INDEX IF NOT EXISTS chunks_doc_name_idx ON chunks (doc_name)")
        self._conn.commit()

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        rows = [
            (
                c.chunk_id, c.doc_name, c.doc_type, c.carrier,
                c.heading, c.chunk_type, " > ".join(c.section_path),
                c.text, json.dumps(c.metadata), emb,
            )
            for c, emb in zip(chunks, embeddings)
        ]
        with self._conn.cursor() as cur:
            self._execute_values(cur, """
                INSERT INTO chunks
                  (chunk_id, doc_name, doc_type, carrier, heading,
                   chunk_type, section_path, text, metadata, embedding)
                VALUES %s
                ON CONFLICT (chunk_id) DO UPDATE SET
                  text = EXCLUDED.text, embedding = EXCLUDED.embedding,
                  metadata = EXCLUDED.metadata
            """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)")
        self._conn.commit()

    def search(self, query_embedding: list[float], top_k: int = 8,
               filter: dict | None = None) -> list[dict]:
        where_clause = ""
        if filter:
            conditions = [f"{k} = %s" for k in filter]
            where_clause = "WHERE " + " AND ".join(conditions)

        filter_vals = list(filter.values()) if filter else []
        exec_params = [str(query_embedding)] + filter_vals + [str(query_embedding), top_k]

        with self._conn.cursor() as cur:
            cur.execute(f"""
                SELECT chunk_id, text, doc_name, doc_type, carrier,
                       heading, chunk_type, section_path,
                       1 - (embedding <=> %s::vector) AS score
                FROM chunks
                {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, exec_params)
            rows = cur.fetchall()

        return [
            {
                "text": row[1],
                "score": float(row[8]),
                "metadata": {
                    "doc_name": row[2], "doc_type": row[3], "carrier": row[4],
                    "heading": row[5], "chunk_type": row[6], "section_path": row[7],
                },
            }
            for row in rows
        ]

    def delete_by_doc(self, doc_name: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE doc_name = %s", (doc_name,))
        self._conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_vector_store(embedder: Embedder) -> VectorStore:
    if settings.vector_store_backend == "pgvector":
        return PgVectorStore(dimension=embedder.dimension)
    return ChromaVectorStore()
