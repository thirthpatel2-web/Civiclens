"""Four real, working adapters that normalize realistically heterogeneous department data shapes
into ``CanonicalRecord`` - the actual technical mechanism "interoperability" requires.

Each adapter ships one realistic *fixture* payload shaped exactly the way that kind of system tends
to export data (verified against public documentation/screenshots of the respective system
categories, not invented at random): a legacy municipal system using SCREAMING_SNAKE_CASE flat
exports, a modern utility CRM using camelCase JSON, a police CCTNS-style FIR record, and a state
portal that represents status as a bare numeric code. None of these are live feeds - no department
has given CivicLens a data-sharing agreement - so this is intentionally exercised against fixtures,
not a live poll. The adapter functions themselves are real and directly reusable against a genuine
feed shaped like these the day such an agreement exists.
"""

from __future__ import annotations

from collections.abc import Callable

from app.interop.common_data_model import CanonicalRecord

# ---------------------------------------------------------------------------------------------
# 1. Legacy municipal system: flat SCREAMING_SNAKE_CASE keys, status as a free-text word.
# ---------------------------------------------------------------------------------------------

MUNICIPAL_STATUS_MAP = {"LODGED": "received", "UNDER_ACTION": "in_progress", "CLOSED_RESOLVED": "resolved", "CLOSED_INVALID": "rejected"}

MUNICIPAL_FIXTURE = {
    "COMPLAINT_ID": "BBMP-2026-00412",
    "COMPLAINT_TYPE": "ROAD_POTHOLE",
    "CURRENT_STATUS": "UNDER_ACTION",
    "CITIZEN_NAME": "R SURESH KUMAR",
    "CITIZEN_MOBILE": "9845012345",
    "WARD_NO": "WARD-114",
    "DATE_LODGED": "18-09-2026",
    "ASSIGNED_DEPT": "BBMP ROADS DIVISION 3",
}


def from_municipal_legacy(rec: dict) -> CanonicalRecord:
    return CanonicalRecord(
        source_system="municipal_legacy",
        external_id=str(rec.get("COMPLAINT_ID", "")),
        category=str(rec.get("COMPLAINT_TYPE", "")).lower().replace("_", " "),
        status=MUNICIPAL_STATUS_MAP.get(str(rec.get("CURRENT_STATUS", "")), "unknown"),
        title=str(rec.get("COMPLAINT_TYPE", "")).replace("_", " ").title(),
        department=str(rec.get("ASSIGNED_DEPT", "")),
        citizen_name=rec.get("CITIZEN_NAME"),
        citizen_contact=rec.get("CITIZEN_MOBILE"),
        location=rec.get("WARD_NO"),
        filed_on=rec.get("DATE_LODGED"),
        raw=rec,
    )


# ---------------------------------------------------------------------------------------------
# 2. Modern utility CRM: camelCase JSON, its own status words.
# ---------------------------------------------------------------------------------------------

UTILITY_STATUS_MAP = {"NEW": "received", "ASSIGNED": "in_progress", "COMPLETED": "resolved", "DUPLICATE": "rejected"}

UTILITY_FIXTURE = {
    "ticketId": "BESCOM-TCK-88213",
    "serviceType": "PowerOutage",
    "ticketStatus": "ASSIGNED",
    "customerName": "Ananya Rao",
    "customerPhone": "+91-9900123456",
    "serviceArea": "Indiranagar Sub-Division",
    "raisedOn": "2026-09-15T09:20:00",
    "ownerTeam": "BESCOM O&M Zone 4",
}


def from_utility_crm(rec: dict) -> CanonicalRecord:
    return CanonicalRecord(
        source_system="utility_crm",
        external_id=str(rec.get("ticketId", "")),
        category=str(rec.get("serviceType", "")).lower(),
        status=UTILITY_STATUS_MAP.get(str(rec.get("ticketStatus", "")), "unknown"),
        title=str(rec.get("serviceType", "")),
        department=str(rec.get("ownerTeam", "")),
        citizen_name=rec.get("customerName"),
        citizen_contact=rec.get("customerPhone"),
        location=rec.get("serviceArea"),
        filed_on=rec.get("raisedOn"),
        raw=rec,
    )


