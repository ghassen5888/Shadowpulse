"""Gemini client wrapper for structured CTI extraction."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from ai.schemas import LLMThreatIntelligence

load_dotenv()

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
                print(f"[LLMClient] Gemini SDK unavailable: {exc}")
                self._enabled = False
            except Exception as exc:
                print(f"[LLMClient] Gemini initialization error: {exc}")
                self._enabled = False

    @staticmethod
    def _fallback_response() -> LLMThreatIntelligence:
        return LLMThreatIntelligence(summary="LLM processing unavailable")

    @staticmethod
    def _to_payload_dict(raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            return {}
        return json.loads(text)

    def extract_intelligence(self, clean_text: str) -> LLMThreatIntelligence:
        if not self._enabled or self._genai is None or not clean_text.strip():
            return self._fallback_response()

        prompt = (
            "Extract CTI entities from this text.\n"
            "Respond with strict JSON matching the schema.\n\n"
            f"TEXT:\n{clean_text[:24000]}"
        )

        for model_name in self.model_candidates:
            try:
                model = self._genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_PROMPT.strip(),
                )
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "response_mime_type": "application/json",
                    },
                    request_options={"timeout": 30},
                )
                payload = self._to_payload_dict(getattr(response, "text", ""))
                return LLMThreatIntelligence.model_validate(payload)
            except json.JSONDecodeError as exc:
                print(f"[LLMClient] Invalid JSON from {model_name}: {exc}")
            except Exception as exc:
                print(f"[LLMClient] Model {model_name} failed: {exc}")

        return self._fallback_response()
