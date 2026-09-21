import unittest
from datetime import UTC, date, datetime, timedelta

from app.core.authorization import AuthContext, Role
from app.core.exceptions import DependencyUnavailable, PermissionDenied, ValidationFailed
from app.services.classification_service import ClassificationService, RuleClassifier, compute_priority
from app.services.complaint_status import (
    ComplaintStatus as S, TRANSITIONS, apply_transition, build_timeline, can_transition, matches_filter,
)
from app.services.duplicate_service import (
    ComplaintSnapshot, DuplicateDetector, DuplicateReviewService, lexical_similarity,
)
from app.services.location_service import aggregate_hotspots, haversine_m, validate_location
from app.services.reference import generate_reference, is_valid_reference
from app.services.routing_service import AiSuggestion, DepartmentRouter, RoutingRule
from app.services.sla_service import (
    EscalationEngine, SlaCalculator, SlaPolicy, SlaScanner, SlaSubject,
)
from tests.rag.helpers import ScriptedChat

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


class StatusTests(unittest.TestCase):
    def test_happy_path_and_illegal_jumps(self):
        path = [S.SUBMITTED, S.AI_ROUTED, S.ASSIGNED, S.UNDER_REVIEW, S.IN_PROGRESS, S.RESOLVED, S.CLOSED]
        for a, b in zip(path, path[1:]):
            self.assertTrue(can_transition(a, b), (a, b))
        for a, b in [(S.SUBMITTED, S.RESOLVED), (S.CLOSED, S.IN_PROGRESS), (S.REJECTED, S.ASSIGNED), (S.ASSIGNED, S.RESOLVED)]:
            self.assertFalse(can_transition(a, b), (a, b))
        self.assertTrue(all(s in TRANSITIONS for s in S))

    def test_remarks_required_for_reject_resolve_reopen(self):
        with self.assertRaises(ValidationFailed):
            apply_transition("c1", S.UNDER_REVIEW, S.RESOLVED, actor_id="o", actor_label="Officer", remarks="  ", at=T0)
        with self.assertRaises(ValidationFailed):
            apply_transition("c1", S.RESOLVED, S.IN_PROGRESS, actor_id="o", actor_label="Officer", remarks=None, at=T0)
        ev = apply_transition("c1", S.UNDER_REVIEW, S.RESOLVED, actor_id="o", actor_label="Officer", remarks=" Fixed. ", at=T0)
        self.assertEqual((ev.from_status, ev.to_status, ev.remarks, ev.actor_id), (S.UNDER_REVIEW, S.RESOLVED, "Fixed.", "o"))

    def test_illegal_transition_error_lists_allowed(self):
        with self.assertRaises(ValidationFailed) as cm:
            apply_transition("c1", S.SUBMITTED, S.RESOLVED, actor_id=None, actor_label=None, remarks="x", at=T0)
        self.assertIn("ai_routed", cm.exception.details["allowed"])

    def test_timeline_uses_recorded_times_only(self):
        evs = [apply_transition("c", a, b, actor_id="s", actor_label="System", remarks=None, at=T0 + timedelta(hours=i))
               for i, (a, b) in enumerate([(S.SUBMITTED, S.AI_ROUTED), (S.AI_ROUTED, S.ASSIGNED)], start=1)]  # fmt: skip
        tl = build_timeline(S.ASSIGNED, evs)
        self.assertEqual([t.label for t in tl], ["Submitted", "AI Routed", "Assigned", "Under Review", "In Progress", "Resolved"])
        self.assertEqual([t.state for t in tl], ["skipped", "done", "current", "upcoming", "upcoming", "upcoming"])
        self.assertIsNone(tl[0].at)  # never invented: no 'submitted' event was recorded
        self.assertEqual(tl[1].at, T0 + timedelta(hours=1))

    def test_timeline_resolved_and_rejected(self):
        tl = build_timeline(S.RESOLVED, [])
        self.assertEqual(tl[-1].state, "done")
        rej = build_timeline(S.REJECTED, [apply_transition("c", S.SUBMITTED, S.REJECTED, actor_id="o", actor_label=None, remarks="spam", at=T0)])
        self.assertEqual([t.state for t in rej], ["skipped", "rejected"])
        self.assertEqual(rej[-1].at, T0)

    def test_tracker_filters(self):
        self.assertTrue(matches_filter("active", status=S.IN_PROGRESS, complaint_type="municipal"))
        self.assertFalse(matches_filter("active", status=S.CLOSED, complaint_type="municipal"))
        self.assertTrue(matches_filter("resolved", status=S.CLOSED, complaint_type="municipal"))
        self.assertTrue(matches_filter("RTI", status=S.SUBMITTED, complaint_type="rti"))
        self.assertFalse(matches_filter("utility", status=S.SUBMITTED, complaint_type="municipal"))
        with self.assertRaises(ValidationFailed):
            matches_filter("bogus", status=S.SUBMITTED, complaint_type="x")


