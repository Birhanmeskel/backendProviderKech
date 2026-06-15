"""Driver document upload validation and persistence."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.drivers.models import DriverDocument, DriverProfile
from core.models import User

MAX_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
)


class DocumentUploadError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validate_file(upload: UploadedFile) -> None:
    if upload.size > MAX_BYTES:
        raise DocumentUploadError("File exceeds 5 MB limit.", status_code=400)
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise DocumentUploadError(
            "Unsupported file type. Use JPEG, PNG, WebP, or PDF.",
            status_code=400,
        )


def upsert_document(
    *,
    user: User,
    document_type: str,
    upload: UploadedFile,
) -> DriverDocument:
    if document_type not in {choice.value for choice in DriverDocument.DocumentType}:
        raise DocumentUploadError("Invalid document type.", status_code=400)

    _validate_file(upload)

    doc, _created = DriverDocument.objects.update_or_create(
        user=user,
        document_type=document_type,
        defaults={"file": upload},
    )
    return doc


def mark_documents_complete_if_ready(profile: DriverProfile) -> None:
    uploaded = set(
        DriverDocument.objects.filter(user_id=profile.user_id).values_list(
            "document_type", flat=True
        )
    )
    if DriverDocument.REQUIRED_TYPES.issubset(uploaded) and not profile.documents_submitted_at:
        profile.documents_submitted_at = timezone.now()
        profile.save(update_fields=["documents_submitted_at", "updated_at"])
