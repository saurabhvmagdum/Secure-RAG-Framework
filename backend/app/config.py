"""
Application Configuration
=========================

All configuration is loaded from environment variables via Pydantic BaseSettings.
No cloud SDK imports. No external network assumptions. All paths must resolve
within the air-gapped on-prem environment.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class AppEnvironment(str, Enum):
    """Deployment environment — always on-prem."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Core application settings."""

    app_name: str = Field(default="isro-rag-framework", description="Application name")
    app_env: AppEnvironment = Field(default=AppEnvironment.PRODUCTION)
    app_debug: bool = Field(default=False, description="Debug mode — NEVER enable in production")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_log_level: str = Field(default="INFO")
    app_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


class ModelSettings(BaseSettings):
    """On-prem model and embedding paths."""

    model_store_path: Path = Field(
        default=Path("/opt/isro/models"),
        description="Root directory for all model weights (on-prem only)",
    )
    embedding_store_path: Path = Field(
        default=Path("/opt/isro/embeddings"),
        description="Root directory for embedding model files (on-prem only)",
    )
    embedding_model_id: str = Field(default="isro-encoder-v2")
    llm_model_id: str = Field(default="isro-llm-v1")
    llm_max_tokens: int = Field(default=2048, ge=1)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_top_p: float = Field(default=0.9, ge=0.0, le=1.0)

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


class OpenSearchSettings(BaseSettings):
    """OpenSearch connection settings for BM25 lexical index."""

    opensearch_host: str = Field(default="opensearch")
    opensearch_port: int = Field(default=9200)
    opensearch_scheme: str = Field(default="https")
    opensearch_username: str = Field(default="admin")
    opensearch_password: str = Field(default="")
    opensearch_index_prefix: str = Field(default="isro_rag")
    opensearch_verify_certs: bool = Field(default=True)
    opensearch_ca_cert_path: Path = Field(
        default=Path("/opt/isro/certs/opensearch-ca.pem")
    )

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}

    @property
    def connection_url(self) -> str:
        return f"{self.opensearch_scheme}://{self.opensearch_host}:{self.opensearch_port}"


class QdrantSettings(BaseSettings):
    """Qdrant connection settings for semantic vector DB."""

    qdrant_host: str = Field(default="qdrant")
    qdrant_port: int = Field(default=6333)
    qdrant_grpc_port: int = Field(default=6334)
    qdrant_api_key: str = Field(default="")
    qdrant_collection_prefix: str = Field(default="isro_rag")
    qdrant_tls_enabled: bool = Field(default=True)
    qdrant_ca_cert_path: Path = Field(
        default=Path("/opt/isro/certs/qdrant-ca.pem")
    )

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


class Neo4jSettings(BaseSettings):
    """Neo4j connection settings for knowledge graph."""

    neo4j_uri: str = Field(default="bolt://neo4j:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")
    neo4j_database: str = Field(default="isro_rag")
    neo4j_encrypted: bool = Field(default=True)
    neo4j_ca_cert_path: Path = Field(
        default=Path("/opt/isro/certs/neo4j-ca.pem")
    )

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


class SecuritySettings(BaseSettings):
    """JWT and encryption settings."""

    jwt_secret_key: str = Field(default="CHANGE_ME")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=60, ge=1)
    auth_provider: str = Field(
        default="internal_jwt",
        description="Auth provider — 'internal_jwt' for Phase 1, 'ldap' future",
    )

    encryption_at_rest_algorithm: str = Field(default="AES-256-GCM")
    encryption_key_store_path: Path = Field(default=Path("/opt/isro/keys"))
    tls_cert_path: Path = Field(default=Path("/opt/isro/certs/server.crt"))
    tls_key_path: Path = Field(default=Path("/opt/isro/certs/server.key"))
    tls_ca_path: Path = Field(default=Path("/opt/isro/certs/ca.crt"))

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if v == "CHANGE_ME":
            import warnings

            warnings.warn(
                "JWT_SECRET_KEY is set to default 'CHANGE_ME'. "
                "This MUST be changed in production.",
                stacklevel=2,
            )
        return v


class GovernanceSettings(BaseSettings):
    """Verification and routing thresholds."""

    governance_default_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    governance_hard_block_below: float = Field(default=0.5, ge=0.0, le=1.0)
    governance_allow_partial: bool = Field(default=True)

    # Per-domain threshold overrides
    governance_procurement_threshold: float = Field(default=0.9)
    governance_telemetry_threshold: float = Field(default=0.85)
    governance_failure_analysis_threshold: float = Field(default=0.9)

    # Confidence score weights (must sum to 1.0)
    weight_relevance: float = Field(default=0.25)
    weight_coverage: float = Field(default=0.20)
    weight_similarity: float = Field(default=0.20)
    weight_consistency: float = Field(default=0.20)
    weight_domain_rules: float = Field(default=0.15)

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}

    @field_validator("weight_domain_rules")
    @classmethod
    def _validate_weights_sum(cls, v: float, info: Any) -> float:
        """Validate confidence weights sum to 1.0."""
        data = info.data
        total = (
            data.get("weight_relevance", 0.25)
            + data.get("weight_coverage", 0.20)
            + data.get("weight_similarity", 0.20)
            + data.get("weight_consistency", 0.20)
            + v
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Confidence weights must sum to 1.0, got {total:.6f}"
            )
        return v

    def get_domain_threshold(self, domain_tag: str) -> float:
        """Return threshold for a given domain tag."""
        overrides: dict[str, float] = {
            "procurement": self.governance_procurement_threshold,
            "telemetry": self.governance_telemetry_threshold,
            "failure_analysis": self.governance_failure_analysis_threshold,
        }
        return overrides.get(domain_tag, self.governance_default_threshold)


class AuditSettings(BaseSettings):
    """Audit logging configuration."""

    audit_log_path: Path = Field(default=Path("/var/log/isro-rag/audit"))
    audit_log_rotation: str = Field(default="daily")
    audit_log_retention_days: int = Field(default=365, ge=1)

    model_config = {"env_prefix": "", "env_file": ".env", "case_sensitive": False}


class Settings:
    """
    Aggregated settings container.

    Usage:
        settings = Settings()
        settings.app.app_name
        settings.model.model_store_path
        settings.opensearch.connection_url
    """

    def __init__(self) -> None:
        self.app = AppSettings()
        self.model = ModelSettings()
        self.opensearch = OpenSearchSettings()
        self.qdrant = QdrantSettings()
        self.neo4j = Neo4jSettings()
        self.security = SecuritySettings()
        self.governance = GovernanceSettings()
        self.audit = AuditSettings()


# Module-level singleton — import and use directly
settings = Settings()