class ReferenceTests(unittest.TestCase):
    def test_generated_reference_is_valid_unique_and_tamper_evident(self):
        refs = {generate_reference("CL", date(2026, 9, 19)) for _ in range(500)}
        self.assertEqual(len(refs), 500)
        ref = next(iter(refs))
        self.assertTrue(ref.startswith("CL-20260919-"))
        self.assertTrue(is_valid_reference(ref, "CL"))
        self.assertFalse(is_valid_reference(ref, "RTI"))
        alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
        swapped = ref[:-1] + next(c for c in alphabet if c != ref[-1])
        self.assertFalse(is_valid_reference(swapped))
        for bad in ("", "CL-1", "cl-20260919-XXXXXXXX", None):
            self.assertFalse(is_valid_reference(bad))  # type: ignore[arg-type]


class LocationTests(unittest.TestCase):
    def test_valid_and_optional(self):
        v = validate_location(12.9716, "77.5946", " Ward 12 ", "MG Road", "Bengaluru")
        self.assertEqual((v.lat, v.lng, v.ward, v.warnings), (12.9716, 77.5946, "Ward 12", ()))
        none = validate_location()
        self.assertEqual((none.lat, none.lng, none.address), (None, None, None))

    def test_invalid_coordinates(self):
        for lat, lng in [(91, 0.5), (10, 181), ("abc", 5), (10, None), (float("nan"), 5), (0, 0)]:
            with self.assertRaises(ValidationFailed, msg=(lat, lng)):
                validate_location(lat, lng)

    def test_outside_india_warns_but_does_not_invent_or_reject(self):
        v = validate_location(51.5, -0.12)
        self.assertEqual(len(v.warnings), 1)
        self.assertIsNone(v.address)

    def test_ward_length_and_control_chars(self):
        with self.assertRaises(ValidationFailed):
            validate_location(ward="w" * 41)
        self.assertEqual(validate_location(address="a\x00b\nc").address, "abc")

    def test_haversine_known_distance(self):
        d = haversine_m(28.6139, 77.2090, 19.0760, 72.8777)  # Delhi -> Mumbai ~1150 km
        self.assertAlmostEqual(d / 1000, 1148, delta=15)
        self.assertEqual(haversine_m(1, 1, 1, 1), 0.0)
        self.assertIsNone(haversine_m(None, 1, 1, 1))

    def test_hotspots_aggregate_only_real_records_and_filter(self):
        recs = [
            {"id": 1, "lat": 12.9716, "lng": 77.5946, "category": "roads", "ward": "12", "severity": "high"},
            {"id": 2, "lat": 12.9717, "lng": 77.5947, "category": "roads", "ward": "12", "severity": "medium"},
            {"id": 3, "lat": 12.9718, "lng": 77.5946, "category": "water", "ward": "12", "severity": "low"},
            {"id": 4, "lat": 13.10, "lng": 77.70, "category": "roads", "ward": "20", "severity": "critical"},
            {"id": 5, "lat": None, "lng": None, "category": "roads", "ward": "12", "severity": "high"},
        ]
        hs = aggregate_hotspots(recs)
        self.assertEqual(sum(h.count for h in hs), 4)  # id 5 (no coordinates) is skipped, not invented
        top = max(hs, key=lambda h: h.count)
        self.assertEqual((top.count, top.categories, top.wards), (3, {"roads": 2, "water": 1}, {"12": 3}))
        self.assertEqual(sum(h.count for h in aggregate_hotspots(recs, category="roads")), 3)
        self.assertEqual(sum(h.count for h in aggregate_hotspots(recs, ward="20")), 1)
        self.assertEqual([h.count for h in aggregate_hotspots(recs, min_count=2)], [3])
        self.assertEqual(aggregate_hotspots([]), [])
        with self.assertRaises(ValueError):
            aggregate_hotspots(recs, link_distance_m=0)
        self.assertGreaterEqual(hs[0].severity_score, hs[-1].severity_score)

    def test_hotspot_has_no_grid_edge_effect_and_links_chains(self):
        # points straddling what would be a fixed-grid boundary stay together when close
        close = [{"id": i, "lat": 12.97 + i * 0.0001, "lng": 77.59, "category": "roads", "severity": "low"} for i in range(60)]
        # 60 points x ~11 m spacing = 660 m chain, each link <= 200 m -> one cluster
        self.assertEqual([h.count for h in aggregate_hotspots(close)], [60])
        far = close + [{"id": 999, "lat": 12.97, "lng": 77.70, "category": "roads", "severity": "low"}]
        self.assertEqual(sorted(h.count for h in aggregate_hotspots(far)), [1, 60])


