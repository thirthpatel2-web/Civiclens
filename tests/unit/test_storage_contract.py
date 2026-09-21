"""One behavioural contract, run against BOTH storage providers (Local for real; Drive against a fake client)."""

import tempfile
import unittest

from app.core.exceptions import NotConfigured, NotFound, ValidationFailed
from app.services.document_service import LocalStorage
from app.storage.providers import GoogleDriveStorageProvider
from tests.workers.test_handlers_providers import _FakeDrive

NAME = "a" * 32 + ".pdf"


def providers():
    tmp = tempfile.TemporaryDirectory()
    drive = GoogleDriveStorageProvider("creds.json", "folder123", service=_FakeDrive(), media_factory=lambda d: d)
    return [("local", LocalStorage(tmp.name), tmp), ("google_drive", drive, None)]


class StorageContractTests(unittest.TestCase):
    def each(self):
        for name, p, keep in providers():
            with self.subTest(provider=name):
                yield name, p
            _ = keep

    def test_same_round_trip_semantics(self):
        for _n, p in self.each():
            p.save(NAME, b"hello")
            self.assertEqual(p.read(NAME), b"hello")
            with self.assertRaises(ValidationFailed):
                p.save(NAME, b"again")  # names are write-once
            p.delete(NAME)
            p.delete(NAME)  # idempotent
            with self.assertRaises((NotFound, KeyError)):
                p.read(NAME)

    def test_same_name_validation(self):
        for _n, p in self.each():
            for bad in ("../etc/passwd", "x.pdf", "A" * 32 + ".pdf", "a" * 32, "a" * 32 + ".p d"):
                with self.assertRaises(ValidationFailed):
                    p.save(bad, b"x")

    def test_health_reports_a_real_round_trip(self):
        for n, p in self.each():
            h = p.health()
            self.assertEqual((h["provider"], h["state"]), (n, "CONNECTED"))
        bad = GoogleDriveStorageProvider("creds.json", "folder123", service=_FakeDrive(fail=True), media_factory=lambda d: d)
        self.assertEqual(bad.health()["state"], "UNAVAILABLE")

    def test_drive_without_credentials_or_folder_is_not_configured(self):
        for args in (("", "folder"), ("creds.json", "")):
            with self.assertRaises(NotConfigured):
                GoogleDriveStorageProvider(*args)


if __name__ == "__main__":
    unittest.main()
