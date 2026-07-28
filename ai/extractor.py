"""Hybrid CTI extraction orchestration layer."""

from __future__ import annotations

import logging
from time import perf_counter
import traceback

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
        raw_len = len(raw_html or "")
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [EXTRACTOR] Starting IOC extraction source=%s raw_html_chars=%d",
            url,
            raw_len,
        )

        clean_text = clean_html_to_text(raw_html)
        clean_len = len(clean_text or "")
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [EXTRACTOR] Parser output source=%s raw_html_chars=%d clean_text_chars=%d",
            url,
            raw_len,
            clean_len,
        )

        regex_start = perf_counter()
        regex_iocs = self.regex_engine.extract_all(clean_text)
        regex_latency_ms = (perf_counter() - regex_start) * 1000.0
        regex_ioc_count = sum(len(values) for values in regex_iocs.model_dump(mode="json").values())
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [EXTRACTOR] Regex output source=%s duration_ms=%.1f extracted_iocs=%d",
            url,
            regex_latency_ms,
            regex_ioc_count,
        )

        llm_start = perf_counter()
        try:
            llm_intel = self.llm_client.extract_intelligence(clean_text)
            if (llm_intel.summary or "").strip() == "LLM processing unavailable":
                LOGGER.error(
                    "[SHADOWPULSE DEBUG] [CRITICAL FAILURE] [EXTRACTOR] source=%s llm_returned_generic_fallback",
                    url,
                )
                llm_intel = LLMThreatIntelligence(
                    summary="LLM extraction failed: Gemini returned generic fallback response"
                )
        except Exception as exc:
            llm_latency_ms = (perf_counter() - llm_start) * 1000.0
            LOGGER.error(
                "[SHADOWPULSE DEBUG] [CRITICAL FAILURE] [EXTRACTOR] source=%s llm_failed latency_ms=%.1f error=%s",
                url,
                llm_latency_ms,
                exc,
            )
            LOGGER.error(traceback.format_exc())
            llm_intel = LLMThreatIntelligence(summary=f"LLM extraction failed: {str(exc)}")

        elapsed_ms = (perf_counter() - start) * 1000.0
        reduction_ratio = 0.0 if raw_len == 0 else max((raw_len - clean_len) / raw_len, 0.0)
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [EXTRACTOR] Completed IOC extraction source=%s total_duration_ms=%.1f reduction_ratio=%.4f",
            url,
            elapsed_ms,
            reduction_ratio,
        )

        return ExtractedCTIPayload(
            source_url=url,
            regex_iocs=regex_iocs,
            llm_intelligence=llm_intel,
            clean_text_length=clean_len,
            raw_html_length=raw_len,
            text_reduction_ratio=reduction_ratio,
            execution_latency_ms=elapsed_ms,
        )
