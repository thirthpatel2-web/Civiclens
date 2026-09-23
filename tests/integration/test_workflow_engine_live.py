"""The residence_certificate_verification workflow definition, executed by the real
WorkflowEngine against real seeded demo data in a live database - proof the engine genuinely
drives the no-reupload scenario as stored, executable steps (Section 12), not just that the
generic engine's control flow works in isolation (see tests/unit/test_workflow_engine.py for
that). Skips cleanly if no live database is reachable.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.core.config import Settings
from app.db.models.identity import UserModel
from app.db.models.interop_platform import (
    InteropConsentGrant,
    MasterEntity,
    MasterIdentifier,
    MockDeptADocument,
    MockDeptAResident,
    MockDeptBApplication,
    MockDeptBBeneficiary,
    UnifiedApplication,
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.db.session import make_engine, make_session_factory
from app.db.uow import SqlUnitOfWork
from app.interop import connector_registry, mock_systems
from app.interop.federation import idp
from app.interop.workflow.definitions import (
    RESIDENCE_CERTIFICATE_VERIFICATION,
    build_residence_certificate_step_registry,
    register_default_workflows,
)
from app.interop.workflow.engine import WorkflowEngine

try:
    _engine = make_engine(Settings.load())
    with _engine.connect():
        pass
    _DB_AVAILABLE = True
    _SKIP_REASON = ""
except Exception as exc:  # noqa: BLE001
    _DB_AVAILABLE = False
    _SKIP_REASON = f"no live database available for this integration test: {exc}"


@unittest.skipUnless(_DB_AVAILABLE, _SKIP_REASON)
class WorkflowEngineLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session_factory = make_session_factory(_engine)
        self.uow_factory = lambda: SqlUnitOfWork(self.session_factory)
        self._suffix = uuid.uuid4().hex[:8]
        self.resident_id = f"TEST-WF-A-{self._suffix}"
        self.beneficiary_code = f"TEST-WF-B-{self._suffix}"
        self.application_no = f"TEST-WF-APP-{self._suffix}"
        self.reference_no = f"TESTREF-WF-{self._suffix}"
        self._created_master_ids: set[str] = set()

        now = datetime.now(UTC)
        with self.uow_factory() as uow:
            s = uow.session
            mock_systems.seed_if_empty(s)
            connector_registry.seed_if_empty(s)
            idp.seed_if_empty(s)
            register_default_workflows(s)
            s.add(MockDeptAResident(resident_id=self.resident_id, full_name="Workflow Test Citizen", mobile="9800011122", address="1 Workflow Rd", city="Pune", state="Maharashtra", created_at=now))
            s.flush()
            s.add(MockDeptADocument(document_id=str(uuid.uuid4()), resident_id=self.resident_id, document_type="residence_certificate", status="verified", reference_no=self.reference_no, issued_on=now, created_at=now))
            s.add(MockDeptBBeneficiary(beneficiary_code=self.beneficiary_code, full_name="Workflow Test Citizen", mobile_number="9800011122", created_at=now))
            s.flush()
            s.add(MockDeptBApplication(application_no=self.application_no, beneficiary_code=self.beneficiary_code, service_type="Small Business Registration", status="pending_document", required_document_type="residence_certificate", document_status="missing", created_at=now, updated_at=now))
            user = UserModel(id=str(uuid.uuid4()), email=f"workflow-test-{self._suffix}@example.invalid", password_hash="x", full_name="Workflow Test Actor", role="admin", is_active=True, created_at=now)
            s.add(user)
            uow.commit()
            self.user_id = user.id

    def tearDown(self) -> None:
        with self.uow_factory() as uow:
            s = uow.session
            executions = list(s.execute(select(WorkflowExecution).where(WorkflowExecution.correlation_id == self.application_no)).scalars().all())
            for execution in executions:
                s.execute(delete(WorkflowStepExecution).where(WorkflowStepExecution.execution_id == execution.execution_id))
            s.execute(delete(WorkflowExecution).where(WorkflowExecution.correlation_id == self.application_no))
            unified = s.execute(select(UnifiedApplication).where(UnifiedApplication.external_reference == self.application_no)).scalars().first()
            if unified is not None:
                s.execute(delete(UnifiedApplication).where(UnifiedApplication.application_id == unified.application_id))
            if self._created_master_ids:
                s.execute(delete(InteropConsentGrant).where(InteropConsentGrant.master_id.in_(self._created_master_ids)))
                s.execute(delete(MasterIdentifier).where(MasterIdentifier.master_id.in_(self._created_master_ids)))
                s.execute(delete(MasterEntity).where(MasterEntity.master_id.in_(self._created_master_ids)))
            s.execute(delete(MockDeptADocument).where(MockDeptADocument.resident_id == self.resident_id))
            s.execute(delete(MockDeptAResident).where(MockDeptAResident.resident_id == self.resident_id))
            s.execute(delete(MockDeptBApplication).where(MockDeptBApplication.application_no == self.application_no))
            s.execute(delete(MockDeptBBeneficiary).where(MockDeptBBeneficiary.beneficiary_code == self.beneficiary_code))
            s.execute(delete(UserModel).where(UserModel.id == self.user_id))
            uow.commit()

    def test_the_stored_definition_has_the_spec_named_steps_in_order(self) -> None:
        with self.uow_factory() as uow:
            from app.db.models.interop_platform import WorkflowDefinition

            definition = uow.session.get(WorkflowDefinition, RESIDENCE_CERTIFICATE_VERIFICATION)
            self.assertIsNotNone(definition)
            self.assertEqual([s["step_id"] for s in definition.steps], ["resolve_identity", "request_consent", "fetch_document", "validate_document", "transform_data", "deliver_document", "publish_event", "update_tracker", "notify"])

    def test_engine_runs_the_real_no_reupload_flow_end_to_end_with_a_manual_approval_pause(self) -> None:
        engine = WorkflowEngine()
        with self.uow_factory() as uow:
            s = uow.session
            registry = build_residence_certificate_step_registry(s)
            execution = engine.start(s, workflow_id=RESIDENCE_CERTIFICATE_VERIFICATION, correlation_id=self.application_no, context={"application_no": self.application_no, "actor_user_id": self.user_id}, step_registry=registry)
            uow.commit()
            self.assertEqual(execution.status, "waiting_approval")
            self.assertEqual(execution.current_step_index, 1)  # paused at request_consent
            self._created_master_ids.add(execution.context["master_id"])
            execution_id = execution.execution_id

        # Nothing was written to Dept B yet - the pause genuinely happened before any read from Dept A.
        with self.uow_factory() as uow:
            app_row = mock_systems.dept_b_get_application(uow.session, self.application_no)
            self.assertEqual(app_row.document_status, "missing")

        with self.uow_factory() as uow:
            s = uow.session
            registry = build_residence_certificate_step_registry(s)
            resumed = engine.resume(s, execution_id=execution_id, step_registry=registry, approve_step="request_consent")
            uow.commit()
            self.assertEqual(resumed.status, "completed", resumed.context)
            self.assertEqual(resumed.context["document_reference"], self.reference_no)
            self.assertTrue(resumed.context["delivered"])
            self.assertTrue(resumed.context["notified"])

        # The real, no-reupload effect: Dept B's own row was actually updated.
        with self.uow_factory() as uow:
            app_row = mock_systems.dept_b_get_application(uow.session, self.application_no)
            self.assertEqual(app_row.document_status, "verified")
            self.assertEqual(app_row.document_reference, self.reference_no)

        with self.uow_factory() as uow:
            steps = list(uow.session.execute(select(WorkflowStepExecution).where(WorkflowStepExecution.execution_id == execution_id).order_by(WorkflowStepExecution.step_index)).scalars().all())
            completed_step_ids = [row.step_id for row in steps if row.status == "completed"]
            self.assertEqual(completed_step_ids, ["resolve_identity", "request_consent", "fetch_document", "validate_document", "transform_data", "deliver_document", "publish_event", "update_tracker", "notify"])

    def test_a_missing_application_fails_the_execution_with_a_real_recorded_reason(self) -> None:
        engine = WorkflowEngine()
        with self.uow_factory() as uow:
            s = uow.session
            registry = build_residence_certificate_step_registry(s)
            execution = engine.start(s, workflow_id=RESIDENCE_CERTIFICATE_VERIFICATION, correlation_id="no-such-app", context={"application_no": "DOES-NOT-EXIST", "actor_user_id": self.user_id}, step_registry=registry)
            uow.commit()
            self.assertEqual(execution.status, "failed")
            execution_id = execution.execution_id

        with self.uow_factory() as uow:
            steps = list(uow.session.execute(select(WorkflowStepExecution).where(WorkflowStepExecution.execution_id == execution_id)).scalars().all())
            self.assertEqual(len(steps), 1)
            self.assertEqual(steps[0].step_id, "resolve_identity")
            self.assertIn("no application", steps[0].error_message)


if __name__ == "__main__":
    unittest.main()
