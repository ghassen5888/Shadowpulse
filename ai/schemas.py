"""Pydantic schemas for normalized CTI extraction payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EntityConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return value.strip()


class RegexIOCs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cves: List[str] = Field(default_factory=list)
    ips: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    sha256: List[str] = Field(default_factory=list)
    bitcoin_wallets: List[str] = Field(default_factory=list)
    onion_addresses: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)


class LLMThreatIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threat_actors: List[EntityConfidence] = Field(default_factory=list)
    malware_families: List[EntityConfidence] = Field(default_factory=list)
    victims: List[EntityConfidence] = Field(default_factory=list)
    target_industries: List[str] = Field(default_factory=list)
    target_countries: List[str] = Field(default_factory=list)
    attack_techniques: List[str] = Field(default_factory=list)
    summary: str = Field(default="LLM processing unavailable")


class ExtractedCTIPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    regex_iocs: RegexIOCs
    llm_intelligence: LLMThreatIntelligence
    clean_text_length: int = Field(ge=0)
    raw_html_length: int = Field(ge=0)
    text_reduction_ratio: float = Field(ge=0.0)
    execution_latency_ms: float = Field(ge=0.0)
