"""Gemini client wrapper for structured CTI extraction."""

from __future__ import annotations

import json
import logging
import os
import re
from time import perf_counter
import traceback
from typing import Any

from dotenv import load_dotenv

from ai.schemas import LLMThreatIntelligence

load_dotenv()

LOGGER = logging.getLogger(__name__)
PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_FALLBACK_MODELS = [
    PRIMARY_MODEL,
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-flash-latest",
    "gemini-1.5-pro",
]
FALLBACK_MODELS = list(dict.fromkeys(DEFAULT_FALLBACK_MODELS))

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
    def __init__(
        self,
        model: str | None = None,
        model_candidates: list[str] | None = None,
    ) -> None:
        configured_model = model or (model_candidates[0] if model_candidates else None) or PRIMARY_MODEL
        ordered_candidates = [
            str(configured_model).strip(),
            *[str(candidate).strip() for candidate in (model_candidates or []) if str(candidate).strip()],
            *FALLBACK_MODELS,
        ]
        self.model_chain = list(dict.fromkeys(candidate for candidate in ordered_candidates if candidate))
        self.model = self.model_chain[0] if self.model_chain else "gemini-2.5-flash"
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._client: Any | None = None
        self._enabled = bool(self.api_key)
        masked_key = f"{self.api_key[:4]}..." if self.api_key else "MISSING"
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [LLM CLIENT] model=%s GEMINI_API_KEY present=%s key_prefix=%s",
            self.model,
            self._enabled,
            masked_key,
        )
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [LLM CLIENT] fallback_chain=%s",
            self.model_chain,
        )
        if self.api_key:
            LOGGER.info("[GEMINI CLIENT] Using API Key starting with: %s...", self.api_key[:5])

        if self._enabled:
            try:
                from google import genai  # type: ignore

                for key in PROXY_ENV_KEYS:
                    os.environ.pop(key, None)
                self._client = genai.Client(api_key=self.api_key)
            except ImportError as exc:
                LOGGER.error("[SHADOWPULSE DEBUG] [LLM CLIENT] Gemini SDK unavailable: %s", exc)
                LOGGER.error(traceback.format_exc())
                self._enabled = False
            except Exception as exc:
                LOGGER.error("[SHADOWPULSE DEBUG] [LLM CLIENT] Gemini initialization error: %s", exc)
                LOGGER.error(traceback.format_exc())
                self._enabled = False
        else:
            LOGGER.error("[SHADOWPULSE DEBUG] [LLM CLIENT] GEMINI_API_KEY is missing or empty.")

    @staticmethod
    def _fallback_response(summary: str = "LLM processing unavailable") -> LLMThreatIntelligence:
        return LLMThreatIntelligence(summary=summary)

    @staticmethod
    def _get_empty_fallback_dict() -> dict[str, Any]:
        return {
            "threat_actors": [],
            "malware_families": [],
            "victims": [],
            "target_industries": [],
            "target_countries": [],
            "attack_techniques": [],
            "summary": "LLM extraction unavailable: invalid or empty Gemini JSON response",
        }

    def _to_payload_dict(self, raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            LOGGER.warning("[LLM CLIENT] Received empty response text from Gemini.")
            return self._get_empty_fallback_dict()

        cleaned_text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text, flags=re.MULTILINE).strip()

        match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
        if match:
            cleaned_text = match.group(0)

        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            LOGGER.error("[LLM CLIENT] Failed to decode JSON. Raw text: %r", raw_text)
            return self._get_empty_fallback_dict()

    @staticmethod
    def _is_empty_fallback_payload(payload: dict[str, Any]) -> bool:
        fallback = LLMClient._get_empty_fallback_dict()
        return payload == fallback

    @staticmethod
    def _log_proxy_env_state() -> None:
        for key in PROXY_ENV_KEYS:
            value = os.environ.get(key)
            masked_value = value if not value else f"{value[:48]}..."
            LOGGER.debug(
                "[SHADOWPULSE DEBUG] [LLM CLIENT] proxy_env %s set=%s value=%s",
                key,
                bool(value),
                masked_value,
            )

    def extract_intelligence(self, clean_text: str) -> LLMThreatIntelligence:
        if not clean_text.strip():
            return self._fallback_response(summary="LLM extraction skipped: empty text")
        if not self._enabled or self._client is None:
            return self._fallback_response(summary="LLM extraction unavailable: Gemini client not initialized")
        self._log_proxy_env_state()

        prompt = (
            "Extract CTI entities from this text.\n"
            "Respond with strict JSON matching the schema.\n\n"
            f"TEXT:\n{clean_text[:24000]}"
        )

        last_error: Exception | None = None
        for index, model_name in enumerate(self.model_chain, start=1):
            model_start = perf_counter()
            try:
                for key in PROXY_ENV_KEYS:
                    os.environ.pop(key, None)
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=f"{SYSTEM_PROMPT.strip()}\n\n{prompt}",
                    config={"response_mime_type": "application/json"},
                )
                latency_ms = (perf_counter() - model_start) * 1000.0
                response_text = getattr(response, "text", "") or ""
                payload = self._to_payload_dict(response_text)
                if self._is_empty_fallback_payload(payload):
                    raise ValueError("Gemini returned invalid or empty JSON payload")

                intelligence = LLMThreatIntelligence.model_validate(payload)
                self.model = model_name
                LOGGER.debug(
                    "[SHADOWPULSE DEBUG] [LLM CLIENT] model=%s success latency_ms=%.1f response_text_chars=%d fallback_attempt=%d/%d",
                    model_name,
                    latency_ms,
                    len(response_text),
                    index,
                    len(self.model_chain),
                )
                return intelligence
            except Exception as exc:
                latency_ms = (perf_counter() - model_start) * 1000.0
                last_error = exc
                LOGGER.warning(
                    "[SHADOWPULSE DEBUG] [LLM CLIENT] model=%s failed latency_ms=%.1f fallback_attempt=%d/%d error=%s",
                    model_name,
                    latency_ms,
                    index,
                    len(self.model_chain),
                    exc,
                )
                LOGGER.debug(traceback.format_exc())
                continue

        LOGGER.error("[GEMINI ERROR] All Gemini fallback models failed: %s", self.model_chain)
        if last_error:
            raise RuntimeError(
                f"Gemini extraction failed for all fallback models: {', '.join(self.model_chain)}"
            ) from last_error
        raise RuntimeError("Gemini extraction failed: no fallback models available")
