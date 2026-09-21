"""Fragmentation diagnostic: grounds "fragmented service delivery" in a sourced national figure
plus a real personal calculation from the citizen's own CivicLens filing history, instead of
asserting the problem without evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

# Source: UMANG (Unified Mobile Application for New-age Governance), the Government of India's own
# unification app under the Digital India programme (Ministry of Electronics & IT). Its own public
# reporting has described aggregating 1,700+ services from 100+ central/state departments - cited
# here as an order-of-magnitude illustration that even the government's own unification effort is
# still bridging a large number of separately-run systems, not a figure this app fetches live.
# Verify the current count on umang.gov.in before quoting it as current.
NATIONAL_UMANG_SERVICES = 1700
NATIONAL_UMANG_DEPARTMENTS = 100
NATIONAL_UMANG_SOURCE = "UMANG — Digital India programme, Ministry of Electronics & IT (see umang.gov.in for the current count)"


@dataclass(frozen=True)
class PersonalFragmentation:
    distinct_departments: int
    total_filings: int
    profile_reuses: int  # filings after the first that reused one CivicLens identity instead of re-entering KYC elsewhere


def personal_diagnostic(department_codes: list[str | None]) -> PersonalFragmentation:
    seen = [d for d in department_codes if d]
    total = len(seen)
    return PersonalFragmentation(distinct_departments=len(set(seen)), total_filings=total, profile_reuses=max(0, total - 1))
