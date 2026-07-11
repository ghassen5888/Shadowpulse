from __future__ import annotations

import copy
import json
import uuid
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Iterable

try:
    from dateutil import parser as date_parser  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without python-dateutil
    date_parser = None  # type: ignore

try:
    import stix2  # type: ignore
except Exception:  # pragma: no cover - fallback for minimal environments
    stix2 = None  # type: ignore


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_to_utc_datetime(value: Any) -> datetime:
    """Convert arbitrary timestamp-like values into a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, (int, float)):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

        if abs(numeric_value) > 1e11:
            numeric_value = numeric_value / 1000.0
        try:
            return datetime.fromtimestamp(numeric_value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.now(timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.now(timezone.utc)

        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            if date_parser is not None:
                try:
                    parsed = date_parser.parse(text)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed.astimezone(timezone.utc)
                except (ValueError, OverflowError):
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

    return datetime.now(timezone.utc)


def _build_native_stix_bundle(results: Iterable[dict[str, Any]], thread_id: str, thread_name: str, trusted_sources: Iterable[dict[str, Any]] | None = None) -> Any:
    if stix2 is None:
        raise RuntimeError("stix2 is not available")

    objects: list[Any] = []
    trusted_lookup = {item.get("url", "").lower(): item for item in (trusted_sources or []) if item.get("url")}

    campaign = stix2.Identity(
        id=f"identity--{uuid.uuid4()}",
        name=f"Shadowpulse Campaign: {thread_name}",
        identity_class="organization",
        description="Parallel dark-web reconnaissance and threat intelligence collection workflow.",
        allow_custom=True,
    )
    objects.append(campaign)

    tool = stix2.Tool(
        id=f"tool--{uuid.uuid4()}",
        name="Shadowpulse Crawler",
        tool_types=["collection"],
        description="Parallel Tor-based crawler for collecting onion-site telemetry and metadata.",
        allow_custom=True,
    )
    objects.append(tool)

    for index, item in enumerate(results, start=1):
        onion_url = str(item.get("onion_url", "")).strip()
        if not onion_url:
            continue

        title = str(item.get("title") or "Unknown")
        source = str(item.get("source") or "unknown")
        latency_ms = float(item.get("latency_ms", 0.0) or 0.0)
        http_status = int(item.get("http_status", 0) or 0)
        payload_bytes = int(item.get("payload_bytes", 0) or 0)
        crawled_at_value = item.get("crawled_at")
        crawled_at_dt = parse_to_utc_datetime(crawled_at_value)
        created_dt = parse_to_utc_datetime(item.get("created") or crawled_at_value)
        modified_dt = parse_to_utc_datetime(item.get("modified") or crawled_at_value)
        summary = str(item.get("summary") or "")
        trust_status = str(item.get("trust_status") or "Untrusted")
        trusted_source = trusted_lookup.get(onion_url.lower())
        if trusted_source is not None:
            trust_status = "Trusted"

        indicator = stix2.Indicator(
            id=f"indicator--{uuid.uuid4()}",
            pattern=f"[url:value = '{onion_url}']",
            pattern_type="stix",
            labels=["malicious-activity"],
            confidence=80,
            created=created_dt,
            modified=modified_dt,
            valid_from=crawled_at_dt,
            created_by_ref=campaign.id,
            description=f"Observed dark-web endpoint {onion_url} discovered during {thread_name}.",
            allow_custom=True,
        )
        objects.append(indicator)

        observed_data = stix2.ObservedData(
            id=f"observed-data--{uuid.uuid4()}",
            created=created_dt,
            first_observed=crawled_at_dt,
            last_observed=crawled_at_dt,
            number_observed=1,
            objects={
                "0": {
                    "type": "url",
                    "value": onion_url,
                },
            },
            labels=["network"],
            created_by_ref=campaign.id,
            allow_custom=True,
        )
        objects.append(observed_data)

        relationship = stix2.Relationship(
            id=f"relationship--{uuid.uuid4()}",
            relationship_type="indicates",
            source_ref=indicator.id,
            target_ref=observed_data.id,
            created=created_dt,
            created_by_ref=campaign.id,
            description=f"The indicator points to observed telemetry for {onion_url}.",
            allow_custom=True,
        )
        objects.append(relationship)

    return stix2.Bundle(
        id=f"bundle--{uuid.uuid4()}",
        objects=objects,
        allow_custom=True,
    )


def build_stix_bundle(results: Iterable[dict[str, Any]], thread_id: str, thread_name: str, trusted_sources: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
    if stix2 is not None:
        try:
            bundle = _build_native_stix_bundle(results, thread_id=thread_id, thread_name=thread_name, trusted_sources=trusted_sources)
            return json.loads(bundle.serialize())
        except Exception:
            pass

    objects: list[dict[str, Any]] = []
    trusted_lookup = {item.get("url", "").lower(): item for item in (trusted_sources or []) if item.get("url")}
    objects.append(
        {
            "type": "identity",
            "spec_version": "2.1",
            "id": "identity--shadowpulse-campaign",
            "name": f"Shadowpulse Campaign: {thread_name}",
            "identity_class": "organization",
            "description": "Parallel dark-web reconnaissance and threat intelligence collection workflow.",
        }
    )
    objects.append(
        {
            "type": "tool",
            "spec_version": "2.1",
            "id": "tool--shadowpulse-crawler",
            "name": "Shadowpulse Crawler",
            "tool_types": ["collection"],
            "description": "Parallel Tor-based crawler for collecting onion-site telemetry and metadata.",
        }
    )

    for index, item in enumerate(results, start=1):
        onion_url = str(item.get("onion_url", "")).strip()
        if not onion_url:
            continue

        title = str(item.get("title") or "Unknown")
        source = str(item.get("source") or "unknown")
        latency_ms = float(item.get("latency_ms", 0.0) or 0.0)
        http_status = int(item.get("http_status", 0) or 0)
        payload_bytes = int(item.get("payload_bytes", 0) or 0)
        crawled_at_value = item.get("crawled_at")
        crawled_at_dt = parse_to_utc_datetime(crawled_at_value)
        crawled_at = crawled_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = str(item.get("summary") or "")
        trust_status = str(item.get("trust_status") or "Untrusted")
        trusted_source = trusted_lookup.get(onion_url.lower())
        if trusted_source is not None:
            trust_status = "Trusted"

        indicator_id = f"indicator--{index:06d}"
        observed_id = f"observed-data--{index:06d}"
        objects.append(
            {
                "type": "indicator",
                "spec_version": "2.1",
                "id": indicator_id,
                "pattern": f"[url:value = '{onion_url}']",
                "pattern_type": "stix",
                "labels": ["malicious-activity"],
                "confidence": 80,
                "created": _utc_now(),
                "modified": _utc_now(),
                "description": f"Observed dark-web endpoint {onion_url} discovered during {thread_name}.",
            }
        )
        objects.append(
            {
                "type": "observed-data",
                "spec_version": "2.1",
                "id": observed_id,
                "created": _utc_now(),
                "first_observed": crawled_at,
                "last_observed": crawled_at,
                "number_observed": 1,
                "objects": {
                    "url": onion_url,
                    "title": title,
                    "source": source,
                    "latency_ms": latency_ms,
                    "http_status": http_status,
                    "payload_bytes": payload_bytes,
                    "summary": summary,
                    "trust_status": trust_status,
                },
                "labels": ["network"],
            }
        )
        objects.append(
            {
                "type": "relationship",
                "spec_version": "2.1",
                "id": f"relationship--{index:06d}",
                "relationship_type": "indicates",
                "source_ref": indicator_id,
                "target_ref": observed_id,
                "description": f"The indicator points to observed telemetry for {onion_url}.",
            }
        )

    return {
        "type": "bundle",
        "id": f"bundle--{thread_id}",
        "objects": objects,
    }


def export_stix_bundle_json(results: Iterable[dict[str, Any]], thread_id: str, thread_name: str, trusted_sources: Iterable[dict[str, Any]] | None = None) -> str:
    if stix2 is not None:
        bundle = _build_native_stix_bundle(results, thread_id=thread_id, thread_name=thread_name, trusted_sources=trusted_sources)
        return bundle.serialize(pretty=True)

    bundle = build_stix_bundle(results, thread_id=thread_id, thread_name=thread_name, trusted_sources=trusted_sources)
    return json.dumps(bundle, indent=2, sort_keys=True)


def export_stix_bundle_bytes(results: Iterable[dict[str, Any]], thread_id: str, thread_name: str, trusted_sources: Iterable[dict[str, Any]] | None = None) -> bytes:
    payload = export_stix_bundle_json(results, thread_id=thread_id, thread_name=thread_name, trusted_sources=trusted_sources)
    return payload.encode("utf-8")


def download_bytes_io(results: Iterable[dict[str, Any]], thread_id: str, thread_name: str, trusted_sources: Iterable[dict[str, Any]] | None = None) -> BytesIO:
    buffer = BytesIO(export_stix_bundle_bytes(results, thread_id=thread_id, thread_name=thread_name, trusted_sources=trusted_sources))
    buffer.seek(0)
    return buffer
