"""
graph/queries.py

Pre-built Cypher query library for common 5G SA graph queries.
All queries return plain Python dicts — the LLM layer formats them.
"""
from __future__ import annotations
from graph.builder import Neo4jClient


class GraphQueryLibrary:
    def __init__(self, client: Neo4jClient):
        self.client = client

    # ── Requirement queries ───────────────────────────────────────────────────

    def get_requirements_for_carrier(self, carrier: str) -> list[dict]:
        """All requirements owned by a specific carrier."""
        return self.client.run("""
            MATCH (c:Carrier {name: $carrier})-[:HAS_REQUIREMENT]->(r:Requirement)
            RETURN r.req_id AS req_id, r.priority AS priority,
                   r.section_heading AS section
            ORDER BY r.req_id
        """, carrier=carrier)

    def get_test_cases_for_requirement(self, req_id: str) -> list[dict]:
        """All test cases that verify a requirement."""
        return self.client.run("""
            MATCH (r:Requirement {req_id: $req_id})-[:VERIFIED_BY]->(t:TestCase)
            RETURN t.tc_id AS tc_id, t.carrier AS carrier,
                   t.status AS status, t.section_heading AS section
        """, req_id=req_id)

    def get_requirements_for_test_case(self, tc_id: str) -> list[dict]:
        """All requirements covered by a test case."""
        return self.client.run("""
            MATCH (t:TestCase {tc_id: $tc_id})-[:COVERS]->(r:Requirement)
            RETURN r.req_id AS req_id, r.carrier AS carrier,
                   r.priority AS priority
        """, tc_id=tc_id)

    def get_uncovered_requirements(self, carrier: str = None) -> list[dict]:
        """Requirements with no associated test cases — coverage gaps."""
        if carrier:
            return self.client.run("""
                MATCH (r:Requirement)
                WHERE r.carrier = $carrier
                  AND NOT (r)-[:VERIFIED_BY]->(:TestCase)
                RETURN r.req_id AS req_id, r.carrier AS carrier,
                       r.priority AS priority, r.section_heading AS section
                ORDER BY r.priority, r.req_id
            """, carrier=carrier)
        return self.client.run("""
            MATCH (r:Requirement)
            WHERE NOT (r)-[:VERIFIED_BY]->(:TestCase)
            RETURN r.req_id AS req_id, r.carrier AS carrier,
                   r.priority AS priority, r.section_heading AS section
            ORDER BY r.carrier, r.priority, r.req_id
        """)

    def get_requirements_by_feature(self, feature: str,
                                     carrier: str = None) -> list[dict]:
        """Requirements related to a specific feature (e.g. 'Handover')."""
        if carrier:
            return self.client.run("""
                MATCH (r:Requirement)-[:RELATES_TO]->(f:Feature {name: $feature})
                WHERE r.carrier = $carrier
                RETURN r.req_id AS req_id, r.carrier AS carrier,
                       r.priority AS priority
                ORDER BY r.req_id
            """, feature=feature, carrier=carrier)
        return self.client.run("""
            MATCH (r:Requirement)-[:RELATES_TO]->(f:Feature {name: $feature})
            RETURN r.req_id AS req_id, r.carrier AS carrier,
                   r.priority AS priority
            ORDER BY r.carrier, r.req_id
        """, feature=feature)

    # ── Cross-carrier comparison ──────────────────────────────────────────────

    def compare_feature_coverage_across_carriers(self, feature: str) -> list[dict]:
        """How many requirements + test cases each carrier has for a feature."""
        return self.client.run("""
            MATCH (c:Carrier)
            OPTIONAL MATCH (c)-[:HAS_REQUIREMENT]->(r:Requirement)-[:RELATES_TO]->(f:Feature {name: $feature})
            OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:TestCase)
            RETURN c.name AS carrier,
                   count(DISTINCT r) AS requirement_count,
                   count(DISTINCT t) AS test_case_count
            ORDER BY c.name
        """, feature=feature)

    def get_all_carriers(self) -> list[str]:
        rows = self.client.run("MATCH (c:Carrier) RETURN c.name AS name ORDER BY c.name")
        return [r["name"] for r in rows]

    def get_coverage_summary(self) -> list[dict]:
        """High-level coverage stats per carrier."""
        return self.client.run("""
            MATCH (c:Carrier)
            OPTIONAL MATCH (c)-[:HAS_REQUIREMENT]->(r:Requirement)
            OPTIONAL MATCH (r)-[:VERIFIED_BY]->(t:TestCase)
            RETURN c.name AS carrier,
                   count(DISTINCT r) AS total_requirements,
                   count(DISTINCT t) AS covered_requirements,
                   count(DISTINCT r) - count(DISTINCT t) AS gap
            ORDER BY gap DESC
        """)

    # ── Conflict detection ────────────────────────────────────────────────────

    def find_feature_conflicts(self) -> list[dict]:
        """
        Carriers that have requirements for the same feature
        but different counts — potential conflict signal.
        """
        return self.client.run("""
            MATCH (f:Feature)<-[:RELATES_TO]-(r:Requirement)
            WITH f.name AS feature, r.carrier AS carrier, count(r) AS req_count
            WITH feature, collect({carrier: carrier, count: req_count}) AS carrier_data
            WHERE size(carrier_data) > 1
            RETURN feature, carrier_data
            ORDER BY feature
        """)

    # ── NR Entity queries ─────────────────────────────────────────────────────

    def get_requirements_involving_entity(self, nr_entity: str) -> list[dict]:
        """All requirements that involve a specific NR entity (AMF, SMF, etc.)."""
        return self.client.run("""
            MATCH (r:Requirement)-[:INVOLVES]->(n:NREntity {name: $name})
            RETURN r.req_id AS req_id, r.carrier AS carrier,
                   r.priority AS priority, r.section_heading AS section
            ORDER BY r.carrier, r.req_id
        """, name=nr_entity)