# ---------------------------------------------------------------------------------------------
# 3. Police CCTNS-style FIR record: domain-specific field names, its own status words.
# ---------------------------------------------------------------------------------------------

POLICE_STATUS_MAP = {"REGISTERED": "received", "UNDER_INVESTIGATION": "in_progress", "CHARGESHEET_FILED": "resolved", "CLOSED_FALSE": "rejected"}

POLICE_FIXTURE = {
    "fir_no": "0142/2026",
    "offence_type": "Theft (Sec 379 IPC)",
    "case_status": "UNDER_INVESTIGATION",
    "complainant_name": "M. Fathima",
    "complainant_contact": "9741023456",
    "police_station": "Koramangala PS",
    "date_of_registration": "10-09-2026",
    "investigating_officer_unit": "Koramangala PS Crime Wing",
}


def from_police_cctns(rec: dict) -> CanonicalRecord:
    return CanonicalRecord(
        source_system="police_cctns",
        external_id=str(rec.get("fir_no", "")),
        category="police",
        status=POLICE_STATUS_MAP.get(str(rec.get("case_status", "")), "unknown"),
        title=str(rec.get("offence_type", "")),
        department=str(rec.get("investigating_officer_unit", "")),
        citizen_name=rec.get("complainant_name"),
        citizen_contact=rec.get("complainant_contact"),
        location=rec.get("police_station"),
        filed_on=rec.get("date_of_registration"),
        raw=rec,
    )


# ---------------------------------------------------------------------------------------------
# 4. State e-governance portal: bare numeric status codes, no domain-word status at all.
# ---------------------------------------------------------------------------------------------

STATE_PORTAL_STATUS_MAP = {1: "received", 2: "in_progress", 3: "resolved", 4: "rejected"}

STATE_PORTAL_FIXTURE = {
    "ref_no": "KA-SEVA-2026-773310",
    "dept_code": "PWD",
    "service_name": "Drainage Blockage",
    "status_code": 2,
    "applicant": "K. Nataraj",
    "mobile": "9632145870",
    "district": "Bengaluru Urban",
    "submitted_date": "2026-09-12",
}


def from_state_portal(rec: dict) -> CanonicalRecord:
    # rec is raw external data, so status_code is not guaranteed to actually be the int this real
    # portal's export normally sends it as; a missing or malformed one now honestly falls through
    # to "unknown" - the same label already used for an int that just isn't in the map - rather
    # than being passed as a lookup key of a type STATE_PORTAL_STATUS_MAP was never keyed by.
    status_code = rec.get("status_code")
    return CanonicalRecord(
        source_system="state_portal",
        external_id=str(rec.get("ref_no", "")),
        category=str(rec.get("service_name", "")).lower(),
        status=STATE_PORTAL_STATUS_MAP.get(status_code, "unknown") if isinstance(status_code, int) else "unknown",
        title=str(rec.get("service_name", "")),
        department=str(rec.get("dept_code", "")),
        citizen_name=rec.get("applicant"),
        citizen_contact=rec.get("mobile"),
        location=rec.get("district"),
        filed_on=rec.get("submitted_date"),
        raw=rec,
    )


SYSTEMS: dict[str, tuple[str, dict, Callable[[dict], CanonicalRecord]]] = {
    "municipal_legacy": ("Legacy Municipal System (flat SCREAMING_SNAKE_CASE export)", MUNICIPAL_FIXTURE, from_municipal_legacy),
    "utility_crm": ("Utility CRM (modern camelCase JSON API)", UTILITY_FIXTURE, from_utility_crm),
    "police_cctns": ("Police CCTNS-style FIR record", POLICE_FIXTURE, from_police_cctns),
    "state_portal": ("State e-Governance Portal (numeric status codes)", STATE_PORTAL_FIXTURE, from_state_portal),
}


def corrupt_payload(payload: dict) -> dict:
    """Simulates a malformed inbound record: blanks contact/name-like fields and breaks the status
    code - so the normalization demo can show what a bad record looks like before and after."""
    out = dict(payload)
    for k in list(out.keys()):
        kl = k.lower()
        if "status" in kl:
            out[k] = "???" if isinstance(out[k], str) else 99
        if any(tok in kl for tok in ("name", "mobile", "phone", "contact", "applicant", "complainant")):
            out[k] = ""
    return out
