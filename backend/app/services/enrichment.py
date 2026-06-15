"""Enrichment.

Augments detections with context an analyst would otherwise gather by hand:
threat-intel reputation on IPs/domains, asset criticality for hosts, and
identity context for users. Backed by pluggable providers; ships with a
deterministic mock provider and an interface for live feeds (MISP, GreyNoise,
CMDB, IdP).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Enrichment:
    threat_intel: dict[str, str] = field(default_factory=dict)
    asset_criticality: str = "unknown"  # low | medium | high | crown_jewel
    identity_context: dict[str, str] = field(default_factory=dict)
    indicators: list[str] = field(default_factory=list)

    def boost(self) -> float:
        """Risk multiplier contribution from context (1.0 = neutral)."""
        mult = 1.0
        crit = {"low": 0.95, "medium": 1.05, "high": 1.15, "crown_jewel": 1.3}
        mult *= crit.get(self.asset_criticality, 1.0)
        if self.threat_intel.get("verdict") == "malicious":
            mult *= 1.25
        if self.identity_context.get("privileged") == "true":
            mult *= 1.15
        return mult


class EnrichmentProvider(ABC):
    @abstractmethod
    async def enrich_ip(self, ip: str) -> dict[str, str]: ...

    @abstractmethod
    async def enrich_host(self, host: str) -> str: ...

    @abstractmethod
    async def enrich_user(self, user: str) -> dict[str, str]: ...


class MockEnrichmentProvider(EnrichmentProvider):
    """Deterministic enrichment for offline dev and demos."""

    _MALICIOUS_PREFIXES = ("203.0.113.", "198.51.100.")
    _CROWN_JEWELS = {"db-prod-02", "dc-01", "vault-01"}
    _HIGH_VALUE = {"web-prod-01", "ws-finance-07"}
    _PRIVILEGED_USERS = {"admin", "root", "svc_backup"}

    async def enrich_ip(self, ip: str) -> dict[str, str]:
        malicious = any(ip.startswith(p) for p in self._MALICIOUS_PREFIXES)
        return {
            "verdict": "malicious" if malicious else "benign",
            "source": "mock-ti",
            "categories": "c2,scanner" if malicious else "none",
        }

    async def enrich_host(self, host: str) -> str:
        if host in self._CROWN_JEWELS:
            return "crown_jewel"
        if host in self._HIGH_VALUE:
            return "high"
        return "medium"

    async def enrich_user(self, user: str) -> dict[str, str]:
        return {
            "privileged": "true" if user in self._PRIVILEGED_USERS else "false",
            "department": "finance" if user.startswith("fin") else "general",
        }


class EnrichmentService:
    def __init__(self, provider: EnrichmentProvider):
        self._provider = provider

    async def enrich(self, *, host: str, user: str | None, ips: list[str]) -> Enrichment:
        enrichment = Enrichment()
        enrichment.asset_criticality = await self._provider.enrich_host(host)
        if user:
            enrichment.identity_context = await self._provider.enrich_user(user)
        for ip in ips:
            ti = await self._provider.enrich_ip(ip)
            if ti.get("verdict") == "malicious":
                enrichment.threat_intel = ti
                enrichment.indicators.append(ip)
        if not enrichment.threat_intel and ips:
            enrichment.threat_intel = await self._provider.enrich_ip(ips[0])
        return enrichment
