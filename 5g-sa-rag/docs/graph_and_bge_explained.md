# Knowledge Graph + BGE Model — Purpose & Design

This document explains why the system uses both a Knowledge Graph (Neo4j) and a
BGE embedding model (vector search), and what each one does that the other cannot.

---

## 1. The BGE Embedding Model

### What It Is

`BAAI/bge-large-en-v1.5` is a local embedding model that runs entirely on your
machine. It converts text into a list of 1024 numbers (a vector) that represents
the **meaning** of that text.

### What It Does in This System

**At ingestion time (once per document):**

```
.docx section text
        ↓
    BGE Model
        ↓
 [0.23, -0.87, 0.41, ...]   ← 1024 numbers representing the meaning
        ↓
 Stored in ChromaDB / pgvector
```

**At query time (every search):**

```
User question: "What are the latency requirements for cell switching?"
        ↓
    BGE Model
        ↓
 [0.21, -0.85, 0.39, ...]   ← numbers for the question meaning
        ↓
 Compare against all stored vectors
        ↓
 Return top-K most semantically similar document chunks
```

### The Problem It Solves

Your `.docx` file might say:

> *"The gNB shall complete the Xn handover procedure within 50 milliseconds"*

A user asks:

> *"What are the latency requirements for cell switching?"*

The words **do not match** — "handover" vs "cell switching", "50ms" vs "latency".
A keyword search finds nothing. The BGE model understands they mean the same thing
and finds the right section anyway.

### Why BGE Specifically

BGE was trained heavily on technical and scientific text. This makes it
significantly better than general-purpose embedding models at understanding
3GPP terminology: AMF, NSSAI, 5QI, PDU Session, Xn handover, AUSF, S-NSSAI, etc.

### What BGE Cannot Do

BGE finds text that is **semantically similar**. It cannot:

- Tell you definitively which test cases are linked to a specific requirement
- Find requirements that have **no** test cases
- Count or compare requirements across carriers
- Trace relationships that span multiple documents

For all of that, you need the Knowledge Graph.

---

## 2. The Knowledge Graph (Neo4j)

### What It Is

Neo4j stores entities (requirements, test cases, carriers, features) as **nodes**
and their connections as **relationships**. You query it with Cypher — a graph
query language.

### What Lives in the Graph

```
(:Carrier {name: "Verizon"})
        │
        │ HAS_REQUIREMENT
        ▼
(:Requirement {req_id: "REQ-SA-042", priority: "P0"})
        │
        │ VERIFIED_BY
        ▼
(:TestCase {tc_id: "TC-SA-007", status: "Pass"})
        │
        │ RELATES_TO
        ▼
(:Feature {name: "Handover"})
```

**Node types:**

| Node | Key property | Represents |
|------|-------------|------------|
| `:Carrier` | `name` | Verizon, T-Mobile, AT&T, etc. |
| `:Requirement` | `req_id` | REQ-SA-042, REQ-QOS-003, etc. |
| `:TestCase` | `tc_id` | TC-SA-007, TC-AUTH-001, etc. |
| `:Feature` | `name` | Handover, QoS, Authentication, etc. |
| `:NREntity` | `name` | AMF, SMF, UPF, gNB, NSSAI, etc. |
| `:Document` | `name` | Source .docx filename |
| `:Section` | `section_id` | A section within a document |

**Relationship types:**

```
(:Carrier)     -[:HAS_REQUIREMENT]→  (:Requirement)
(:Requirement) -[:VERIFIED_BY]→      (:TestCase)
(:TestCase)    -[:COVERS]→           (:Requirement)
(:Requirement) -[:RELATES_TO]→       (:Feature)
(:Requirement) -[:INVOLVES]→         (:NREntity)
(:Document)    -[:CONTAINS]→         (:Section)
(:Section)     -[:HAS_REQUIREMENT]→  (:Requirement)
```

### How the Graph Gets Built

When you ingest a `.docx`, the system automatically:

1. Finds `REQ-SA-042` → creates a `:Requirement` node
2. Finds `TC-SA-007` → creates a `:TestCase` node
3. Finds text like *"REQ-SA-042 is verified by TC-SA-007"* → creates `VERIFIED_BY` edge
4. Detects `Verizon` in the doc → links both to the `:Carrier` node
5. Finds `Handover` keyword → links requirement to `:Feature` node

