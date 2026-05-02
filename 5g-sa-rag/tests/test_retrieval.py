"""
tests/test_retrieval.py

Unit tests for the retrieval layer (router, assembler).
No external services required.
"""
import pytest
from retrieval.router import QueryRouter, RouteType, ContextAssembler


class TestQueryRouter:
    def setup_method(self):
        self.router = QueryRouter()

    def test_graph_route_for_req_id(self):
        assert self.router.classify("Which test cases cover REQ-SA-042?") == RouteType.GRAPH

    def test_graph_route_for_tc_id(self):
        assert self.router.classify("What does TC-SA-001 verify?") == RouteType.GRAPH

    def test_graph_route_for_coverage_gap(self):
        assert self.router.classify("Which requirements have no test cases?") == RouteType.GRAPH

    def test_graph_route_for_comparison(self):
        assert self.router.classify("Compare requirements across all carriers") == RouteType.GRAPH

    def test_graph_route_for_conflict(self):
        assert self.router.classify("Find conflicts between AT&T and Verizon") == RouteType.GRAPH

    def test_vector_route_for_summary(self):
        assert self.router.classify("Summarize the authentication section") == RouteType.VECTOR

    def test_vector_route_for_explanation(self):
        assert self.router.classify("What is PDU session establishment?") == RouteType.VECTOR

    def test_both_route_default(self):
        assert self.router.classify("Tell me about Verizon 5G requirements") == RouteType.BOTH

    def test_classify_returns_route_type(self):
        result = self.router.classify("some query")
        assert isinstance(result, RouteType)


class TestContextAssembler:
    def setup_method(self):
        self.assembler = ContextAssembler()

    def test_empty_returns_no_context_message(self):
        result = self.assembler.assemble({}, [])
        assert "No relevant context" in result

    def test_graph_results_formatted(self):
        result = self.assembler.assemble(
            {"requirements": [{"req_id": "REQ-SA-001", "priority": "P0"}]}, []
        )
        assert "STRUCTURED KNOWLEDGE GRAPH RESULTS" in result
        assert "REQ-SA-001" in result
        assert "P0" in result

    def test_empty_graph_result_shows_no_results(self):
        result = self.assembler.assemble({"coverage_gaps": []}, [])
        assert "No results found" in result

    def test_vector_chunks_formatted(self):
        chunks = [{"text": "The AMF shall authenticate UE.",
                   "metadata": {"doc_name": "vz_req", "carrier": "Verizon", "heading": "Auth"},
                   "score": 0.88}]
        result = self.assembler.assemble({}, chunks)
        assert "RELEVANT DOCUMENT SECTIONS" in result
        assert "Verizon" in result
        assert "0.88" in result

    def test_dedup_vector_chunks(self):
        same_chunk = {"text": "duplicate text",
                      "metadata": {"doc_name": "d", "carrier": "X", "heading": "S"}, "score": 0.9}
        result = self.assembler.assemble({}, [same_chunk, same_chunk])
        assert result.count("duplicate text") == 1

    def test_max_vector_chunks_cap(self):
        chunks = [
            {"text": f"chunk {i}", "metadata": {"doc_name": "d", "carrier": "X", "heading": "S"}, "score": 0.5}
            for i in range(20)
        ]
        result = self.assembler.assemble({}, chunks)
        assert result.count("chunk ") <= ContextAssembler.MAX_VECTOR_CHUNKS

    def test_combined_graph_and_vector(self):
        graph = {"tcs": [{"tc_id": "TC-001", "status": "Pass"}]}
        vec   = [{"text": "REQ content", "metadata": {"doc_name": "d", "carrier": "C", "heading": "S"}, "score": 0.7}]
        result = self.assembler.assemble(graph, vec)
        assert "TC-001" in result
        assert "REQ content" in result