class ClassificationTests(unittest.TestCase):
    def test_english_and_hindi_rules(self):
        r = RuleClassifier().classify("Big pothole on main road near school")
        self.assertEqual((r.category, r.near_sensitive_site, r.source), ("roads", True, "rules"))
        self.assertFalse(r.ambiguous)
        h = RuleClassifier().classify("सड़क पर बड़ा गड्ढा है")
        self.assertEqual(h.category, "roads")
        self.assertEqual(RuleClassifier().classify("घर के सामने कचरा जमा है").category, "sanitation")

    def test_severity_and_safety(self):
        r = RuleClassifier().classify("Exposed wire sparking near the transformer")
        self.assertEqual((r.category, r.severity, r.affects_safety), ("electricity", "critical", True))

    def test_no_match_is_other_low_confidence_ambiguous(self):
        r = RuleClassifier().classify("Something strange happened yesterday")
        self.assertEqual((r.category, r.confidence, r.ambiguous), ("other", 0.0, True))

    def test_tie_is_ambiguous(self):
        r = RuleClassifier().classify("pothole and garbage")
        self.assertTrue(r.ambiguous)

    def test_llm_consulted_only_when_needed_and_validated(self):
        chat = ScriptedChat('{"category": "water", "severity": "medium", "confidence": 0.8, "reason": "supply"}')
        svc = ClassificationService(chat)
        clear = svc.classify("Pothole", "Big pothole pothole road damaged")
        self.assertEqual(chat.calls, [])
        self.assertEqual((clear.category, clear.ai_status), ("roads", "not_needed"))
        vague = svc.classify("Help", "Something is wrong at home")
        self.assertEqual((vague.category, vague.source, vague.ai_status), ("water", "llm", "ok"))

    def test_llm_failure_modes_keep_rules_result_and_say_so(self):
        for reply, status in [(DependencyUnavailable("down"), "unavailable"), ('{"category":"martians","severity":"low"}', "rejected_output"), ("not json", "rejected_output")]:
            r = ClassificationService(ScriptedChat(reply)).classify("Help", "Something is wrong at home")
            self.assertEqual((r.source, r.ai_status), ("rules", status))
        self.assertEqual(ClassificationService(None).classify("Help", "Something wrong").ai_status, "not_configured")

    def test_model_cannot_downgrade_rule_detected_danger(self):
        chat = ScriptedChat('{"category": "electricity", "severity": "low", "confidence": 0.9, "reason": "x"}')
        r = ClassificationService(chat).classify("Live wire", "live wire and garbage garbage dustbin waste trash")
        self.assertEqual(r.severity, "critical")

    def test_priority_factors_are_explained(self):
        p = compute_priority("high", affects_safety=True, near_sensitive_site=True, duplicate_count=3)
        self.assertEqual(p["priority"], "critical")
        self.assertEqual(len(p["factors"]), 4)
        self.assertEqual(compute_priority("low", affects_safety=False, near_sensitive_site=False)["priority"], "low")


