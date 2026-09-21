"""Concrete platform adapters. Each declares identity and its environment prefix only;
behaviour (states, retries, SSRF guard, honesty) lives in ``GovernmentAdapter``."""

from __future__ import annotations

from collections.abc import Mapping

from app.integrations.base import AdapterConfig, GovernmentAdapter


class CPGRAMSAdapter(GovernmentAdapter):
    platform, display_name, env_prefix = "cpgrams", "CPGRAMS", "CPGRAMS"


class UMANGAdapter(GovernmentAdapter):
    platform, display_name, env_prefix = "umang", "UMANG", "UMANG"


class SwachhataAdapter(GovernmentAdapter):
    platform, display_name, env_prefix = "swachhata", "Swachhata App", "SWACHHATA"


class BBMPSahaayaAdapter(GovernmentAdapter):
    platform, display_name, env_prefix = "bbmp_sahaaya", "BBMP Sahaaya", "BBMP_SAHAAYA"


class MyGovAdapter(GovernmentAdapter):
    platform, display_name, env_prefix = "mygov", "MyGov", "MYGOV"


ADAPTER_CLASSES: tuple[type[GovernmentAdapter], ...] = (CPGRAMSAdapter, UMANGAdapter, SwachhataAdapter, BBMPSahaayaAdapter, MyGovAdapter)


def build_adapters(env: Mapping[str, str], **kwargs) -> dict[str, GovernmentAdapter]:  # type: ignore[no-untyped-def]
    timeout = float(env.get("GOV_ADAPTER_TIMEOUT_SECONDS", "10") or 10)
    retries = int(env.get("GOV_ADAPTER_MAX_RETRIES", "2") or 2)
    return {cls.platform: cls(AdapterConfig.from_env(cls.env_prefix, env, timeout=timeout, retries=retries), **kwargs) for cls in ADAPTER_CLASSES}  # type: ignore[attr-defined]
