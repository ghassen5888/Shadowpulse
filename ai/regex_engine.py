"""Deterministic IOC extraction engine."""

from __future__ import annotations

import re

from ai.schemas import RegexIOCs


class RegexEngine:
    CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
    IPV4_PATTERN = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
    )
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
    SHA256_PATTERN = re.compile(r"\b[a-fA-F0-9]{64}\b")
    BTC_LEGACY_PATTERN = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
    BTC_SEGWIT_PATTERN = re.compile(r"\b3[a-km-zA-HJ-NP-Z1-9]{25,34}\b")
    BTC_NATIVE_PATTERN = re.compile(r"\bbc1[ac-hj-np-z02-9]{11,71}\b", re.IGNORECASE)
    ONION_PATTERN = re.compile(r"\b[a-z2-7]{16,56}\.onion\b", re.IGNORECASE)
    URL_PATTERN = re.compile(r"\bhttps?://[^\s\"'<>]+", re.IGNORECASE)

    @classmethod
    def extract_all(cls, text: str) -> RegexIOCs:
        data = text or ""
        cves = sorted({match.upper() for match in cls.CVE_PATTERN.findall(data)})
        ips = sorted(set(cls.IPV4_PATTERN.findall(data)))
        emails = sorted({match.lower() for match in cls.EMAIL_PATTERN.findall(data)})
        sha256 = sorted({match.lower() for match in cls.SHA256_PATTERN.findall(data)})

        wallets = {
            *cls.BTC_LEGACY_PATTERN.findall(data),
            *cls.BTC_SEGWIT_PATTERN.findall(data),
            *cls.BTC_NATIVE_PATTERN.findall(data),
        }
        bitcoin_wallets = sorted(wallets)
        onion_addresses = sorted({match.lower() for match in cls.ONION_PATTERN.findall(data)})
        urls = sorted({match.rstrip(".,;:)") for match in cls.URL_PATTERN.findall(data)})

        return RegexIOCs(
            cves=cves,
            ips=ips,
            emails=emails,
            sha256=sha256,
            bitcoin_wallets=bitcoin_wallets,
            onion_addresses=onion_addresses,
            urls=urls,
        )
