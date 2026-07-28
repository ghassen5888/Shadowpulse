"""Hybrid CTI extraction orchestration layer."""

from __future__ import annotations

import logging
from time import perf_counter

from ai.client import LLMClient
from ai.parser import clean_html_to_text
from ai.regex_engine import RegexEngine
from ai.schemas import ExtractedCTIPayload, LLMThreatIntelligence

LOGGER = logging.getLogger(__name__)


class HybridIntelligenceEngine:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()
        self.regex_engine = RegexEngine()

    def process_raw_html(self, raw_html: str, url: str) -> ExtractedCTIPayload:
        start = perf_counter()

        clean_text = clean_html_to_text(raw_html)
        regex_iocs = self.regex_engine.extract_all(clean_text)
        regex_ioc_count = sum(len(values) for values in regex_iocs.model_dump(mode="json").values())
        LOGGER.error("[REGEX ENGINE] source=%s extracted_iocs=%d", url, regex_ioc_count)

        llm_start = perf_counter()
        try:
            llm_intel = self.llm_client.extract_intelligence(clean_text)
        except Exception as exc:
            llm_latency_ms = (perf_counter() - llm_start) * 1000.0
            LOGGER.error(
                "[LLM CLIENT] source=%s failed latency_ms=%.1f error=%s",
                url,
                llm_latency_ms,
                exc,
            )
            llm_intel = LLMThreatIntelligence(summary="")

        elapsed_ms = (perf_counter() - start) * 1000.0
        raw_len = len(raw_html or "")
        clean_len = len(clean_text or "")
        reduction_ratio = 0.0 if raw_len == 0 else max((raw_len - clean_len) / raw_len, 0.0)

        return ExtractedCTIPayload(
            source_url=url,
            regex_iocs=regex_iocs,
            llm_intelligence=llm_intel,
            clean_text_length=clean_len,
            raw_html_length=raw_len,
            text_reduction_ratio=reduction_ratio,
            execution_latency_ms=elapsed_ms,
        )