class RoutingTests(unittest.TestCase):
    DEPTS = frozenset({"roads", "water", "electricity"})

    def router(self, *rules):
        return DepartmentRouter(list(rules), self.DEPTS)

    def cls(self, cat="roads", sev="medium"):
        c = RuleClassifier().classify("x")
        c.category, c.severity = cat, sev
        return c

    def test_rule_priority_and_conditions(self):
        r = self.router(
            RoutingRule("generic", 50, "roads", categories=frozenset({"roads"})),
            RoutingRule("ward7-bridge", 10, "water", categories=frozenset({"roads"}), wards=frozenset({"7"}), keywords_any=("bridge",)),
        )  # fmt: skip
        d = r.route(self.cls(), "crack on bridge", ward="7")
        self.assertEqual((d.department_code, d.source, d.rule_id), ("water", "rule", "ward7-bridge"))
        d2 = r.route(self.cls(), "crack on bridge", ward="8")
        self.assertEqual(d2.rule_id, "generic")

    def test_inactive_and_empty_rules_never_match(self):
        r = self.router(RoutingRule("off", 1, "roads", categories=frozenset({"roads"}), active=False), RoutingRule("empty", 2, "water"))
        self.assertEqual(r.route(self.cls(), "x").source, "unrouted")

    def test_severity_condition(self):
        r = self.router(RoutingRule("crit", 1, "electricity", min_severity="high"))
        self.assertEqual(r.route(self.cls(sev="critical"), "x").department_code, "electricity")
        self.assertEqual(r.route(self.cls(sev="medium"), "x").source, "unrouted")

    def test_ai_fallback_only_when_no_rule_and_valid(self):
        r = self.router(RoutingRule("w", 1, "water", categories=frozenset({"water"})))
        ok = r.route(self.cls("other"), "x", ai=AiSuggestion("roads", 0.8, "pothole mention"))
        self.assertEqual((ok.department_code, ok.source), ("roads", "ai_fallback"))
        for ai in (AiSuggestion("ministry_of_magic", 0.99, "?"), AiSuggestion("roads", 0.2, "?"), None):
            d = r.route(self.cls("other"), "x", ai=ai)
            self.assertEqual((d.department_code, d.source, d.needs_manual_triage), (None, "unrouted", True))

    def test_ai_never_overrides_rule_but_disagreement_is_recorded(self):
        r = self.router(RoutingRule("w", 1, "water", categories=frozenset({"water"})))
        d = r.route(self.cls("water"), "x", ai=AiSuggestion("roads", 0.95, "guess"))
        self.assertEqual((d.department_code, d.source), ("water", "rule"))
        self.assertEqual(d.ai_disagreement["ai_department"], "roads")
        agree = r.route(self.cls("water"), "x", ai=AiSuggestion("water", 0.9, "same"))
        self.assertIsNone(agree.ai_disagreement)

    def test_rules_must_reference_known_departments(self):
        with self.assertRaises(ValueError):
            self.router(RoutingRule("bad", 1, "nope", categories=frozenset({"roads"})))


def snap(id_, text, cat="roads", dt=T0, lat=12.9716, lng=77.5946, emb=None):
    return ComplaintSnapshot(id_, f"REF-{id_}", text, cat, dt, lat, lng, emb)


