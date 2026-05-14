"""
Graph Retriever Protocol & Adapter
==================================

Entity-relationship traversal retrieval from Neo4j.
Executes graph path queries, neighborhood expansion, and rule-based
traversals under RBAC constraints.

Phase 3: Implements Neo4jGraphRetriever adapter.
Extracts entities out of queries, queries Neo4j for neighborhoods,
and packages paths back into EvidenceChunks.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import RetrievalError
from app.core.logging import get_logger
from app.models.auth import Principal
from app.models.evidence import EvidenceChunk, IndexType
from app.models.metadata import DomainTag, SensitivityLevel, DocumentMetadata
from app.utils.circuit_breaker import CircuitBreaker
from app.indexing.graph import ENTITY_PATTERNS  # Reuse definitions from Phase 2 Graph Writer

logger = get_logger(__name__)


@runtime_checkable
class GraphRetriever(Protocol):
    """
    Protocol for knowledge graph retrieval.
    """

    def retrieve(
        self,
        query: str,
        principal: Principal,
        top_k: int = 20,
        max_hops: int = 2,
        domain_filter: list[str] | None = None,
        max_sensitivity: str | None = None,
    ) -> list[EvidenceChunk]:
        """
        Retrieve evidence via graph traversal.
        """
        ...


class Neo4jGraphRetriever:
    """
    Neo4j adapter for Graph retrieval.

    Extracts keywords mapping to known entities via regex (same as ingestion),
    runs Cypher to traverse X hops, filters nodes based on RBAC, and surfaces
    resulting relations as synthesized text evidence.
    """

    def __init__(self, neo4j_driver: Any | None = None) -> None:
        self._driver = neo4j_driver
        self._circuit_breaker = CircuitBreaker(
            service_name="neo4j_retrieval",
            failure_threshold=3,
            recovery_timeout_seconds=30.0,
        )

    def retrieve(
        self,
        query: str,
        principal: Principal,
        top_k: int = 20,
        max_hops: int = 2,
        domain_filter: list[str] | None = None,
        max_sensitivity: str | None = None,
    ) -> list[EvidenceChunk]:
        
        logger.info(
            "graph_retrieval_started",
            principal_id=principal.principal_id,
            top_k=top_k,
            max_hops=max_hops,
        )

        entities = self._extract_query_entities(query)
        if not entities:
            logger.debug("graph_retriever_no_entities_found", query=query)
            return []

        if self._driver is None:
            # Dry-run stub
            logger.debug("graph_retriever_dry_run_stub", entities=entities)
            return []

        try:
            return self._circuit_breaker.call(
                self._execute_traversal, 
                entities, 
                top_k, 
                max_hops, 
                domain_filter, 
                max_sensitivity
            )
        except Exception as exc:
            logger.error("graph_retrieval_failed", error=str(exc))
            raise RetrievalError(
                message=f"Neo4j retrieval failed: {exc}",
                index_type="graph",
            ) from exc

    def _extract_query_entities(self, query: str) -> list[str]:
        """
        Extract canonical entity names from query text using exact match rule-based mapping.
        """
        matched_entities = set()
        for patterns in ENTITY_PATTERNS.values():
            for pattern in patterns:
                for match in re.finditer(pattern, query, re.IGNORECASE):
                    # Canonical names
                    matched_entities.add(match.group(1).strip())
        
        return list(matched_entities)

    def _execute_traversal(
        self,
        entity_names: list[str],
        top_k: int,
        max_hops: int,
        domain_filter: list[str] | None,
        max_sensitivity: str | None,
    ) -> list[EvidenceChunk]:
        """
        Executes a Cypher query bounding traversal to allowed max sensitivity. 
        """
        # The schema uses Node { canonical_name }.
        # Cypher:
        # MATCH path = (n)-[*1..2]-(m) 
        # WHERE n.canonical_name IN $entity_names
        #  AND n.sensitivity_level IN $allowed_sensitivities
        #  AND m.sensitivity_level IN $allowed_sensitivities
        # RETURN path LIMIT $top_k

        allowed_sensitivities = self._resolve_allowed_sensitivities(max_sensitivity) if max_sensitivity else []

        cypher_query = f"""
        MATCH path = (n)-[*1..{max_hops}]-(m)
        WHERE n.canonical_name IN $entity_names
        """
        
        # We append RBAC constraints to the WHERE clause to fail-safe bounds
        if allowed_sensitivities:
            cypher_query += " AND n.sensitivity_level IN $allowed_sens AND m.sensitivity_level IN $allowed_sens"
        
        if domain_filter:
            cypher_query += " AND n.domain_tag IN $domain_filter AND m.domain_tag IN $domain_filter"

        cypher_query += "\nRETURN path LIMIT $top_k"

        params = {
            "entity_names": entity_names,
            "top_k": top_k,
            "allowed_sens": allowed_sensitivities,
            "domain_filter": domain_filter or [],
        }

        with self._driver.session() as session:
            records = session.run(cypher_query, params)
            
            results: list[EvidenceChunk] = []
            for rank, record in enumerate(records):
                # record["path"] is a Neo4j Path object mapping
                path = record["path"]
                
                # Synthesize text from the graph edges:
                # e.g., "PSLV-C60 (MISSION) USES_COMPONENT S200 booster (COMPONENT)."
                sentences = []
                for relationship in path.relationships:
                    start_node = path.nodes[0] # simplification for mock map
                    end_node = path.nodes[-1]
                    rel_type = relationship.type
                    sentences.append(
                        f"{start_node.get('canonical_name', 'Unknown')} "
                        f"{rel_type} "
                        f"{end_node.get('canonical_name', 'Unknown')}."
                    )
                
                text_chunk = " ".join(sentences)

                # Source tracing
                final_node = path.nodes[-1]
                doc_id = final_node.get("source_doc_ids", ["unknown_target"])[0]
                chunk_id = final_node.get("source_chunk_ids", ["unknown_target"])[0]
                
                metadata_dict = {
                    "domain_tag": DomainTag(final_node.get("domain_tag", "general")),
                    "sensitivity_level": SensitivityLevel(final_node.get("sensitivity_level", "PUBLIC")),
                    "version": final_node.get("version", "1.0"),
                    "origin": final_node.get("origin", "graph_traversal"),
                }

                chunk = EvidenceChunk(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    text=text_chunk,
                    rank=rank,
                    index_type=IndexType.GRAPH,
                    score=1.0 - (0.1 * rank), # Naive synthetic score for subgraph relevance
                    section_path="graph_expansion",
                    metadata=DocumentMetadata(**metadata_dict),
                )
                results.append(chunk)

            return results

    def _resolve_allowed_sensitivities(self, max_sensitivity: str) -> list[str]:
        try:
            target = SensitivityLevel(max_sensitivity)
            return [
                lvl.value for lvl in SensitivityLevel 
                if lvl.numeric_level <= target.numeric_level
            ]
        except ValueError:
            return [SensitivityLevel.PUBLIC.value]
