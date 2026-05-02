"""
graph/builder.py

Populates the Neo4j knowledge graph from parsed + extracted document data.
"""
from __future__ import annotations

import structlog
from neo4j import GraphDatabase, Driver

from config.settings import settings
from graph.schema import SCHEMA_CONSTRAINTS
from ingestion.parser import ParsedDocument, DocSection
from ingestion.entity_extractor import EntityExtractor, ExtractedEntities

log = structlog.get_logger()


class Neo4jClient:
    def __init__(self):
        self._driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._db = settings.neo4j_database

    def close(self):
        self._driver.close()

    def run(self, query: str, **params):
        with self._driver.session(database=self._db) as session:
            return session.run(query, **params).data()

    def apply_schema(self):
        for constraint in SCHEMA_CONSTRAINTS:
            try:
                self.run(constraint)
            except Exception as e:
                log.warning("schema_constraint_skip", constraint=constraint[:60], error=str(e))
        log.info("neo4j_schema_applied")

    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class GraphBuilder:
    """
    Builds the knowledge graph from parsed documents.

    Call order:
      1. apply_schema()
      2. ingest_document(parsed_doc)   ← repeat for each doc
    """

    def __init__(self, client: Neo4jClient):
        self.client    = client
        self.extractor = EntityExtractor()

    def ingest_document(self, doc: ParsedDocument):
        log.info("graph_ingest_start", doc=doc.doc_name, carrier=doc.carrier)
        self._upsert_document(doc)
        self._upsert_carrier(doc.carrier)
        for idx, section in enumerate(doc.sections):
            self._ingest_section(doc, section, idx)
        log.info("graph_ingest_done", doc=doc.doc_name)

    # ── Node upserts ──────────────────────────────────────────────────────────

    def _upsert_document(self, doc: ParsedDocument):
        self.client.run("""
            MERGE (d:Document {name: $name})
            SET d.file_path = $file_path,
                d.doc_type  = $doc_type,
                d.carrier   = $carrier
        """, name=doc.doc_name, file_path=doc.file_path,
             doc_type=doc.doc_type, carrier=doc.carrier)

    def _upsert_carrier(self, carrier: str):
        self.client.run("""
            MERGE (c:Carrier {name: $name})
        """, name=carrier)

    def _upsert_requirement(self, req_id: str, carrier: str,
                             section_heading: str, priority: str = "Unknown"):
        self.client.run("""
            MERGE (r:Requirement {req_id: $req_id})
            SET r.carrier          = $carrier,
                r.section_heading  = $section_heading,
                r.priority         = $priority
        """, req_id=req_id, carrier=carrier,
             section_heading=section_heading, priority=priority)

        # Link to carrier
        self.client.run("""
            MATCH (c:Carrier {name: $carrier}), (r:Requirement {req_id: $req_id})
            MERGE (c)-[:HAS_REQUIREMENT]->(r)
        """, carrier=carrier, req_id=req_id)

    def _upsert_test_case(self, tc_id: str, carrier: str,
                           section_heading: str):
        self.client.run("""
            MERGE (t:TestCase {tc_id: $tc_id})
            SET t.carrier         = $carrier,
                t.section_heading = $section_heading,
                t.status          = coalesce(t.status, 'Not Run')
        """, tc_id=tc_id, carrier=carrier, section_heading=section_heading)

        self.client.run("""
            MATCH (c:Carrier {name: $carrier}), (t:TestCase {tc_id: $tc_id})
            MERGE (c)-[:HAS_TEST_CASE]->(t)
        """, carrier=carrier, tc_id=tc_id)

    def _upsert_feature(self, feature: str):
        self.client.run("""
            MERGE (f:Feature {name: $name})
        """, name=feature)

    def _upsert_nr_entity(self, entity: str):
        self.client.run("""
            MERGE (n:NREntity {name: $name})
        """, name=entity)

    # ── Section ingestion ─────────────────────────────────────────────────────

    def _ingest_section(self, doc: ParsedDocument, section: DocSection, idx: int):
        section_id = f"{doc.doc_name}__sec{idx}"

        # Create section node
        self.client.run("""
            MERGE (s:Section {section_id: $section_id})
            SET s.doc_name    = $doc_name,
                s.heading     = $heading,
                s.carrier     = $carrier,
                s.doc_type    = $doc_type
        """, section_id=section_id, doc_name=doc.doc_name,
             heading=section.heading, carrier=doc.carrier, doc_type=doc.doc_type)

        # Link section → document
        self.client.run("""
            MATCH (d:Document {name: $doc_name}), (s:Section {section_id: $section_id})
            MERGE (d)-[:CONTAINS]->(s)
        """, doc_name=doc.doc_name, section_id=section_id)

        # Extract entities from section text
        full_text = section.content
        for table in section.tables:
            full_text += "\n" + " ".join(cell for row in table for cell in row)

        entities: ExtractedEntities = self.extractor.extract(full_text)
        links = self.extractor.extract_req_to_tc_links(full_text)

        # Priority — take first found in section
        priority = entities.priorities[0] if entities.priorities else "Unknown"

        # Upsert requirements
        for req_id in set(entities.req_ids):
            self._upsert_requirement(req_id, doc.carrier, section.heading, priority)
            self.client.run("""
                MATCH (s:Section {section_id: $sid}), (r:Requirement {req_id: $req_id})
                MERGE (s)-[:HAS_REQUIREMENT]->(r)
            """, sid=section_id, req_id=req_id)

        # Upsert test cases
        for tc_id in set(entities.tc_ids):
            self._upsert_test_case(tc_id, doc.carrier, section.heading)
            self.client.run("""
                MATCH (s:Section {section_id: $sid}), (t:TestCase {tc_id: $tc_id})
                MERGE (s)-[:HAS_TEST_CASE]->(t)
            """, sid=section_id, tc_id=tc_id)

        # Explicit REQ → TC links
        for req_id, tc_id in links:
            if req_id in entities.req_ids and tc_id in entities.tc_ids:
                self.client.run("""
                    MATCH (r:Requirement {req_id: $req_id}), (t:TestCase {tc_id: $tc_id})
                    MERGE (r)-[:VERIFIED_BY]->(t)
                    MERGE (t)-[:COVERS]->(r)
                """, req_id=req_id, tc_id=tc_id)

        # Features
        for feature in set(entities.features):
            self._upsert_feature(feature)
            for req_id in set(entities.req_ids):
                self.client.run("""
                    MATCH (r:Requirement {req_id: $req_id}), (f:Feature {name: $feature})
                    MERGE (r)-[:RELATES_TO]->(f)
                """, req_id=req_id, feature=feature)
            for tc_id in set(entities.tc_ids):
                self.client.run("""
                    MATCH (t:TestCase {tc_id: $tc_id}), (f:Feature {name: $feature})
                    MERGE (t)-[:RELATES_TO]->(f)
                """, tc_id=tc_id, feature=feature)

        # NR Entities
        for nr_ent in set(entities.nr_entities):
            self._upsert_nr_entity(nr_ent)
            for req_id in set(entities.req_ids):
                self.client.run("""
                    MATCH (r:Requirement {req_id: $req_id}), (n:NREntity {name: $name})
                    MERGE (r)-[:INVOLVES]->(n)
                """, req_id=req_id, name=nr_ent)