class DuplicateTests(unittest.TestCase):
    det = DuplicateDetector()

    def test_same_issue_nearby_is_possible_duplicate_with_explanation(self):
        a = snap("a", "Large pothole on MG Road near the bus stop causing accidents")
        b = snap("b", "Large pothole on MG Road near bus stop, causing accidents", dt=T0 + timedelta(days=1), lat=12.97165, lng=77.59455)
        m = self.det.compare(a, b)
        self.assertEqual(m.verdict, "possible_duplicate")
        self.assertGreater(m.score, 0.75)
        self.assertIn("same category", m.explanation)
        self.assertIn("m apart", m.explanation)

    def test_gates_far_different_category_or_old(self):
        base = "Large pothole on MG Road near the bus stop causing accidents"
        a = snap("a", base)
        self.assertIsNone(self.det.compare(a, snap("b", base, lat=13.5, lng=78.0)))
        self.assertIsNone(self.det.compare(a, snap("c", base, cat="water")))
        self.assertIsNone(self.det.compare(a, snap("d", base, dt=T0 + timedelta(days=60))))
        self.assertIsNone(self.det.compare(a, snap("e", "Street light not working in sector nine park")))

    def test_missing_components_are_reported_not_faked(self):
        a = snap("a", "Large pothole on MG Road near the bus stop causing accidents", lat=None, lng=None)
        b = snap("b", "Large pothole on MG Road near the bus stop causing accidents", lat=None, lng=None)
        m = self.det.compare(a, b)
        self.assertIsNone(m.components["geo"])
        self.assertIsNone(m.components["semantic"])
        self.assertIn("Not compared", m.explanation)
        self.assertGreater(m.score, 0.9)

    def test_semantic_component_used_when_embeddings_present(self):
        a = snap("a", "pothole road accidents", emb=[1.0, 0.0])
        b = snap("b", "pothole road accidents", emb=[1.0, 0.0])
        self.assertEqual(self.det.compare(a, b).components["semantic"], 1.0)

    def test_find_orders_and_excludes_self_and_limits(self):
        new = snap("n", "Large pothole on MG Road near the bus stop")
        cands = [snap("n", "same"), snap("x1", "Large pothole on MG Road near the bus stop"), snap("x2", "Big pothole MG Road near bus stop"), snap("x3", "Garbage pile behind the market", cat="sanitation")]
        res = self.det.find(new, cands, limit=1)
        self.assertEqual([m.complaint_id for m in res], ["x1"])
        self.assertNotIn("n", [m.complaint_id for m in self.det.find(new, cands)])

    def test_lexical_similarity_bounds(self):
        self.assertAlmostEqual(lexical_similarity("same words here", "same words here"), 1.0)
        self.assertLess(lexical_similarity("pothole road", "water tap leak"), 0.2)

    def test_review_requires_permission_access_and_valid_decision_and_persists(self):
        class Repo:
            rows: list = []
            def add(self, r): self.rows.append(r)
        repo = Repo()
        svc = DuplicateReviewService(repo)
        off = AuthContext("o1", Role.OFFICER, "roads")
        args = dict(complaint_id="a", complaint_owner="citizen", complaint_department="roads", other_complaint_id="b", note=" same ", at=T0)
        rec = svc.record(off, decision="confirmed_duplicate", **args)
        self.assertEqual((rec.reviewer_id, rec.note, len(repo.rows)), ("o1", "same", 1))
        for ctx, kw in [
            (AuthContext("c", Role.CITIZEN), {}),
            (AuthContext("o2", Role.OFFICER, "water"), {}),
        ]:
            with self.assertRaises(PermissionDenied):
                svc.record(ctx, decision="related", **{**args, **kw})
        with self.assertRaises(ValidationFailed):
            svc.record(off, decision="merge_and_delete", **args)
        with self.assertRaises(ValidationFailed):
            svc.record(off, decision="related", **{**args, "other_complaint_id": "a"})
        self.assertEqual(len(repo.rows), 1)


