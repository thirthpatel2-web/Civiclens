"""In-memory UnitOfWork and repositories. TEST DOUBLES ONLY - production uses app/db.

The unit of work snapshots state on entry and restores it when the block exits without
``commit()``, so tests can prove that failures leave no partial writes.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any

from app.services.complaint_status import FINISHED
from app.services.ports import (
    AnomalyRecord,
    ComplaintEvent,
    ComplaintRecord,
    ComplaintRow,
    ConsentRecord,
    ConversationMessage,
    ConversationRecord,
    DepartmentRecord,
    DraftRecord,
    EvidenceRecord,
    FeedbackRecord,
    InvestigationRecord,
    JobRecord,
    NotificationPreference,
    NotificationRecord,
    OfficerLoad,
    ProfileRecord,
)
from app.services.routing_service import RoutingRule
from app.services.sla_service import SlaPolicy


class Stores:
    def __init__(self) -> None:
        self.complaints: dict[str, ComplaintRecord] = {}
        self.events: dict[str, list[ComplaintEvent]] = {}
        self.evidence: dict[str, EvidenceRecord] = {}
        self.feedback: dict[str, FeedbackRecord] = {}
        self.notifications: dict[str, NotificationRecord] = {}
        self.prefs: dict[str, NotificationPreference] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.profiles: dict[str, ProfileRecord] = {}
        self.consent: list[ConsentRecord] = []
        self.drafts: dict[str, DraftRecord] = {}
        self.anomalies: dict[str, AnomalyRecord] = {}
        self.investigations: dict[str, InvestigationRecord] = {}
        self.conversations: dict[str, ConversationRecord] = {}
        self.messages: list[ConversationMessage] = []
        self.audit: list[Any] = []
        self.users: dict[str, Any] = {}
        self.sessions: dict[str, Any] = {}
        self.resets: dict[str, Any] = {}
        self.mfa: dict[str, Any] = {}
        self.rti: dict[str, Any] = {}
        self.voice: dict[str, Any] = {}
        self.documents: dict[str, Any] = {}
        self.snapshots: list = []
        self.push: list = []
        self.emergency: dict = {}
        self.dup_reviews: list = []
        self.wf_rules: dict = {}
        self.wf_exec: dict = {}
        self.gov: dict = {}
        self.legal: dict = {}
        self.departments: list[DepartmentRecord] = [DepartmentRecord("roads", "Roads Department"), DepartmentRecord("water", "Water Supply Department"), DepartmentRecord("general", "General Administration")]
        self.rules: list[RoutingRule] = [RoutingRule("r-roads", 10, "roads", categories=frozenset({"roads"})), RoutingRule("r-water", 10, "water", categories=frozenset({"water"}))]
        self.sla: list[SlaPolicy] = [SlaPolicy("p-medium", "medium", 72), SlaPolicy("p-high", "high", 24), SlaPolicy("p-critical", "critical", 8), SlaPolicy("p-low", "low", 240)]
        self.officers: dict[str, list[str]] = {"roads": ["off-roads-1", "off-roads-2"], "water": ["off-water-1"]}
        self.labels: dict[str, str] = {}
        self.admins: list[str] = ["admin-1"]
        self.wards: list = []
        self.cities: list = []
        self.services: list = []
        self.offices: list = []
        self.external_ids: list = []
        self.int_exceptions: dict = {}
        self.ext_links: dict = {}
        self.corrections: list = []


class MemComplaints:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, c): self.s.complaints[c.id] = c
    def get(self, i): return self.s.complaints.get(i)
    def get_by_reference(self, r): return next((c for c in self.s.complaints.values() if c.reference == r), None)
    def get_by_client_request(self, citizen_id, crid): return next((c for c in self.s.complaints.values() if c.citizen_id == citizen_id and c.client_request_id == crid), None)
    def reference_exists(self, r): return self.get_by_reference(r) is not None
    def update(self, c): self.s.complaints[c.id] = c
    def list_for_citizen(self, citizen_id, *, limit=50, offset=0):
        return sorted((c for c in self.s.complaints.values() if c.citizen_id == citizen_id), key=lambda c: c.created_at, reverse=True)[offset : offset + limit]

    def list_for_department(self, dept, *, statuses=None, officer_id=None, limit=50, offset=0):
        rows = [c for c in self.s.complaints.values() if c.department_code == dept and (not statuses or c.status in statuses) and (officer_id is None or c.assigned_officer_id == officer_id)]
        return sorted(rows, key=lambda c: c.created_at, reverse=True)[offset : offset + limit]

    def list_unrouted(self, *, limit=100): return [c for c in self.s.complaints.values() if c.department_code is None][:limit]
    def list_by_status(self, statuses, *, limit=1000): return [c for c in self.s.complaints.values() if c.status in statuses][:limit]
    def list_open(self): return [c for c in self.s.complaints.values() if c.status not in FINISHED]
    def duplicate_candidates(self, category, since, *, limit=200): return [c for c in self.s.complaints.values() if c.category == category and c.created_at >= since][:limit]

    def rows(self, *, citizen_id=None, department_code=None, since=None):
        return [ComplaintRow(c.id, c.reference, c.status, c.category, c.severity, c.priority, c.department_code, c.ward, c.complaint_type, c.created_at, c.resolved_at, c.sla_due_at, c.escalation_level, c.lat, c.lng, c.assigned_officer_id, c.citizen_id, c.routing.get("source"), bool(c.duplicates))
                for c in self.s.complaints.values() if (citizen_id is None or c.citizen_id == citizen_id) and (department_code is None or c.department_code == department_code) and (since is None or c.created_at >= since)]  # fmt: skip

    def add_event(self, e): self.s.events.setdefault(e.complaint_id, []).append(e)
    def list_events(self, cid): return sorted(self.s.events.get(cid, []), key=lambda e: e.at)
    def add_evidence(self, e): self.s.evidence[e.id] = e
    def get_evidence(self, i): return self.s.evidence.get(i)
    def update_evidence(self, e): self.s.evidence[e.id] = e
    def list_evidence(self, cid): return [e for e in self.s.evidence.values() if e.complaint_id == cid]
    def add_feedback(self, f): self.s.feedback[f.complaint_id] = f
    def get_feedback(self, cid): return self.s.feedback.get(cid)

    def officer_loads(self, dept, ids):
        return [OfficerLoad(i, sum(1 for c in self.s.complaints.values() if c.assigned_officer_id == i and c.status not in FINISHED)) for i in ids]


class MemOfficers:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def officer_ids_for_department(self, d): return list(self.s.officers.get(d, []))
    def user_label(self, uid): return self.s.labels.get(uid, uid)
    def admin_ids(self): return list(self.s.admins)


class MemNotifications:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, n):
        if n.dedupe_key and any(x.user_id == n.user_id and x.dedupe_key == n.dedupe_key for x in self.s.notifications.values()):
            return False
        self.s.notifications[n.id] = n
        return True

    def get(self, i): return self.s.notifications.get(i)
    def update(self, n): self.s.notifications[n.id] = n
    def list_for_user(self, uid, *, unread_only=False, limit=50):
        rows = [n for n in self.s.notifications.values() if n.user_id == uid and (not unread_only or n.read_at is None)]
        return sorted(rows, key=lambda n: n.created_at, reverse=True)[:limit]
    def status_counts(self):
        out: dict = {}
        for n in self.s.notifications.values():
            out.setdefault(n.channel, {}).setdefault(n.status, 0)
            out[n.channel][n.status] += 1
        return out
    def unread_count(self, uid): return sum(1 for n in self.s.notifications.values() if n.user_id == uid and n.read_at is None and n.channel == "in_app")
    def get_preferences(self, uid): return self.s.prefs.get(uid)
    def save_preferences(self, p): self.s.prefs[p.user_id] = p


class MemJobs:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add_if_absent(self, j):
        ex = next((x for x in self.s.jobs.values() if x.idempotency_key == j.idempotency_key), None)
        if ex:
            return ex, False
        self.s.jobs[j.id] = j
        return j, True

    def get(self, i): return self.s.jobs.get(i)
    def update(self, j): self.s.jobs[j.id] = j
    def list_orphans(self, older_than, limit=100):
        return [j for j in self.s.jobs.values() if (j.status == "pending" and j.updated_at <= older_than) or (j.status in ("queued", "retrying") and j.run_at <= older_than and j.updated_at <= older_than)][:limit]
    def counts_by_status(self):
        out: dict[str, int] = {}
        for j in self.s.jobs.values():
            out[j.status] = out.get(j.status, 0) + 1
        return out
    def list_recent(self, limit=50, status=None): return sorted((j for j in self.s.jobs.values() if status is None or j.status == status), key=lambda j: j.created_at, reverse=True)[:limit]


class MemSimple:
    """profiles / consent / drafts / anomalies / investigations / conversations."""

    def __init__(self, s: Stores) -> None:
        self.s = s

    # profiles
    def get(self, key): return self.s.profiles.get(key)
    def save(self, p): self.s.profiles[p.user_id] = p


class MemConsent:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, c): self.s.consent.append(c)
    def latest_by_purpose(self, uid):
        out: dict[str, ConsentRecord] = {}
        for c in sorted((c for c in self.s.consent if c.user_id == uid), key=lambda c: c.at):
            out[c.purpose] = c
        return out
    def history(self, uid): return [c for c in self.s.consent if c.user_id == uid]


class MemDrafts:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def get_by_client_request(self, uid, crid): return next((d for d in self.s.drafts.values() if d.user_id == uid and d.client_request_id == crid), None)
    def get(self, i): return self.s.drafts.get(i)
    def save(self, d): self.s.drafts[d.id] = d
    def list_for_user(self, uid, kind=None): return [d for d in self.s.drafts.values() if d.user_id == uid and (kind is None or d.kind == kind)]
    def delete(self, i): self.s.drafts.pop(i, None)


class MemAnomalies:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add_if_new(self, a):
        if any(x.dedupe_key == a.dedupe_key and x.status == "open" for x in self.s.anomalies.values()):
            return False
        self.s.anomalies[a.id] = a
        return True
    def list(self, *, status=None, department_code=None, limit=100):
        rows = [a for a in self.s.anomalies.values() if (status is None or a.status == status) and (department_code is None or a.department_code == department_code)]
        return sorted(rows, key=lambda a: a.detected_at, reverse=True)[:limit]
    def get(self, i): return self.s.anomalies.get(i)
    def update(self, a): self.s.anomalies[a.id] = a


class MemInvestigations:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, i): self.s.investigations[i.id] = i
    def get(self, i): return self.s.investigations.get(i)
    def update(self, i): self.s.investigations[i.id] = i
    def list(self, *, department_code=None, limit=100): return [i for i in self.s.investigations.values() if department_code is None or i.department_code == department_code][:limit]


class MemConversations:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add_conversation(self, c): self.s.conversations[c.id] = c
    def get_conversation(self, i): return self.s.conversations.get(i)
    def list_conversations(self, uid, limit=50): return [c for c in self.s.conversations.values() if c.user_id == uid][:limit]
    def add_message(self, m): self.s.messages.append(m)
    def list_messages(self, cid): return [m for m in self.s.messages if m.conversation_id == cid]


class MemConfig:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def departments(self): return list(self.s.departments)
    def routing_rules(self): return list(self.s.rules)
    def sla_policies(self): return list(self.s.sla)
    def wards(self): return list(self.s.wards)
    def cities(self): return list(self.s.cities)
    def services(self): return list(self.s.services)
    def offices(self): return list(self.s.offices)

    def save_department(self, d):
        self.s.departments = [x for x in self.s.departments if x.code != d.code] + [d]
    def save_routing_rule(self, r):
        self.s.rules = [x for x in self.s.rules if x.id != r.id] + [r]
    def delete_routing_rule(self, rid):
        n = len(self.s.rules)
        self.s.rules = [x for x in self.s.rules if x.id != rid]
        return len(self.s.rules) < n
    def save_sla_policy(self, p):
        self.s.sla = [x for x in self.s.sla if x.id != p.id] + [p]
    def delete_sla_policy(self, pid):
        n = len(self.s.sla)
        self.s.sla = [x for x in self.s.sla if x.id != pid]
        return len(self.s.sla) < n
    def save_ward(self, w): self.s.wards = [x for x in self.s.wards if x.code != w.code] + [w]
    def save_city(self, c): self.s.cities = [x for x in self.s.cities if x.code != c.code] + [c]
    def save_service(self, v): self.s.services = [x for x in self.s.services if x.code != v.code] + [v]
    def save_office(self, o): self.s.offices = [x for x in self.s.offices if x.id != o.id] + [o]


class MemAudit:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, e): self.s.audit.append(e)
    def query(self, *, action_prefix=None, actor_id=None, resource_id=None, since=None, limit=100):
        rows = [e for e in self.s.audit if (not action_prefix or e.action.startswith(action_prefix)) and (actor_id is None or e.actor_id == actor_id)
                and (resource_id is None or e.resource_id == resource_id) and (since is None or e.occurred_at >= since)]
        return sorted(rows, key=lambda e: e.occurred_at, reverse=True)[:limit]


class MemDict:
    """Generic dict-backed repo for users/sessions/resets/mfa/rti (looked up by attribute so rollback restores it)."""

    def __init__(self, s: Stores, name: str) -> None:
        self._s, self._n = s, name

    @property
    def d(self) -> dict:
        return getattr(self._s, self._n)

    def add(self, x): self.d[getattr(x, "id", None) or getattr(x, "token_hash", None)] = x
    def get(self, k): return self.d.get(k)
    def update(self, x): self.add(x)
    def get_by_id(self, k): return self.d.get(k)
    def save(self, r): self.d[r.user_id] = r
    def delete(self, k): self.d.pop(k, None)
    def get_by_token_hash(self, h): return next((x for x in self.d.values() if getattr(x, "token_hash", None) == h), None)
    def mark_used(self, token_hash, at):
        from app.services.auth_service import ResetTokenRecord

        r = self.d[token_hash]
        self.d[token_hash] = ResetTokenRecord(r.token_hash, r.user_id, r.expires_at, at)
    def get_by_email(self, email): return next((u for u in self.d.values() if getattr(u, "email", None) == email), None)
    def count_with_role(self, role): return sum(1 for u in self.d.values() if getattr(u, "role", None) is role)
    def list(self, *, role=None, limit=100, offset=0): return [u for u in self.d.values() if role is None or u.role is role][offset : offset + limit]
    def revoke_all_for_user(self, user_id, at):
        for x in self.d.values():
            if getattr(x, "user_id", None) == user_id and getattr(x, "revoked_at", 1) is None:
                x.revoked_at = at
    def list_for_owner(self, owner_id): return [a for a in self.d.values() if a.owner_id == owner_id]
    def list_filed(self): return [a for a in self.d.values() if getattr(a.status, "value", a.status) == "filed"]


class MemDocuments:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, d): self.s.documents[d.id] = d
    def get(self, i): return self.s.documents.get(i)
    def update(self, d): self.s.documents[d.id] = d
    def list_for_owner(self, owner_id, limit=50): return [d for d in self.s.documents.values() if d.owner_id == owner_id][:limit]
    def link(self, doc_id, t, i): pass


class MemAnalytics:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add_snapshot(self, scope, taken_at, metrics): self.s.snapshots.append((scope, taken_at, metrics))
    def latest_snapshot(self, scope): return next((m for sc, _t, m in reversed(self.s.snapshots) if sc == scope), None)
    def list_snapshots(self, scope, since, limit=500): return [(t, m) for sc, t, m in self.s.snapshots if sc == scope and t >= since][:limit]


class MemPush:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def upsert(self, d): self.s.push = [x for x in self.s.push if x.token != d.token] + [d]
    def list_for_user(self, uid): return [d for d in self.s.push if d.user_id == uid]
    def delete(self, token, uid):
        n = len(self.s.push)
        self.s.push = [d for d in self.s.push if not (d.token == token and d.user_id == uid)]
        return len(self.s.push) < n


class MemEmergency:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def list(self, *, active_only=True, city_code=None):
        rows = [c for c in self.s.emergency.values() if (not active_only or c.active) and (city_code is None or c.scope == "national" or c.city_code == city_code)]
        return sorted(rows, key=lambda c: (c.sort_order, c.id))
    def save(self, c): self.s.emergency[c.id] = c
    def delete(self, i): return self.s.emergency.pop(i, None) is not None


class MemDupReviews:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r): self.s.dup_reviews.append(r)
    def list_for_complaint(self, cid): return [r for r in self.s.dup_reviews if r.complaint_id == cid]


class MemWorkflow:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def list_rules(self, *, active_only=False): return sorted((r for r in self.s.wf_rules.values() if not active_only or r.active), key=lambda r: (r.priority, r.id))
    def save_rule(self, r): self.s.wf_rules[r.id] = r
    def delete_rule(self, i): return self.s.wf_rules.pop(i, None) is not None
    def try_record_execution(self, e):
        k = (e.rule_id, e.complaint_id)
        if k in self.s.wf_exec:
            return False
        self.s.wf_exec[k] = e
        return True
    def list_executions(self, *, limit=100): return list(self.s.wf_exec.values())[:limit]


class MemGovernment:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def get(self, cid, platform): return self.s.gov.get((cid, platform))
    def save(self, r): self.s.gov[(r.complaint_id, r.platform)] = r
    def list_for_complaint(self, cid): return [r for (c, _), r in self.s.gov.items() if c == cid]
    def counts_by_state(self):
        out: dict = {}
        for r in self.s.gov.values():
            out[r.state] = out.get(r.state, 0) + 1
        return out


class MemLegal:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r): self.s.legal[r.id] = r
    def get(self, i): return self.s.legal.get(i)
    def list_for_user(self, uid, limit=50): return sorted((r for r in self.s.legal.values() if r.user_id == uid), key=lambda r: r.created_at, reverse=True)[:limit]


class MemMasterData:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r):
        if any(e.id_type == r.id_type and e.id_hash == r.id_hash for e in self.s.external_ids):
            return False
        self.s.external_ids.append(r)
        return True

    def list_for_user(self, uid): return [e for e in self.s.external_ids if e.user_id == uid]
    def remove(self, record_id, uid):
        m = next((e for e in self.s.external_ids if e.id == record_id and e.user_id == uid), None)
        if m is None:
            return False
        self.s.external_ids.remove(m)
        return True


class MemExceptions:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r): self.s.int_exceptions[r.id] = r
    def get(self, i): return self.s.int_exceptions.get(i)
    def update(self, r): self.s.int_exceptions[r.id] = r
    def list(self, *, status=None, limit=100):
        rows = [r for r in self.s.int_exceptions.values() if status is None or r.status == status]
        return sorted(rows, key=lambda r: r.detected_at, reverse=True)[:limit]

    def counts_by_status(self):
        out: dict = {}
        for r in self.s.int_exceptions.values():
            out[r.status] = out.get(r.status, 0) + 1
        return out


class MemExternalLinks:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r): self.s.ext_links[r.id] = r
    def list_for_user(self, uid): return sorted((r for r in self.s.ext_links.values() if r.user_id == uid), key=lambda r: r.created_at, reverse=True)
    def update(self, r):
        if r.id in self.s.ext_links and self.s.ext_links[r.id].user_id == r.user_id:
            self.s.ext_links[r.id] = r

    def remove(self, record_id, uid):
        m = self.s.ext_links.get(record_id)
        if m is None or m.user_id != uid:
            return False
        del self.s.ext_links[record_id]
        return True


class MemCorrections:
    def __init__(self, s: Stores) -> None:
        self.s = s

    def add(self, r): self.s.corrections.append(r)
    def list_recent(self, limit=100): return sorted(self.s.corrections, key=lambda r: r.corrected_at, reverse=True)[:limit]

    def find_similar(self, text, limit=5):
        from app.services.duplicate_service import lexical_similarity

        scored = sorted(((lexical_similarity(text, c.text_snapshot), c) for c in self.s.corrections), key=lambda t: -t[0])
        return [c for score, c in scored[:limit] if score >= 0.2]


class MemoryUow:
    def __init__(self, stores: Stores | None = None) -> None:
        self.s = stores or Stores()
        s = self.s
        self.complaints, self.officers, self.notifications, self.jobs = MemComplaints(s), MemOfficers(s), MemNotifications(s), MemJobs(s)
        self.profiles, self.consent, self.drafts = MemSimple(s), MemConsent(s), MemDrafts(s)
        self.anomalies, self.investigations, self.conversations = MemAnomalies(s), MemInvestigations(s), MemConversations(s)
        self.config, self.audit = MemConfig(s), MemAudit(s)
        self.rti, self.users, self.sessions, self.resets, self.mfa = MemDict(s, "rti"), MemDict(s, "users"), MemDict(s, "sessions"), MemDict(s, "resets"), MemDict(s, "mfa")
        self.voice = MemDict(s, "voice")
        self.documents = MemDocuments(s)
        self.analytics = MemAnalytics(s)
        self.push, self.emergency, self.duplicate_reviews = MemPush(s), MemEmergency(s), MemDupReviews(s)
        self.workflow, self.government, self.legal = MemWorkflow(s), MemGovernment(s), MemLegal(s)
        self.master_data, self.exceptions = MemMasterData(s), MemExceptions(s)
        self.external_links, self.classification_corrections = MemExternalLinks(s), MemCorrections(s)
        self.extras: dict[str, Any] = {}
        self._snap: dict[str, Any] | None = None
        self._committed = False

    def __enter__(self):
        self._snap, self._committed = copy.deepcopy(self.s.__dict__), False
        return self

    def __exit__(self, *exc):
        if not self._committed and self._snap is not None:
            self.s.__dict__.clear()
            self.s.__dict__.update(self._snap)
            # repos hold a reference to the Stores object itself, whose attributes were just replaced
        self._snap = None

    def commit(self): self._committed = True
    def rollback(self): self._committed = False


def uow_factory(stores: Stores):
    return lambda: MemoryUow(stores)


class MemQueueBackend:
    """TEST DOUBLE for the Redis backend: a due-time ordered list."""

    def __init__(self) -> None:
        self.items: list[tuple[datetime, str]] = []
        self.up = True
        self.beats: dict[str, tuple[datetime, dict]] = {}

    def _check(self):
        from app.core.exceptions import DependencyUnavailable

        if not self.up:
            raise DependencyUnavailable("Redis is unreachable.")

    def push(self, job_id, run_at): self._check(); self.items.append((run_at, job_id)); self.items.sort()
    def pop_due(self, now):
        self._check()
        for i, (at, jid) in enumerate(self.items):
            if at <= now:
                self.items.pop(i)
                return jid
        return None
    def depth(self): self._check(); return len(self.items)
    def heartbeat(self, w, now, info): self._check(); self.beats[w] = (now, info)
    def workers(self, now, max_age_seconds=60): self._check(); return {w: {"last_seen": t.isoformat(), **i} for w, (t, i) in self.beats.items() if now - t <= timedelta(seconds=max_age_seconds)}
    def ping(self): return self.up


class RecordingBus:
    """TEST DOUBLE event bus."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def publish(self, event): self.events.append(event)

    def of(self, type_: str): return [e for e in self.events if e.type == type_]


class MemStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, name, data): self.files[name] = data
    def read(self, name): return self.files[name]
    def delete(self, name): self.files.pop(name, None)

