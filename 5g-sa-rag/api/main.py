"""
api/main.py  +  api/routes/query.py  +  api/models.py

FastAPI backend — single file for simplicity, split into routes as you scale.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import structlog

from config.settings import settings
from ingestion.parser import DocxParser
from ingestion.chunker import SectionAwareChunker
from ingestion.entity_extractor import EntityExtractor
from graph.builder import Neo4jClient, GraphBuilder
from graph.queries import GraphQueryLibrary
from embeddings.vector_store import Embedder, create_vector_store
from retrieval.router import QueryRouter, RouteType, GraphRetriever, ContextAssembler
from llm.adapter import CorporateLLMAdapter

log = structlog.get_logger()

app = FastAPI(
    title="5G SA Carrier Requirements Query System",
    version="1.0.0",
    description="Hybrid GraphRAG for 5G SA carrier requirements and test plans",
)

# ── Singletons (initialized on startup) ──────────────────────────────────────
_embedder:   Embedder             | None = None
_vs:         object               | None = None
_neo4j:      Neo4jClient          | None = None
_graph_ql:   GraphQueryLibrary    | None = None
_llm:        CorporateLLMAdapter  | None = None
_router:     QueryRouter          | None = None
_g_retriever: GraphRetriever      | None = None
_assembler:  ContextAssembler     | None = None


@app.on_event("startup")
async def startup():
    global _embedder, _vs, _neo4j, _graph_ql, _llm, _router, _g_retriever, _assembler
    log.info("app_startup")
    _embedder    = Embedder()
    _vs          = create_vector_store(_embedder)
    _neo4j       = Neo4jClient()
    _graph_ql    = GraphQueryLibrary(_neo4j)
    _llm         = CorporateLLMAdapter()
    _router      = QueryRouter()
    _g_retriever = GraphRetriever(_graph_ql)
    _assembler   = ContextAssembler()
    log.info("app_ready")


@app.on_event("shutdown")
async def shutdown():
    if _neo4j:
        _neo4j.close()


# ── Request / Response models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    carrier_filter: str | None = None    # optional: restrict to one carrier
    top_k: int = 8
    conversation_history: list[dict] | None = None


class QueryResponse(BaseModel):
    answer: str
    route_used: str
    graph_results_count: int
    vector_chunks_count: int


class IngestRequest(BaseModel):
    folder_path: str     # path to folder containing .docx files


# ── Query endpoint ────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # 1. Route
    route = _router.classify(req.query)
    log.info("query_routed", route=route, query=req.query[:80])

    # 2. Graph retrieval
    graph_results: dict = {}
    if route in (RouteType.GRAPH, RouteType.BOTH):
        graph_results = _g_retriever.retrieve(req.query)

    # 3. Vector retrieval
    vector_chunks: list[dict] = []
    if route in (RouteType.VECTOR, RouteType.BOTH):
        q_embedding = _embedder.embed_one(req.query)
        filter_meta = {"carrier": req.carrier_filter} if req.carrier_filter else None
        vector_chunks = _vs.search(q_embedding, top_k=req.top_k, filter=filter_meta)

    # 4. Assemble context
    context = _assembler.assemble(graph_results, vector_chunks)

    # 5. LLM synthesis
    answer = _llm.query(
        user_query=req.query,
        context=context,
        conversation_history=req.conversation_history,
    )

    return QueryResponse(
        answer=answer,
        route_used=route.value,
        graph_results_count=sum(len(v) for v in graph_results.values()),
        vector_chunks_count=len(vector_chunks),
    )


# ── Ingest endpoint ───────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest(req: IngestRequest):
    parser   = DocxParser()
    chunker  = SectionAwareChunker(
        max_tokens=settings.chunk_size,
        overlap_tokens=settings.chunk_overlap,
    )
    builder  = GraphBuilder(_neo4j)
    _neo4j.apply_schema()

    ingested = []
    errors   = []

    for parsed_doc in parser.parse_folder(req.folder_path):
        try:
            # Graph
            builder.ingest_document(parsed_doc)

            # Vector store
            chunks = chunker.chunk_document_sections(parsed_doc.sections)
            if chunks:
                embed_texts = [c.to_embed_text() for c in chunks]
                embeddings  = _embedder.embed(embed_texts)
                _vs.upsert(chunks, embeddings)

            ingested.append({"doc": parsed_doc.doc_name, "chunks": len(chunks),
                              "sections": len(parsed_doc.sections),
                              "carrier": parsed_doc.carrier})
        except Exception as e:
            log.error("ingest_error", doc=parsed_doc.doc_name, error=str(e))
            errors.append({"doc": parsed_doc.doc_name, "error": str(e)})

    return {"ingested": ingested, "errors": errors, "total": len(ingested)}


# ── Graph stats endpoint ──────────────────────────────────────────────────────

@app.get("/graph/coverage")
async def coverage_summary():
    return _graph_ql.get_coverage_summary()


@app.get("/graph/carriers")
async def list_carriers():
    return {"carriers": _graph_ql.get_all_carriers()}


@app.get("/graph/gaps")
async def coverage_gaps(carrier: str | None = None):
    return _graph_ql.get_uncovered_requirements(carrier)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