POLICIES = [
    SlaPolicy("high-default", "high", 72, escalation_gap_hours=48, max_level=3),
    SlaPolicy("high-roads", "high", 24, department_code="roads"),
    SlaPolicy("low-default", "low", 240),
]


def subj(status=S.IN_PROGRESS, priority="high", dept="water", created=T0, level=0, esc=None, due=None):
    return SlaSubject("c1", priority, dept, status, created, due, level, esc)


class SlaTests(unittest.TestCase):
    calc = SlaCalculator(POLICIES)

    def test_policy_selection_specific_beats_default(self):
        self.assertEqual(self.calc.policy_for("high", "roads").id, "high-roads")
        self.assertEqual(self.calc.policy_for("high", "water").id, "high-default")
        self.assertIsNone(self.calc.policy_for("critical", "water"))
        self.assertEqual(self.calc.due_at(T0, "high", "roads"), T0 + timedelta(hours=24))
        self.assertIsNone(self.calc.due_at(T0, "critical", "water"))

    def test_status_progression(self):
        s = subj()
        self.assertEqual(self.calc.status(s, T0 + timedelta(hours=10)).state, "on_track")
        at_risk = self.calc.status(s, T0 + timedelta(hours=60))
        self.assertEqual(at_risk.state, "at_risk")
        self.assertEqual(at_risk.remaining, timedelta(hours=12))
        self.assertEqual(self.calc.status(s, T0 + timedelta(hours=73)).state, "breached")
        self.assertEqual(self.calc.status(subj(status=S.RESOLVED), T0 + timedelta(days=99)).state, "finished")
        self.assertEqual(self.calc.status(subj(priority="critical"), T0).state, "no_policy")

    def test_explicit_due_date_wins(self):
        s = subj(due=T0 + timedelta(hours=5))
        self.assertEqual(self.calc.status(s, T0 + timedelta(hours=6)).state, "breached")

    def test_escalation_ladder_is_idempotent_and_timed(self):
        eng = EscalationEngine(self.calc)
        due = T0 + timedelta(hours=72)
        self.assertIsNone(eng.evaluate(subj(), due - timedelta(minutes=1)))
        first = eng.evaluate(subj(), due + timedelta(minutes=1))
        self.assertEqual((first.from_level, first.to_level), (0, 1))
        after_first = subj(level=1, esc=first.at)
        self.assertIsNone(eng.evaluate(after_first, first.at + timedelta(hours=47)))  # not yet
        second = eng.evaluate(after_first, first.at + timedelta(hours=48))
        self.assertEqual(second.to_level, 2)
        self.assertEqual(eng.evaluate(after_first, first.at + timedelta(hours=48)), second)  # same input, same output
        self.assertIsNone(eng.evaluate(subj(level=3, esc=T0), T0 + timedelta(days=90)))  # ladder exhausted
        self.assertIsNone(eng.evaluate(subj(status=S.RESOLVED), T0 + timedelta(days=90)))

    def test_scanner_report(self):
        subjects = [
            SlaSubject("ok", "high", "water", S.ASSIGNED, T0),
            SlaSubject("risk", "high", "water", S.ASSIGNED, T0 - timedelta(hours=60)),
            SlaSubject("late", "high", "water", S.ASSIGNED, T0 - timedelta(hours=100)),
            SlaSubject("done", "high", "water", S.CLOSED, T0 - timedelta(hours=999)),
            SlaSubject("nopol", "critical", "water", S.ASSIGNED, T0 - timedelta(hours=999)),
        ]
        rep = SlaScanner(self.calc).scan(subjects, T0)
        self.assertEqual((rep.at_risk, rep.breached), (["risk"], ["late"]))
        self.assertEqual([(a.complaint_id, a.to_level) for a in rep.actions], [("late", 1)])

    def test_policy_validation(self):
        for kw in ({"resolution_hours": 0}, {"approaching_fraction": 1.5}, {"max_level": 0}):
            with self.assertRaises(ValueError):
                SlaPolicy("x", "high", **{"resolution_hours": 10, **kw})


if __name__ == "__main__":
    unittest.main()
