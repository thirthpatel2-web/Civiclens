"""Storage providers behind the ``Storage`` protocol (save/read/delete by server-generated name)."""

from __future__ import annotations

import io
import re
from typing import Any

from app.core.config import Settings
from app.core.exceptions import DependencyUnavailable, NotConfigured, NotFound, ValidationFailed
from app.services.document_service import LocalStorage, Storage

LocalStorageProvider = LocalStorage  # documented name from the architecture; same implementation
_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def _default_media(data: bytes) -> Any:
    from googleapiclient.http import MediaIoBaseUpload

    return MediaIoBaseUpload(io.BytesIO(data), mimetype="application/octet-stream")


class GoogleDriveStorageProvider:
    """Stores files in one Drive folder using a service account.

    Only constructed when ``GOOGLE_DRIVE_ENABLED=true`` and a credentials file exists; otherwise
    ``NotConfigured``. Requires ``google-api-python-client`` and ``google-auth``. NOT exercised in
    this build (no credentials/network): runtime verification is environment-dependent.
    """

    provider_name = "google_drive"

    def health(self) -> dict[str, str]:
        try:
            self._svc.files().list(q=f"'{self._folder}' in parents and trashed = false", fields="files(id)", pageSize=1).execute()
            return {"provider": self.provider_name, "state": "CONNECTED", "detail": "folder reachable"}
        except Exception as exc:
            return {"provider": self.provider_name, "state": "UNAVAILABLE", "detail": type(exc).__name__}

    def __init__(self, credentials_file: str, folder_id: str, service: Any | None = None, media_factory: Any | None = None) -> None:
        if not credentials_file or not folder_id:
            raise NotConfigured("Google Drive storage needs GOOGLE_CREDENTIALS_FILE and GOOGLE_DRIVE_FOLDER_ID.")
        self._folder, self._media = folder_id, media_factory or _default_media
        if service is not None:  # injected in tests
            self._svc = service
            return
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise NotConfigured("Install google-api-python-client and google-auth to use Drive storage.") from exc
        creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=["https://www.googleapis.com/auth/drive.file"])
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    def _check(self, name: str) -> None:
        if not _NAME.match(name):
            raise ValidationFailed("Invalid storage name.")

    def _find(self, name: str) -> str | None:
        res = self._svc.files().list(q=f"name = '{name}' and '{self._folder}' in parents and trashed = false", fields="files(id)", pageSize=1).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def save(self, storage_name: str, data: bytes) -> None:
        self._check(storage_name)
        try:
            if self._find(storage_name):
                raise ValidationFailed("Storage name already exists.")
            media = self._media(data)
            self._svc.files().create(body={"name": storage_name, "parents": [self._folder]}, media_body=media, fields="id").execute()
        except ValidationFailed:
            raise
        except Exception as exc:
            raise DependencyUnavailable(f"Google Drive save failed ({type(exc).__name__}).") from exc

    def read(self, storage_name: str) -> bytes:
        self._check(storage_name)
        try:
            fid = self._find(storage_name)
            if fid is None:
                raise NotFound("File not found.")
            return bytes(self._svc.files().get_media(fileId=fid).execute())
        except NotFound:
            raise
        except Exception as exc:
            raise DependencyUnavailable(f"Google Drive read failed ({type(exc).__name__}).") from exc

    def delete(self, storage_name: str) -> None:
        self._check(storage_name)
        try:
            fid = self._find(storage_name)
            if fid:
                self._svc.files().delete(fileId=fid).execute()
        except Exception as exc:
            raise DependencyUnavailable(f"Google Drive delete failed ({type(exc).__name__}).") from exc


def build_storage(settings: Settings, drive_folder_id: str = "") -> Storage:
    if settings.google_drive_enabled:
        return GoogleDriveStorageProvider(settings.google_credentials_file, drive_folder_id)  # type: ignore[return-value]
    return LocalStorageProvider(settings.upload_dir)
