from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.drivers.models import DriverDocument, DriverProfile
from apps.drivers.permissions import HasDriverOnboardingToken
from apps.drivers.services.documents import DocumentUploadError, mark_documents_complete_if_ready, upsert_document
from core.models import User

from .serializers import DriverStatusSerializer


class DriverOnboardingStatusView(APIView):
    """
    GET /api/v1/drivers/onboarding/status/

    Uses X-Registration-Token (pending drivers cannot obtain JWT).
    """

    permission_classes = [HasDriverOnboardingToken]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_driver_onboarding"

    def get(self, request, *args, **kwargs):
        user = get_object_or_404(User, pk=request.onboarding_user_id, role=User.Role.DRIVER)
        profile = get_object_or_404(DriverProfile, user=user)
        return Response(DriverStatusSerializer(profile).data)


class DriverDocumentUploadView(APIView):
    """
    POST /api/v1/drivers/onboarding/documents/

    multipart: document_type, file
  Header: X-Registration-Token
    """

    permission_classes = [HasDriverOnboardingToken]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_driver_onboarding"

    def post(self, request, *args, **kwargs):
        document_type = request.data.get("document_type")
        upload = request.data.get("file")
        if not document_type or upload is None:
            return Response(
                {"detail": "Fields 'document_type' and 'file' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_object_or_404(User, pk=request.onboarding_user_id, role=User.Role.DRIVER)
        profile = get_object_or_404(DriverProfile, user=user)

        try:
            doc = upsert_document(user=user, document_type=str(document_type), upload=upload)
        except DocumentUploadError as exc:
            return Response({"detail": exc.message}, status=exc.status_code)

        mark_documents_complete_if_ready(profile)

        return Response(
            {
                "message": "Document uploaded successfully.",
                "document_type": doc.document_type,
                "uploaded_at": doc.uploaded_at,
            },
            status=status.HTTP_201_CREATED,
        )


class DriverRequiredDocumentsView(APIView):
    """GET /api/v1/drivers/onboarding/documents/required/ — lists required + uploaded types."""

    permission_classes = [HasDriverOnboardingToken]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_driver_onboarding"

    def get(self, request, *args, **kwargs):
        user_id = request.onboarding_user_id
        uploaded = list(
            DriverDocument.objects.filter(user_id=user_id).values_list("document_type", flat=True)
        )
        return Response(
            {
                "required": sorted(DriverDocument.REQUIRED_TYPES),
                "uploaded": uploaded,
                "optional": [DriverDocument.DocumentType.PROFILE_PHOTO],
            }
        )
