"""STIX 2.1 exporter for extracted CTI payloads."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ai.schemas import ExtractedCTIPayload


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_payload(payload: ExtractedCTIPayload | dict[str, Any]) -> ExtractedCTIPayload:
    if isinstance(payload, ExtractedCTIPayload):
        return payload
    return ExtractedCTIPayload.model_validate(payload)


def _indicator(pattern: str, name: str, description: str) -> dict[str, Any]:
    timestamp = _now()
    return {
        "type": "indicator",
        "spec_version": "2.1",
        "id": f"indicator--{uuid.uuid4()}",
        "created": timestamp,
        "modified": timestamp,
        "name": name,
        "description": description,
        "pattern": pattern,
        "pattern_type": "stix",
        "valid_from": timestamp,
    }


def build_stix_bundle_from_payload(payload: ExtractedCTIPayload | dict[str, Any]) -> dict[str, Any]:
    parsed = _as_payload(payload)
    created = parsed.processed_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    iocs = parsed.regex_iocs

    objects: list[dict[str, Any]] = [
        {
            "type": "identity",
            "spec_version": "2.1",
            "id": f"identity--{uuid.uuid4()}",
            "created": created,
            "modified": created,
            "name": "Shadowpulse Hybrid CTI",
            "identity_class": "organization",
        },
        {
            "type": "report",
            "spec_version": "2.1",
            "id": f"report--{uuid.uuid4()}",
            "created": created,
            "modified": created,
            "name": f"CTI Extraction: {parsed.source_url}",
            "description": parsed.llm_intelligence.summary,
            "published": created,
            "report_types": ["threat-report"],
        },
    ]

    for cve in iocs.cves:
        objects.append(_indicator(f"[vulnerability:name = '{cve}']", f"CVE Indicator {cve}", "Extracted CVE"))
    for ip in iocs.ips:
        objects.append(_indicator(f"[ipv4-addr:value = '{ip}']", f"IP Indicator {ip}", "Extracted IPv4 IOC"))
    for email in iocs.emails:
        objects.append(_indicator(f"[email-addr:value = '{email}']", f"Email Indicator {email}", "Extracted email IOC"))
    for sha in iocs.sha256:
        objects.append(
            _indicator(
                f"[file:hashes.'SHA-256' = '{sha}']",
                f"SHA256 Indicator {sha[:12]}",
                "Extracted SHA256 IOC",
            )
        )
    for url in sorted(set(iocs.urls + iocs.onion_addresses)):
        if ".onion" in url and not url.startswith("http"):
            value = f"http://{url}"
        else:
            value = url
        objects.append(_indicator(f"[url:value = '{value}']", f"URL Indicator {value}", "Extracted URL/onion IOC"))

    for wallet in iocs.bitcoin_wallets:
        objects.append(
            {
                "type": "x-shadowpulse-bitcoin-wallet",
                "spec_version": "2.1",
                "id": f"x-shadowpulse-bitcoin-wallet--{uuid.uuid4()}",
                "created": created,
                "modified": created,
                "value": wallet,
            }
        )

    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "spec_version": "2.1",
        "objects": objects,
    }


def export_cti_payload_with_stix_json(payload: ExtractedCTIPayload | dict[str, Any]) -> str:
    parsed = _as_payload(payload)
    data = {
        "extracted_cti_payload": parsed.model_dump(mode="json"),
        "stix_bundle": build_stix_bundle_from_payload(parsed),
    }
    return json.dumps(data, indent=2, sort_keys=True)
