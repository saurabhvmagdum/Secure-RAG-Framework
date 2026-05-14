"""
Graph Index Writer — Neo4j Adapter
=====================================

Extracts entities and relations from document chunks and writes them
to the Neo4j knowledge graph.
Governance checkpoint: indexing.graph_write

Features:
- Entity extraction from chunk text (rule-based NER)
- Relation extraction from co-occurring entities
- Node provenance tracking (doc_id, chunk_id, sensitivity)
- Classification-aware eligibility check
- Circuit breaker for Neo4j connectivity
- Audit event emission on every write
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.audit.logger import AuditLogger, FileAuditLogger
from app.audit.models import AuditAction, AuditDecision, AuditEvent
from app.core.correlation import get_correlation_id
from app.core.exceptions import IndexingError
from app.core.logging import get_logger
from app.governance.checkpoint import governance_checkpoint
from app.governance.classification import ClassificationEngine, DefaultClassificationEngine
from app.models.document import Chunk
from app.models.graph import GraphEdge, GraphEdgeProperties, GraphNode, GraphNodeProperties
from app.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)


# ── Rule-Based Entity Patterns ──────────────────────────────────────────────
# Governance-approved patterns for domain entity extraction.
# No ML-based NER — only explicit pattern matching for determinism.

ENTITY_PATTERNS: dict[str, list[str]] = {
    "MISSION": [
        r"\b(PSLV-C\d+)\b",
        r"\b(GSLV-MkII?I?-[A-Z]\d+)\b",
        r"\b(Chandrayaan-\d+)\b",
        r"\b(Mangalyaan(?:-\d+)?)\b",
        r"\b(Aditya-L\d+)\b",
        r"\b(Gaganyaan)\b",
        r"\b(INSAT-\d+[A-Z]*)\b",
        r"\b(IRS-\w+)\b",
    ],
    "COMPONENT": [
        r"\b(PS[1-4])\b",  # Solid stages
        r"\b(GS[1-3])\b",  # Strap-on stages
        r"\b(C25\s+engine)\b",
        r"\b(CE-\d+)\b",   # Cryogenic engines
        r"\b(Vikas\s+engine)\b",
        r"\b(S200\s+booster)\b",
        r"\b(L110\s+stage)\b",
    ],
    "SYSTEM": [
        r"\b(avionics\s+(?:system|subsystem|module))\b",
        r"\b(guidance\s+(?:system|computer))\b",
        r"\b(telemetry\s+(?:system|module|package))\b",
        r"\b(power\s+(?:system|subsystem|bus))\b",
        r"\b(thermal\s+(?:system|control|protection))\b",
        r"\b(propulsion\s+(?:system|module))\b",
        r"\b(navigation\s+(?:system|sensor|unit))\b",
    ],
    "PARAMETER": [
        r"\b(thrust)\b",
        r"\b(specific\s+impulse)\b",
        r"\b(burn\s+time)\b",
        r"\b(orbital\s+(?:velocity|altitude|inclination))\b",
        r"\b(apogee|perigee)\b",
        r"\b(mass\s+(?:flow\s+)?rate)\b",
    ],
    "ANOMALY": [
        r"\b(anomaly\s+\w+-\d+)\b",
        r"\b(failure\s+mode\s+\w+)\b",
        r"\b(deviation\s+report\s+\w+)\b",
    ],
    "FACILITY": [
        r"\b(SDSC[-\s]SHAR)\b",
        r"\b(Sriharikota)\b",
        r"\b(ISAC)\b",
        r"\b(VSSC)\b",
        r"\b(LPSC)\b",
        r"\b(ISITE)\b",
        r"\b(ISTRAC)\b",
    ],
}

# Relation templates for co-occurring entities
RELATION_TEMPLATES: list[tuple[str, str, str]] = [
    ("MISSION", "USES_COMPONENT", "COMPONENT"),
    ("MISSION", "HAS_SYSTEM", "SYSTEM"),
    ("COMPONENT", "HAS_PARAMETER", "PARAMETER"),
    ("SYSTEM", "DETECTED_ANOMALY", "ANOMALY"),
    ("MISSION", "LAUNCHED_FROM", "FACILITY"),
    ("COMPONENT", "PART_OF_SYSTEM", "SYSTEM"),
]


class ExtractedEntity:
    """An entity extracted from text."""

    def __init__(self, text: str, entity_type: str, start: int, end: int) -> None:
        self.text = text
        self.entity_type = entity_type
        self.start = start
        self.end = end

    def __repr__(self) -> str:
        return f"Entity({self.entity_type}: '{self.text}')"


@runtime_checkable
class GraphIndexWriter(Protocol):
    """Protocol for writing to the knowledge graph index."""

    def upsert_node(self, node: GraphNode) -> GraphNode:
        ...

    def upsert_edge(self, edge: GraphEdge) -> GraphEdge:
        ...

    def index_chunk(self, chunk: Chunk) -> tuple[list[GraphNode], list[GraphEdge]]:
        ...

    def delete_by_doc_id(self, doc_id: str) -> int:
        ...

    def health_check(self) -> bool:
        ...


class Neo4jGraphIndexWriter:
    """
    Neo4j adapter for knowledge graph indexing.

    Entity extraction strategy:
    - Rule-based pattern matching (governance-approved patterns only)
    - No ML-based NER for determinism and auditability
    - Entities: MISSION, COMPONENT, SYSTEM, PARAMETER, ANOMALY, FACILITY
    - Relations inferred from entity co-occurrence within chunks

    Node strategy:
    - Node ID: deterministic from entity_type + canonical_name
    - Properties include provenance (doc_id, chunk_id, sensitivity)
    - Merged on upsert (idempotent)

    Edge strategy:
    - Edge provenance: chunk_id, confidence, doc_id
    - Relations from co-occurring entities per templates
    """

    def __init__(
        self,
        neo4j_driver: Any | None = None,
        classification_engine: ClassificationEngine | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._driver = neo4j_driver  # None in Phase 2 skeleton
        self._classification = classification_engine or DefaultClassificationEngine()
        self._audit = audit_logger or FileAuditLogger()
        self._circuit_breaker = CircuitBreaker(
            service_name="neo4j",
            failure_threshold=5,
            recovery_timeout_seconds=30.0,
        )

    @governance_checkpoint(
        "indexing.graph_write", require_principal=False
    )
    def index_chunk(
        self, chunk: Chunk
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """
        Extract entities and relations from a chunk, write to Neo4j.

        Steps:
        1. Validate classification eligibility
        2. Extract entities via rule-based patterns
        3. Infer relations from entity co-occurrence
        4. Build GraphNode and GraphEdge objects
        5. Upsert to Neo4j
        6. Emit audit event
        """
        # 1. Classification eligibility
        if not self._classification.validate_index_eligibility(
            chunk.metadata.sensitivity_level, "graph"
        ):
            raise IndexingError(
                message=(
                    f"Chunk {chunk.chunk_id} not eligible for graph index "
                    f"at sensitivity {chunk.metadata.sensitivity_level.value}"
                ),
                context={"chunk_id": chunk.chunk_id},
            )

        # 2. Extract entities
        entities = self._extract_entities(chunk.text)

        if not entities:
            logger.debug(
                "graph_index_no_entities",
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
            )
            return [], []

        # 3. Build graph nodes
        nodes: list[GraphNode] = []
        for entity in entities:
            node_id = self._generate_node_id(entity.entity_type, entity.text)
            node = GraphNode(
                node_id=node_id,
                label=entity.entity_type,
                properties=GraphNodeProperties(
                    canonical_name=entity.text,
                    display_name=entity.text,
                    entity_type=entity.entity_type,
                    source_doc_ids=[chunk.doc_id],
                    source_chunk_ids=[chunk.chunk_id],
                    domain_tag=chunk.metadata.domain_tag.value,
                    sensitivity_level=chunk.metadata.sensitivity_level.value,
                ),
            )
            nodes.append(node)

        # 4. Infer and build edges
        edges = self._infer_relations(entities, chunk)

        # 5. Write to Neo4j
        for node in nodes:
            self._upsert_node_to_neo4j(node)

        for edge in edges:
            self._upsert_edge_to_neo4j(edge)

        # 6. Audit event
        self._emit_write_audit(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            nodes_created=len(nodes),
            edges_created=len(edges),
            sensitivity=chunk.metadata.sensitivity_level.value,
        )

        logger.info(
            "graph_index_write",
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            entities_extracted=len(entities),
            nodes_written=len(nodes),
            edges_written=len(edges),
        )

        return nodes, edges

    def upsert_node(self, node: GraphNode) -> GraphNode:
        """Upsert a single graph node."""
        self._upsert_node_to_neo4j(node)
        return node

    def upsert_edge(self, edge: GraphEdge) -> GraphEdge:
        """Upsert a single graph edge."""
        self._upsert_edge_to_neo4j(edge)
        return edge

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all nodes and edges derived from a document."""
        logger.info("graph_index_delete", doc_id=doc_id)

        if self._driver is None:
            return 0

        # TODO: Execute Cypher: MATCH (n) WHERE doc_id IN n.source_doc_ids
        #       DETACH DELETE n
        return 0

    def health_check(self) -> bool:
        """Check Neo4j connectivity."""
        if self._driver is None:
            return False
        try:
            return self._circuit_breaker.call(
                lambda: self._driver.verify_connectivity() is None
            )
        except Exception:
            return False

    def _extract_entities(self, text: str) -> list[ExtractedEntity]:
        """
        Extract entities from text using governance-approved patterns.

        Deterministic — same text always produces same entities.
        """
        entities: list[ExtractedEntity] = []
        seen: set[tuple[str, str]] = set()

        for entity_type, patterns in ENTITY_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    canonical = match.group(1).strip()
                    key = (entity_type, canonical.lower())

                    if key not in seen:
                        seen.add(key)
                        entities.append(
                            ExtractedEntity(
                                text=canonical,
                                entity_type=entity_type,
                                start=match.start(),
                                end=match.end(),
                            )
                        )

        return entities

    def _infer_relations(
        self,
        entities: list[ExtractedEntity],
        chunk: Chunk,
    ) -> list[GraphEdge]:
        """
        Infer relations from entity co-occurrence within the same chunk.

        Uses governance-approved relation templates.
        """
        edges: list[GraphEdge] = []

        # Group entities by type
        by_type: dict[str, list[ExtractedEntity]] = {}
        for e in entities:
            by_type.setdefault(e.entity_type, []).append(e)

        for source_type, relation, target_type in RELATION_TEMPLATES:
            sources = by_type.get(source_type, [])
            targets = by_type.get(target_type, [])

            for source in sources:
                for target in targets:
                    source_id = self._generate_node_id(source.entity_type, source.text)
                    target_id = self._generate_node_id(target.entity_type, target.text)

                    edge = GraphEdge(
                        edge_id=self._generate_edge_id(source_id, relation, target_id),
                        source_node_id=source_id,
                        target_node_id=target_id,
                        relation_type=relation,
                        properties=GraphEdgeProperties(
                            confidence=0.8,  # Pattern-based extraction confidence
                            source_chunk_id=chunk.chunk_id,
                            source_doc_id=chunk.doc_id,
                            extraction_method="rule_based_cooccurrence",
                        ),
                    )
                    edges.append(edge)

        return edges

    def _upsert_node_to_neo4j(self, node: GraphNode) -> None:
        """Upsert a node to Neo4j."""
        if self._driver is None:
            logger.debug(
                "graph_node_dry_run",
                node_id=node.node_id,
                label=node.label,
            )
            return

        try:
            cypher = """
            MERGE (n:{label} {{node_id: $node_id}})
            SET n += $properties
            """.format(label=node.label)

            properties = {
                "node_id": node.node_id,
                "canonical_name": node.properties.canonical_name,
                "display_name": node.properties.display_name,
                "entity_type": node.properties.entity_type,
                "domain_tag": node.properties.domain_tag,
                "sensitivity_level": node.properties.sensitivity_level,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            self._circuit_breaker.call(
                self._execute_cypher, cypher, {"node_id": node.node_id, "properties": properties}
            )

        except Exception as exc:
            raise IndexingError(
                message=f"Neo4j node upsert failed: {exc}",
                context={"node_id": node.node_id},
            ) from exc

    def _upsert_edge_to_neo4j(self, edge: GraphEdge) -> None:
        """Upsert an edge to Neo4j."""
        if self._driver is None:
            logger.debug(
                "graph_edge_dry_run",
                edge_id=edge.edge_id,
                relation=edge.relation_type,
            )
            return

        try:
            cypher = """
            MATCH (a {{node_id: $source_id}})
            MATCH (b {{node_id: $target_id}})
            MERGE (a)-[r:{relation} {{edge_id: $edge_id}}]->(b)
            SET r += $properties
            """.format(relation=edge.relation_type)

            properties = {
                "edge_id": edge.edge_id,
                "confidence": edge.properties.confidence,
                "source_chunk_id": edge.properties.source_chunk_id,
                "source_doc_id": edge.properties.source_doc_id,
                "extraction_method": edge.properties.extraction_method,
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            self._circuit_breaker.call(
                self._execute_cypher,
                cypher,
                {
                    "source_id": edge.source_node_id,
                    "target_id": edge.target_node_id,
                    "edge_id": edge.edge_id,
                    "properties": properties,
                },
            )

        except Exception as exc:
            raise IndexingError(
                message=f"Neo4j edge upsert failed: {exc}",
                context={"edge_id": edge.edge_id},
            ) from exc

    def _execute_cypher(self, query: str, params: dict[str, Any]) -> Any:
        """Execute a Cypher query against Neo4j."""
        with self._driver.session() as session:
            return session.run(query, params)

    @staticmethod
    def _generate_node_id(entity_type: str, canonical_name: str) -> str:
        """Generate deterministic node ID from entity type + name."""
        seed = f"{entity_type}:{canonical_name.lower().strip()}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))

    @staticmethod
    def _generate_edge_id(source_id: str, relation: str, target_id: str) -> str:
        """Generate deterministic edge ID from source + relation + target."""
        seed = f"{source_id}:{relation}:{target_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))

    def _emit_write_audit(
        self,
        chunk_id: str,
        doc_id: str,
        nodes_created: int,
        edges_created: int,
        sensitivity: str,
    ) -> None:
        """Emit audit event for graph index write."""
        try:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                principal_id="indexing-service",
                principal_type="SERVICE",
                action=AuditAction.INDEX_WRITE,
                resource="INDEX:GRAPH",
                request_id=get_correlation_id(),
                decision=AuditDecision.ALLOW,
                metadata={
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "index_type": "graph",
                    "nodes_created": nodes_created,
                    "edges_created": edges_created,
                    "sensitivity": sensitivity,
                },
            )
            self._audit.log_event(event)
        except Exception as exc:
            logger.error("graph_audit_failed", error=str(exc))
