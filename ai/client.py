"""Gemini client wrapper for structured CTI extraction."""

from __future__ import annotations

import contextlib
import json
import logging
import os
from time import perf_counter
from typing import Any

from dotenv import load_dotenv

from ai.schemas import LLMThreatIntelligence

load_dotenv()

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a cyber threat intelligence extraction engine.
Task:
- Perform passive NER extraction only from provided text.
- Do not infer unsupported entities.
- Return strict JSON only.

Return JSON with this exact schema:
{
  "threat_actors": [{"name": "string", "confidence": 0.0}],
  "malware_families": [{"name": "string", "confidence": 0.0}],
  "victims": [{"name": "string", "confidence": 0.0}],
  "target_industries": ["string"],
  "target_countries": ["string"],
  "attack_techniques": ["string"],
  "summary": "2-3 sentence executive summary"
}
"""


class LLMClient:
    def __init__(self, model_candidates: list[str] | None = None) -> None:
        self.model_candidates = model_candidates or ["gemini-2.5-flash", "gemini-1.5-flash"]
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._genai = None
        self._enabled = bool(self.api_key)

        if self._enabled:
            try:
                import google.generativeai as genai  # type: ignore

                genai.configure(api_key=self.api_key)
                self._genai = genai
            except ImportError as exc:
                LOGGER.error("[LLM CLIENT] Gemini SDK unavailable: %s", exc)
                self._enabled = False
            except Exception as exc:
                LOGGER.error("[LLM CLIENT] Gemini initialization error: %s", exc)
                self._enabled = False
        else:
            LOGGER.error("[LLM CLIENT] GEMINI_API_KEY is missing or empty.")

    @staticmethod
    def _fallback_response(summary: str = "LLM processing unavailable") -> LLMThreatIntelligence:
        return LLMThreatIntelligence(summary=summary)

    @staticmethod
    def _to_payload_dict(raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            return {}
        return json.loads(text)

    @staticmethod
    @contextlib.contextmanager
    def _without_proxy_env():
        proxy_keys = (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
        previous = {key: os.environ.get(key) for key in proxy_keys}
        try:
            for key in proxy_keys:
                if key in os.environ:
                    del os.environ[key]
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @staticmethod
    def _is_network_error(exc: Exception) -> bool:
        message = str(exc).lower()
        network_markers = (
            "timeout",
            "timed out",
            "connection",
            "network",
            "ssl",
            "tls",
            "socket",
            "proxy",
            "unreachable",
        )
        return any(marker in message for marker in network_markers)

    def extract_intelligence(self, clean_text: str) -> LLMThreatIntelligence:
        if not self._enabled or self._genai is None or not clean_text.strip():
            return self._fallback_response()

        prompt = (
            "Extract CTI entities from this text.\n"
            "Respond with strict JSON matching the schema.\n\n"
            f"TEXT:\n{clean_text[:24000]}"
        )

        saw_network_failure = False
        for model_name in self.model_candidates:
            model_start = perf_counter()
            try:
                model = self._genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_PROMPT.strip(),
                )
                with self._without_proxy_env():
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.1,
                            "response_mime_type": "application/json",
                        },
                        request_options={"timeout": 30},
                    )
                latency_ms = (perf_counter() - model_start) * 1000.0
                LOGGER.error("[LLM CLIENT] model=%s latency_ms=%.1f", model_name, latency_ms)
                payload = self._to_payload_dict(getattr(response, "text", ""))
                return LLMThreatIntelligence.model_validate(payload)
            except json.JSONDecodeError as exc:
                latency_ms = (perf_counter() - model_start) * 1000.0
                LOGGER.error(
                    "[LLM CLIENT] model=%s invalid_json latency_ms=%.1f error=%s",
                    model_name,
                    latency_ms,
                    exc,
                )
            except Exception as exc:
                latency_ms = (perf_counter() - model_start) * 1000.0
                LOGGER.error(
                    "[LLM CLIENT] model=%s failed latency_ms=%.1f error=%s",
                    model_name,
                    latency_ms,
                    exc,
                )
                if self._is_network_error(exc):
                    saw_network_failure = True

        if saw_network_failure:
            return self._fallback_response(summary="")
        return self._fallback_response()
