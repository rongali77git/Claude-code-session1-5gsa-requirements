"""
retrieval/router.py

Classifies an incoming query and decides which retrievers to invoke:
  - "graph"  → structured relationship queries (traceability, coverage)
  - "vector" → semantic similarity search
  - "both"   → hybrid (most analytical queries)
"""
from __future__ import annotations

import re
from enum import Enum


class RouteType(str, Enum):
    GRAPH  = "graph"
    VECTOR = "vector"
    BOTH   = "both"


# Signals that strongly suggest a graph query
GRAPH_SIGNALS = [
    r"\b(which|what|list|find|show)\b.{0,40}\b(test cases?|TCs?)\b.{0,40}\b(cover|verify|for|related to)\b",
    r"\b(which|what|list)\b.{0,40}\b(requirements?|REQs?)\b.{0,40}\b(have no|without|missing|uncovered|no test)\b",
    r"\bREQ[-_][A-Z0-9_-]+\b",
    r"\bTC[-_][A-Z0-9_-]+\b",
    r"\b(coverage|gap|traceability|trace matrix)\b",
    r"\b(compare|comparison|across carriers?|all carriers?)\b",
    r"\b(conflict|conflicts|contradicts?)\b",
    r"\b(priority|P0|P1|critical|mandatory)\b.{0,30}\b(requirements?)\b",
]

# Signals that suggest a pure vector/semantic query
VECTOR_SIGNALS = [
    r"\b(summarize|summary|explain|describe|what is|how does|overview)\b",
    r"\b(document|section|paragraph|chapter)\b",
    r"\b(similar to|like|related to|about)\b.{0,40}\b(concept|topic|area)\b",
]


class QueryRouter:

    def classify(self, query: str) -> RouteType:
        q = query.lower()

        graph_score  = sum(1 for p in GRAPH_SIGNALS  if re.search(p, q, re.IGNORECASE))
        vector_score = sum(1 for p in VECTOR_SIGNALS if re.search(p, q, re.IGNORECASE))

        if graph_score > 0 and vector_score == 0:
            return RouteType.GRAPH
        if vector_score > 0 and graph_score == 0:
            return RouteType.VECTOR
        return RouteType.BOTH  # default: hybrid gives best results


# ─────────────────────────────────────────────────────────────────────────────
#  retrieval/graph_retriever.py
# ─────────────────────────────────────────────────────────────────────────────

import re as _re
from graph.queries import GraphQueryLibrary
from ingestion.entity_extractor import EntityExtractor, REQ_ID_PATTERN, TC_ID_PATTERN, FEATURE_PATTERNS
from ingestion.parser import CARRIER_PATTERNS


class GraphRetriever:
    def __init__(self, query_lib: GraphQueryLibrary):
        self.lib       = query_lib
        self.extractor = EntityExtractor()

    def retrieve(self, query: str) -> dict:
        """
        Run targeted graph queries based on entities found in the query.
        Returns a dict of labelled result sets.
        """
        results = {}
        q_upper = query.upper()

        # Find explicit IDs in query
        req_ids = REQ_ID_PATTERN.findall(q_upper)
        tc_ids  = TC_ID_PATTERN.findall(q_upper)

        # Find carrier mentions
        carrier = None
        for name, pattern in CARRIER_PATTERNS.items():
            if _re.search(pattern, query, _re.IGNORECASE):
                carrier = name
                break

        # Find feature mentions
        feature = None
        for feat_name, pattern in FEATURE_PATTERNS.items():
            if _re.search(pattern, query, _re.IGNORECASE):
                feature = feat_name
                break

        # REQ-specific queries
        for req_id in req_ids:
            results[f"test_cases_for_{req_id}"] = \
                self.lib.get_test_cases_for_requirement(req_id)

        # TC-specific queries
        for tc_id in tc_ids:
            results[f"requirements_for_{tc_id}"] = \
                self.lib.get_requirements_for_test_case(tc_id)

        # Coverage gap
        if _re.search(r"\b(gap|uncovered|no test|missing test)\b", query, _re.IGNORECASE):
            results["coverage_gaps"] = self.lib.get_uncovered_requirements(carrier)

        # Carrier requirements
        if carrier and not req_ids:
            results[f"requirements_{carrier}"] = \
                self.lib.get_requirements_for_carrier(carrier)

        # Feature queries
        if feature:
            if carrier:
                results[f"requirements_{feature}_{carrier}"] = \
                    self.lib.get_requirements_by_feature(feature, carrier)
            else:
                results[f"requirements_{feature}"] = \
                    self.lib.get_requirements_by_feature(feature)
                results[f"carrier_comparison_{feature}"] = \
                    self.lib.compare_feature_coverage_across_carriers(feature)

        # Cross-carrier comparison
        if _re.search(r"\b(compare|comparison|across|all carriers?)\b", query, _re.IGNORECASE):
            results["coverage_summary"] = self.lib.get_coverage_summary()

        # Conflict detection
        if _re.search(r"\b(conflict|contradict)\b", query, _re.IGNORECASE):
            results["potential_conflicts"] = self.lib.find_feature_conflicts()

        return results


# ─────────────────────────────────────────────────────────────────────────────
#  retrieval/assembler.py
# ─────────────────────────────────────────────────────────────────────────────

import json as _json


class ContextAssembler:
    """
    Merges graph results + vector chunks into a clean context string
    for the corporate LLM.
    """

    MAX_VECTOR_CHUNKS = 6
    MAX_GRAPH_ROWS    = 50  # cap table rows to avoid token explosion

    def assemble(self, graph_results: dict, vector_chunks: list[dict]) -> str:
        parts: list[str] = []

        # ── Graph structured facts ────────────────────────────────────────────
        if graph_results:
            parts.append("=== STRUCTURED KNOWLEDGE GRAPH RESULTS ===")
            for label, rows in graph_results.items():
                if not rows:
                    parts.append(f"\n[{label}]: No results found.")
                    continue
                parts.append(f"\n[{label}] ({len(rows)} records):")
                for row in rows[: self.MAX_GRAPH_ROWS]:
                    parts.append("  " + " | ".join(f"{k}: {v}" for k, v in row.items()))
                if len(rows) > self.MAX_GRAPH_ROWS:
                    parts.append(f"  ... and {len(rows) - self.MAX_GRAPH_ROWS} more rows (truncated)")

        # ── Vector semantic chunks ────────────────────────────────────────────
        if vector_chunks:
            parts.append("\n=== RELEVANT DOCUMENT SECTIONS ===")
            seen = set()
            count = 0
            for chunk in vector_chunks:
                if count >= self.MAX_VECTOR_CHUNKS:
                    break
                text = chunk["text"]
                if text in seen:
                    continue
                seen.add(text)
                meta = chunk.get("metadata", {})
                score = chunk.get("score", 0)
                parts.append(
                    f"\n[Source: {meta.get('doc_name','?')} | "
                    f"Carrier: {meta.get('carrier','?')} | "
                    f"Section: {meta.get('heading','?')} | "
                    f"Score: {score:.2f}]\n{text}"
                )
                count += 1

        if not parts:
            return "No relevant context found in documents or knowledge graph."

        return "\n".join(parts)
