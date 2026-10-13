from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


DEFAULT_BUCKET = "insurance-documents"


class InsuranceDocumentStorage:
    def __init__(self, bucket: str | None = None):
        self.bucket = bucket or os.getenv("INSURANCE_DOCUMENTS_BUCKET", DEFAULT_BUCKET)
        self._bucket_checked = False

    @staticmethod
    def _client():
        from risk_monitor.supabase_client import supabase

        return supabase

    @staticmethod
    def safe_file_name(file_name: str) -> str:
        name = Path(file_name or "document").name.strip() or "document"
        return "".join(character for character in name if character not in {"\x00", "/", "\\"})

    def build_path(self, owner_type: str, owner_id: str, file_name: str) -> str:
        suffix = Path(self.safe_file_name(file_name)).suffix.lower()
        return f"{owner_type}/{owner_id}/{uuid4().hex}{suffix}"

    def upload(
        self,
        *,
        path: str,
        content: bytes,
        content_type: str | None,
    ) -> None:
        self.ensure_bucket()
        options = {
            "content-type": content_type or "application/octet-stream",
            "upsert": "false",
        }
        self._client().storage.from_(self.bucket).upload(
            path,
            content,
            file_options=options,
        )

    def ensure_bucket(self) -> None:
        if self._bucket_checked:
            return
        client = self._client()
        try:
            client.storage.get_bucket(self.bucket)
        except Exception:
            try:
                client.storage.create_bucket(
                    self.bucket,
                    options={
                        "public": False,
                        "file_size_limit": 20 * 1024 * 1024,
                    },
                )
            except Exception as exc:
                message = str(exc).lower()
                if "already exists" not in message and "duplicate" not in message:
                    raise
        self._bucket_checked = True

    def remove(self, path: str) -> None:
        self._client().storage.from_(self.bucket).remove([path])

    def download(self, path: str) -> bytes:
        return self._client().storage.from_(self.bucket).download(path)

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        response = self._client().storage.from_(self.bucket).create_signed_url(
            path,
            expires_in,
        )
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signedUrl")
        return None
