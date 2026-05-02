# 5G SA Carrier Requirements — GraphRAG System

A hybrid Knowledge Graph + RAG pipeline for querying 5G SA carrier-specific
requirements and test plan documents, powered by your corporate LLM.

---

## Architecture

```
DOCX Files
    ↓
Document Parser (python-docx / Unstructured.io)
    ↓                          ↓
Entity Extraction          Text Chunking
(Req IDs, features,        (by section/heading)
 test IDs, carriers)            ↓
    ↓                      Embeddings (Local BGE)
Knowledge Graph                ↓
(Neo4j/FalkorDB)           Vector Store (pgvector)
    ↓                          ↓
    └──────────┬───────────────┘
               ↓
         Query Router
               ↓
      Context Assembler
               ↓
       YOUR CORPORATE LLM
               ↓
         Query Interface (FastAPI + UI)
```

---

## Project Structure

```
5g-sa-rag/
├── ingestion/              # Document parsing & chunking
│   ├── parser.py           # python-docx parser
│   ├── chunker.py          # Section-aware chunker
│   └── entity_extractor.py # NER for Req IDs, test IDs, carriers
│
├── graph/                  # Knowledge graph layer
│   ├── schema.py           # Neo4j node/rel definitions
│   ├── builder.py          # Populates graph from extracted entities
│   ├── queries.py          # Cypher query library
│   └── neo4j_client.py     # Connection wrapper
│
├── embeddings/             # Vector store layer
│   ├── embedder.py         # Local BGE / corp embedding model
│   └── vector_store.py     # pgvector / ChromaDB abstraction
│
├── retrieval/              # Hybrid retrieval
│   ├── router.py           # Query classification & routing
│   ├── graph_retriever.py  # Graph-based retrieval
│   ├── vector_retriever.py # Semantic retrieval
│   └── assembler.py        # Context merging & ranking
│
├── llm/                    # Corporate LLM adapter
│   ├── adapter.py          # Swappable LLM interface
│   └── prompts.py          # System prompts & templates
│
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── routes/
│   │   ├── query.py
│   │   ├── ingest.py
│   │   └── graph.py
│   └── models.py
│
├── ui/                     # Simple query interface
│   └── index.html
│
├── config/
│   ├── settings.py         # Pydantic settings
│   └── .env.example
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_retrieval.py
│   └── test_graph.py
│
├── scripts/
│   ├── ingest_docs.py      # CLI: ingest a folder of docx files
│   └── rebuild_graph.py    # CLI: rebuild KG from scratch
│
├── requirements.txt
└── docker-compose.yml      # Neo4j + pgvector + app
```

---

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Start infrastructure
docker-compose up -d

# 3. Configure your corporate LLM
cp config/.env.example config/.env
# Edit .env with your LLM endpoint, API key, model name

# 4. Ingest your documents
python scripts/ingest_docs.py --input ./your-docx-folder/

# 5. Start the API
uvicorn api.main:app --reload

# 6. Open UI
open http://localhost:8000/ui
```

---

## Query Examples

```
"List all requirements for carrier Verizon related to handover"
"Which test cases cover REQ-SA-042?"
"Are there any requirements with no associated test cases?"
"Compare QoS requirements across all carriers"
"Summarize authentication test plan for T-Mobile"
"Find conflicts between AT&T and Verizon on slicing requirements"
```
