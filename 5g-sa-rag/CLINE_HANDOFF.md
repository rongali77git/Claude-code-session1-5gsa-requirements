# CLINE_HANDOFF.md
# 5G SA Carrier Requirements — GraphRAG System
# Handoff Brief for Cline + Corporate LLM Integration

---

## 1. Project Purpose

This system enables natural language querying over **5G SA carrier-specific
requirements and test plan .docx documents** using a hybrid
**Knowledge Graph + RAG** architecture, with your **corporate LLM** as the
reasoning layer.

Example queries this system answers:
- "Which test cases cover REQ-SA-042?"
- "List all uncovered requirements for Verizon"
- "Compare QoS requirements across all carriers"
- "Are there conflicts between AT&T and Verizon on handover requirements?"
- "Summarize the authentication test plan for T-Mobile"

---

## 2. Architecture Overview

```
DOCX Files
    ↓
Document Parser          (ingestion/parser.py)
    ↓                          ↓
Entity Extraction         Text Chunking
(ingestion/entity_extractor.py)  (ingestion/chunker.py)
    ↓                          ↓
Knowledge Graph           Embeddings → Vector Store
(graph/builder.py)        (embeddings/vector_store.py)
(Neo4j)                   (ChromaDB or pgvector)
    ↓                          ↓
    └──────────┬───────────────┘
               ↓
         Query Router            (retrieval/router.py)
               ↓
      Context Assembler          (retrieval/router.py → ContextAssembler)
               ↓
       CORPORATE LLM             (llm/adapter.py)   ← YOUR INTEGRATION POINT
               ↓
     FastAPI + Query UI          (api/main.py + ui/index.html)
```

---

## 3. Full Project Structure

```
5g-sa-rag/
├── ingestion/
│   ├── parser.py             # Parses .docx → structured sections
│   ├── chunker.py            # Splits sections → embeddable chunks
│   └── entity_extractor.py  # Extracts Req IDs, TC IDs, features, NR entities
│
├── graph/
│   ├── schema.py             # Neo4j constraints and indexes
│   ├── builder.py            # Populates graph from parsed docs
│   └── queries.py            # Cypher query library (coverage, gaps, comparisons)
│
├── embeddings/
│   └── vector_store.py       # Embedder class + ChromaDB/pgvector abstraction
│
├── retrieval/
│   └── router.py             # QueryRouter + GraphRetriever + ContextAssembler
│
├── llm/
│   ├── adapter.py            # *** CORPORATE LLM ADAPTER — PRIMARY INTEGRATION FILE ***
│   └── prompts.py            # System prompt + user message template
│
├── api/
│   └── main.py               # FastAPI app — /query, /ingest, /graph/* endpoints
│
├── ui/
│   └── index.html            # Browser query interface
│
├── config/
│   ├── settings.py           # Pydantic settings (reads from .env)
│   └── .env.example          # Template — copy to .env and fill in
│
├── scripts/
│   └── ingest_docs.py        # CLI: ingest a folder of .docx files
│
├── tests/
│   └── test_ingestion.py     # Unit tests for parser, extractor, chunker
│
├── Dockerfile
├── docker-compose.yml        # Neo4j + pgvector + app
└── requirements.txt
```

---

## 4. Priority Task List for Cline

Work through these in order:

### TASK 1 — Configure the corporate LLM (REQUIRED)

**File:** `config/.env`

```bash
cp config/.env.example config/.env
```

Fill in:
```
CORP_LLM_ENDPOINT=https://<your-internal-llm-url>/v1/chat/completions
CORP_LLM_API_KEY=<your-key>
CORP_LLM_MODEL_NAME=<your-model-name>
NEO4J_PASSWORD=<choose-a-password>
```

---

### TASK 2 — Adapt the LLM adapter to your corporate API schema (REQUIRED)

**File:** `llm/adapter.py`

The adapter uses **OpenAI chat completions format** by default. If your
corporate LLM uses a different request/response schema, override these
two methods ONLY — everything else stays the same:

```python
def _build_payload(self, messages: list[dict]) -> dict:
    """
    DEFAULT (OpenAI format):
    {
        "model": "...",
        "messages": [...],
        "max_tokens": 2048,
        "temperature": 0.1
    }

    OVERRIDE EXAMPLE for a custom internal API:
    {
        "prompt": messages[-1]["content"],
        "system": messages[0]["content"],
        "parameters": {"max_new_tokens": 2048}
    }
    """

def _parse_response(self, data: dict) -> str:
    """
    DEFAULT (OpenAI format):
        return data["choices"][0]["message"]["content"]

    OVERRIDE EXAMPLE for a custom internal API:
        return data["result"]["text"]
        # or: return data["output"]
        # or: return data["generated_text"]
    """
```

**Also check:** if your corp LLM requires additional headers beyond
`Authorization: Bearer <key>` (e.g. `x-api-version`, `x-tenant-id`,
client certificates, proxy settings), add them to the `self.headers`
dict in `CorporateLLMAdapter.__init__()`.

---

### TASK 3 — Decide on embedding strategy (REQUIRED)

**File:** `embeddings/vector_store.py`, class `Embedder`

**Option A — Use local BGE model (default, no data leaves network):**
```python
# Already configured. Model downloads from HuggingFace on first run (~1.3GB).
# Set in .env:
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
EMBEDDING_DEVICE=cpu   # or "cuda" if GPU available
```

**Option B — Use your corporate embedding endpoint:**

Replace the `Embedder` class in `embeddings/vector_store.py` with:

```python
class Embedder:
    def __init__(self):
        self.endpoint  = settings.corp_embedding_endpoint
        self.dimension = 1536   # ← set to your model's actual output dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            self.endpoint,
            json={"input": texts, "model": settings.corp_embedding_model},
            headers={"Authorization": f"Bearer {settings.corp_llm_api_key}"},
            timeout=60,
        )
        response.raise_for_status()
        return [item["embedding"] for item in response.json()["data"]]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
```

Then add to `config/settings.py`:
```python
corp_embedding_endpoint: str = ""
corp_embedding_model: str = ""
```

And add to `.env`:
```
CORP_EMBEDDING_ENDPOINT=https://<your-internal-embedding-url>
CORP_EMBEDDING_MODEL=<your-embedding-model-name>
```

> ⚠️ IMPORTANT: The embedding model used at ingest time and query time
> MUST be the same model. If you switch models, re-ingest all documents.

---

### TASK 4 — Choose vector store backend

**File:** `config/.env`

```
# For quick start / development:
VECTOR_STORE_BACKEND=chroma

# For production / enterprise:
VECTOR_STORE_BACKEND=pgvector
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=<your-pg-password>
```

Both are supported. ChromaDB requires no extra setup. pgvector requires
the postgres service from docker-compose.

---

### TASK 5 — Start infrastructure

```bash
docker-compose up -d
```

This starts:
- **Neo4j** on bolt://localhost:7687 (Browser UI: http://localhost:7474)
- **pgvector/Postgres** on localhost:5432 (only needed if VECTOR_STORE_BACKEND=pgvector)
- **App** on http://localhost:8000 (after build)