This works **across multiple documents**. A requirement in one `.docx` and its
test case in a different `.docx` are still connected in the graph.

### What Only the Graph Can Answer

| Question | Why only the graph can answer it |
|----------|----------------------------------|
| "Which TCs cover REQ-SA-042?" | Needs exact `VERIFIED_BY` traversal |
| "List all uncovered requirements for Verizon" | Needs REQs with no outgoing `VERIFIED_BY` link |
| "Compare handover req counts across carriers" | Needs to count across multiple carrier nodes |
| "Find conflicts between AT&T and Verizon on QoS" | Needs to compare same feature across carriers |
| "What is the coverage gap for T-Mobile?" | Total REQs minus those with linked TCs |
| "All P0 requirements with no test case" | Filter by priority + detect missing relationship |

### Graph vs BGE on the Same Question

```
USER ASKS: "Which test cases cover REQ-SA-042?"

BGE approach:
  Searches for text similar to "REQ-SA-042 test cases"
  Returns chunks that mention both terms near each other
  ✗ May miss TCs defined in a separate document
  ✗ May return false positives
  ✗ Cannot guarantee completeness

Graph approach:
  MATCH (r:Requirement {req_id: "REQ-SA-042"})
        -[:VERIFIED_BY]->(t:TestCase)
  RETURN t.tc_id
  ✓ Exact answer — every TC linked to this requirement
  ✓ Works even when TC and REQ are in different documents
  ✓ Guaranteed complete — no false positives
```

---

## 3. BGE vs Corporate LLM — Different Jobs

A common point of confusion: both BGE and the Corporate LLM are "AI models" —
but they do completely different things.

| | BGE Model | Corporate LLM |
|---|-----------|--------------|
| **Job** | Find relevant chunks | Understand and answer |
| **Input** | Raw text | Retrieved context + question |
| **Output** | A vector (numbers) | Human-readable answer |
| **Runs** | Locally on your machine | Your internal LLM server |
| **Data leaves network?** | Never | Only assembled context |
| **Used at** | Ingest time + query time | Query time only |

---

## 4. How All Three Work Together

The real power comes from combining all three components:

```
USER ASKS:
"Summarize uncovered P0 handover requirements for Verizon
 and explain why they matter"

                        ┌─────────────────────────────────┐
STEP 1 — Graph          │  Query Neo4j for exact list:    │
finds exact list        │  REQ-SA-042 (P0, no TC linked)  │
                        │  REQ-SA-051 (P0, no TC linked)  │
                        └─────────────────────────────────┘
                                        +
                        ┌─────────────────────────────────┐
STEP 2 — BGE            │  Find relevant doc sections:    │
finds context           │  "REQ-SA-042: The gNB shall     │
                        │   complete Xn handover in 50ms" │
                        │  "REQ-SA-051: AMF shall maintain │
                        │   session continuity during HO" │
                        └─────────────────────────────────┘
                                        ↓
                        ┌─────────────────────────────────┐
STEP 3 — LLM            │  "Verizon has 2 uncovered P0    │
synthesises answer      │  handover requirements:         │
                        │  REQ-SA-042 requires <50ms Xn   │
                        │  handover — no test case exists. │
                        │  REQ-SA-051 requires AMF session │
                        │  continuity — no test case...   │
                        │  These are critical because..." │
                        └─────────────────────────────────┘
```

**Graph gives precision. BGE gives context. LLM gives the answer.**

---

## 5. Summary

| Component | Answers | Cannot answer |
|-----------|---------|---------------|
| **BGE + Vector Search** | "Explain this concept", "Summarize this section", "What does this mean?" | Exact traceability, coverage gaps, cross-carrier counts |
| **Knowledge Graph** | "Which TCs cover this REQ?", "What is uncovered?", "Compare carriers" | Fuzzy/semantic questions, explanations |
| **Corporate LLM** | Synthesises both into a natural language answer | Retrieval — it only sees what graph + BGE give it |

Remove any one of the three and the system loses a major capability.
The combination is what makes it useful for 5G SA carrier requirements analysis.
