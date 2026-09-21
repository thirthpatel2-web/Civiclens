import io
import unittest
from datetime import UTC, datetime, timedelta

from app.core.authorization import AuthContext, Role
from app.core.exceptions import NotConfigured, NotFound, PermissionDenied, ValidationFailed
from app.services.reference import is_valid_reference
from app.services.rti_service import (
    RtiApplication, RtiDraft, RtiRules, RtiService, RtiStatus, due_reminders, render_pdf,
)
from tests.support import FakeClock

CIT = AuthContext("c1", Role.CITIZEN)
OTHER = AuthContext("c2", Role.CITIZEN)


def draft(**kw):
    base = dict(subject="Road repair expenditure Ward 12", public_authority="Public Works Department, City Corporation",
                questions=("Provide the sanctioned amount for road repair in Ward 12 for 2025-26.", "Provide the work order numbers."),
                applicant_name="Asha Rao", applicant_address="12, 3rd Cross, Jayanagar, Bengaluru 560011")  # fmt: skip
    base.update(kw)
    return RtiDraft(**base)


class Repo:
    def __init__(self):
        self.rows = {}
    def add(self, a): self.rows[a.id] = a
    def get(self, i): return self.rows.get(i)
    def update(self, a): self.rows[a.id] = a


class RtiTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.repo = Repo()
        self.svc = RtiService(self.repo, RtiRules(), self.clock)

    def test_rules_defaults_and_config_override(self):
        r = RtiRules()
        t = datetime(2026, 1, 1, tzinfo=UTC)
        self.assertEqual(r.deadline(t, life_or_liberty=False), t + timedelta(days=30))
        self.assertEqual(r.deadline(t, life_or_liberty=True), t + timedelta(hours=48))
        self.assertEqual(RtiRules(response_days=45).deadline(t, life_or_liberty=False), t + timedelta(days=45))

    def test_validation_reports_each_field(self):
        with self.assertRaises(ValidationFailed) as cm:
            self.svc.create(CIT, draft(subject="x", questions=("  ",), applicant_name="", applicant_address="short"))
        self.assertEqual(set(cm.exception.details), {"subject", "questions", "applicant_name", "applicant_address"})
        with self.assertRaises(ValidationFailed):
            self.svc.create(CIT, draft(questions=tuple(f"q{i}" * 3 for i in range(21))))

    def test_create_generate_file_track_full_flow(self):
        app = self.svc.create(CIT, draft(purpose="Public interest"))
        self.assertEqual((app.status, app.reference), (RtiStatus.DRAFT, None))
        app = self.svc.generate(CIT, app.id)
        self.assertEqual(app.status, RtiStatus.GENERATED)
        self.assertTrue(is_valid_reference(app.reference, "RTI"))
        txt = app.generated_text
        for needle in ("Section 6(1) of the Right to Information Act, 2005", "1. Provide the sanctioned amount", "2. Provide the work order numbers.",
                       "within 30 days (Section 7(1))", "Sections 8 and 9", "Asha Rao", app.reference, "Section 6(2)"):  # fmt: skip
            self.assertIn(needle, txt)
        self.assertEqual(self.svc.track(CIT, app.id)[1].state, "not_started")
        self.clock.advance(hours=1)
        app = self.svc.mark_filed(CIT, app.id)
        self.assertEqual((app.status, app.due_at, app.deadline_is_estimate), (RtiStatus.FILED, self.clock.now + timedelta(days=30), True))
        _, cd = self.svc.track(CIT, app.id)
        self.assertEqual((cd.state, cd.days_remaining, cd.is_estimate), ("running", 30, True))
        self.clock.advance(days=29, hours=1)
        self.assertEqual(self.svc.track(CIT, app.id)[1].days_remaining, 0)
        self.assertEqual(self.svc.track(CIT, app.id)[1].state, "due_today")
        self.clock.advance(days=2)
        cd = self.svc.track(CIT, app.id)[1]
        self.assertEqual(cd.state, "overdue")
        self.assertLess(cd.hours_remaining, 0)
        self.svc.mark_responded(CIT, app.id)
        self.assertEqual(self.svc.track(CIT, app.id)[1].state, "answered")

    def test_life_or_liberty_uses_48_hours_and_wording(self):
        app = self.svc.generate(CIT, self.svc.create(CIT, draft(life_or_liberty=True)).id)
        self.assertIn("48 hours", app.generated_text)
        app = self.svc.mark_filed(CIT, app.id)
        self.assertEqual(app.due_at, self.clock.now + timedelta(hours=48))

    def test_recorded_receipt_date_is_not_an_estimate(self):
        app = self.svc.generate(CIT, self.svc.create(CIT, draft()).id)
        self.clock.advance(days=3)
        recv = self.clock.now - timedelta(days=2)
        app = self.svc.mark_filed(CIT, app.id, received_at=recv)
        self.assertEqual((app.due_at, app.deadline_is_estimate), (recv + timedelta(days=30), False))
        with self.assertRaises(ValidationFailed):
            self.svc.mark_filed(CIT, self.svc.generate(CIT, self.svc.create(CIT, draft()).id).id, received_at=self.clock.now + timedelta(days=1))

    def test_bpl_and_fee_wording(self):
        txt = self.svc.generate(CIT, self.svc.create(CIT, draft(below_poverty_line=True)).id).generated_text
        self.assertIn("below the poverty line", txt)
        txt2 = self.svc.generate(CIT, self.svc.create(CIT, draft()).id, fee_note="Fee of Rs. 10 paid by IPO no. 123.").generated_text
        self.assertIn("IPO no. 123", txt2)

    def test_state_machine_and_edit_locking(self):
        app = self.svc.create(CIT, draft())
        with self.assertRaises(ValidationFailed):
            self.svc.mark_filed(CIT, app.id)  # not generated
        with self.assertRaises(ValidationFailed):
            self.svc.export_pdf(CIT, app.id)
        self.svc.generate(CIT, app.id)
        self.svc.mark_filed(CIT, app.id)
        with self.assertRaises(ValidationFailed):
            self.svc.update_draft(CIT, app.id, draft(subject="Changed subject here"))
        with self.assertRaises(ValidationFailed):
            self.svc.generate(CIT, app.id)
        with self.assertRaises(ValidationFailed):
            self.svc.mark_responded(CIT, self.svc.create(CIT, draft()).id)

    def test_editing_generated_draft_resets_text_but_keeps_reference(self):
        app = self.svc.generate(CIT, self.svc.create(CIT, draft()).id)
        ref = app.reference
        app = self.svc.update_draft(CIT, app.id, draft(subject="A different subject line"))
        self.assertEqual((app.status, app.generated_text, app.reference), (RtiStatus.DRAFT, None, ref))
        self.assertEqual(self.svc.generate(CIT, app.id).reference, ref)

    def test_ownership_isolation_and_role(self):
        app = self.svc.create(CIT, draft())
        for fn in (lambda: self.svc.track(OTHER, app.id), lambda: self.svc.generate(OTHER, app.id), lambda: self.svc.export_pdf(OTHER, app.id)):
            with self.assertRaises(NotFound):
                fn()
        with self.assertRaises(NotFound):
            self.svc.track(CIT, "nope")
        with self.assertRaises(PermissionDenied):
            self.svc.create(AuthContext("o", Role.OFFICER, "roads"), draft())

    def test_pdf_export_contains_the_draft_text(self):
        from pypdf import PdfReader

        app = self.svc.generate(CIT, self.svc.create(CIT, draft()).id)
        pdf = self.svc.export_pdf(CIT, app.id)
        self.assertTrue(pdf.startswith(b"%PDF"))
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn(app.reference, text)
        self.assertIn("Right to Information Act", text)
        self.assertIn("Asha Rao", text)

    def test_pdf_with_non_latin_text_refuses_without_font_instead_of_garbling(self):
        with self.assertRaises(NotConfigured):
            render_pdf("सूचना का अधिकार अधिनियम", title="t")

    def test_long_text_paginates(self):
        from pypdf import PdfReader

        pdf = render_pdf("\n".join(f"Line number {i} of a very long RTI application." for i in range(200)), title="t")
        self.assertGreater(len(PdfReader(io.BytesIO(pdf)).pages), 1)

    def test_reminders_fire_once_per_threshold(self):
        rules = RtiRules()
        t = datetime(2026, 1, 1, tzinfo=UTC)
        app = RtiApplication("a", "c1", draft(), RtiStatus.FILED, due_at=t + timedelta(days=30))
        self.assertEqual(due_reminders(app, t, rules), [])
        self.assertEqual(due_reminders(app, t + timedelta(days=23, hours=1), rules), [7])
        app.reminders_sent = (7,)
        self.assertEqual(due_reminders(app, t + timedelta(days=24), rules), [])
        self.assertEqual(due_reminders(app, t + timedelta(days=27, hours=1), rules), [3])
        self.assertEqual(due_reminders(app, t + timedelta(days=31), rules), [])  # overdue: no "days left" reminder
        app.status = RtiStatus.RESPONDED
        self.assertEqual(due_reminders(app, t + timedelta(days=27, hours=1), rules), [])


if __name__ == "__main__":
    unittest.main()