To run the app locally without Docker during development:
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn api.main:app --reload
```

---

### TASK 6 — Ingest documents

```bash
# Place your .docx files in data/docs/
mkdir -p data/docs
cp /path/to/your/docx/files/*.docx data/docs/

# Run ingestion
python scripts/ingest_docs.py --input ./data/docs/
```

The script will:
1. Parse each .docx into sections
2. Auto-detect carrier (Verizon, T-Mobile, AT&T, etc.) and doc type
3. Extract entities and populate Neo4j knowledge graph
4. Embed chunks and store in vector store
5. Print a summary table

---

### TASK 7 — Verify everything works

```bash
# Run unit tests
pytest tests/ -v

# Check API health
curl http://localhost:8000/health

# Check coverage stats
curl http://localhost:8000/graph/coverage

# Test a query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "List all requirements for carrier Verizon"}'
```

Open the UI: http://localhost:8000/ui

---

## 5. Carrier Auto-Detection

The system auto-detects carrier from document filename and content.
Supported out of the box: **Verizon, T-Mobile, AT&T, Dish, US-Cellular**

To add a new carrier, edit `ingestion/parser.py`:
```python
CARRIER_PATTERNS = {
    "Verizon":    r"\b(verizon|vzw)\b",
    "T-Mobile":   r"\b(t-?mobile|tmobile|tmo)\b",
    "AT&T":       r"\b(at&t|att)\b",
    "NewCarrier": r"\b(newcarrier|nc)\b",   # ← add here
}
```

---

## 6. Requirement / Test Case ID Patterns

The entity extractor recognizes IDs matching:
- Requirements: `REQ-SA-001`, `REQ-QOS-003`, `REQ_AUTH_007` etc.
- Test Cases:   `TC-SA-042`, `TC-001`, `TC_QOS_003` etc.

If your documents use a different naming convention, update the patterns
in `ingestion/entity_extractor.py`:
```python
REQ_ID_PATTERN = re.compile(r"\b(REQ[-_][A-Z0-9]+[-_][A-Z0-9]+)\b", re.IGNORECASE)
TC_ID_PATTERN  = re.compile(r"\b(TC[-_][A-Z0-9]+(?:[-_][A-Z0-9]+)*)\b", re.IGNORECASE)
```

---

## 7. API Endpoints Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/query` | Main query endpoint — hybrid graph + vector + LLM |
| POST | `/ingest` | Ingest a folder of .docx files |
| GET  | `/graph/coverage` | Coverage summary per carrier |
| GET  | `/graph/carriers` | List all carriers in the graph |
| GET  | `/graph/gaps?carrier=Verizon` | Uncovered requirements (optional filter) |
| GET  | `/health` | Health check |

**Query request body:**
```json
{
  "query": "Which test cases cover REQ-SA-042?",
  "carrier_filter": "Verizon",        
  "top_k": 8,                          
  "conversation_history": []           
}
```

---

## 8. Key Dependencies

| Package | Purpose |
|---------|---------|
| `python-docx` | Parse .docx files |
| `sentence-transformers` | Local BGE embedding model |
| `neo4j` | Knowledge graph driver |
| `chromadb` | Vector store (dev) |
| `psycopg2` + `pgvector` | Vector store (prod) |
| `fastapi` + `uvicorn` | API server |
| `httpx` | HTTP client for corporate LLM calls |
| `tenacity` | Retry logic for LLM calls |
| `spacy` | NLP support |
| `rich` | CLI output formatting |

---

## 9. Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` from LLM | Check `CORP_LLM_API_KEY` in `.env` |
| `KeyError: choices` on LLM response | Override `_parse_response()` in `llm/adapter.py` |
| Neo4j connection refused | Run `docker-compose up -d neo4j` |
| Embedding dim mismatch on search | Re-ingest all docs after changing embedding model |
| Carrier shows as "Unknown" | Add pattern to `CARRIER_PATTERNS` in `ingestion/parser.py` |
| No Req IDs extracted | Check ID format matches regex in `entity_extractor.py` |
| Slow first run | BGE model downloading (~1.3GB) — normal, cached after first run |

---

## 10. Extending the System (Future Use Cases)

| Use Case | What to build |
|----------|--------------|
| Traceability matrix export | Query `graph/queries.py` → export to Excel |
| Conflict auto-detection | Expand `find_feature_conflicts()` in `graph/queries.py` |
| Test coverage dashboard | Call `/graph/coverage` → visualize in UI |
| Multi-version doc diffing | Add `version` property to Document nodes in Neo4j |
| Slack/Teams bot | Add a new route in `api/main.py` that accepts webhook payloads |
| CI/CD coverage gate | Call `/graph/gaps` in pipeline — fail if P0 gaps exist |
