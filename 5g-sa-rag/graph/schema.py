"""
graph/schema.py

Neo4j node labels, relationship types, and schema constraints
for the 5G SA requirements knowledge graph.

Node Types:
  (:Document)         — source .docx file
  (:Carrier)          — Verizon, T-Mobile, AT&T, etc.
  (:Requirement)      — REQ-SA-001, REQ-QOS-003, etc.
  (:TestCase)         — TC-SA-001, etc.
  (:Feature)          — Handover, QoS, Authentication, etc.
  (:NREntity)         — AMF, SMF, UPF, gNB, etc.
  (:Section)          — a document section (links to chunks)

Relationship Types:
  (:Carrier)-[:HAS_REQUIREMENT]->(:Requirement)
  (:Requirement)-[:VERIFIED_BY]->(:TestCase)
  (:TestCase)-[:COVERS]->(:Requirement)          # inverse
  (:Requirement)-[:RELATES_TO]->(:Feature)
  (:TestCase)-[:RELATES_TO]->(:Feature)
  (:Requirement)-[:INVOLVES]->(:NREntity)
  (:TestCase)-[:INVOLVES]->(:NREntity)
  (:Document)-[:CONTAINS]->(:Section)
  (:Section)-[:HAS_REQUIREMENT]->(:Requirement)
  (:Section)-[:HAS_TEST_CASE]->(:TestCase)
  (:Requirement)-[:SAME_AS]->(:Requirement)      # cross-carrier equivalence
  (:Requirement)-[:CONFLICTS_WITH]->(:Requirement)
"""

SCHEMA_CONSTRAINTS = [
    # Uniqueness constraints
    "CREATE CONSTRAINT req_id IF NOT EXISTS FOR (r:Requirement) REQUIRE r.req_id IS UNIQUE",
    "CREATE CONSTRAINT tc_id  IF NOT EXISTS FOR (t:TestCase)    REQUIRE t.tc_id   IS UNIQUE",
    "CREATE CONSTRAINT carrier_name IF NOT EXISTS FOR (c:Carrier) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT doc_name IF NOT EXISTS FOR (d:Document) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT feature_name IF NOT EXISTS FOR (f:Feature) REQUIRE f.name IS UNIQUE",
    "CREATE CONSTRAINT nr_entity_name IF NOT EXISTS FOR (n:NREntity) REQUIRE n.name IS UNIQUE",

    # Indexes for frequent lookups
    "CREATE INDEX req_carrier IF NOT EXISTS FOR (r:Requirement) ON (r.carrier)",
    "CREATE INDEX req_priority IF NOT EXISTS FOR (r:Requirement) ON (r.priority)",
    "CREATE INDEX tc_status IF NOT EXISTS FOR (t:TestCase) ON (t.status)",
    "CREATE INDEX feature_name_idx IF NOT EXISTS FOR (f:Feature) ON (f.name)",
]
