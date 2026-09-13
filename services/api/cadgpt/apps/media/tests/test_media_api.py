"""What `POST /api/v1/media/` will and will not accept."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_an_ifc_upload_succeeds(api: APIClient) -> None:
    response = api.post(
        "/api/v1/media/",
        {
            "kind": "ifc_model",
            "file": SimpleUploadedFile("model.ifc", b"ISO-10303-21;\nENDSEC;\n"),
        },
        format="multipart",
    )
    assert response.status_code == 201, response.data
    assert response.data["kind"] == "ifc_model"


def test_a_report_kind_upload_is_refused(api: APIClient) -> None:
    """T-0054: `report` is a real `MediaKind`, but it is written only by
    `ReportGenerationService.generate` -- never received from a client. Before this fix,
    `MediaUploadSerializer.kind` accepted every `MediaKind`, including this one, and `.md`
    was an allowed extension, so a tenant could upload arbitrary Markdown labelled
    "Generated report". It can never attach to a run (`report_file` is set only by the
    generator), but nothing refused the upload itself -- this is that refusal.
    """
    response = api.post(
        "/api/v1/media/",
        {
            "kind": "report",
            "file": SimpleUploadedFile("report.md", b"# Not a real report\n"),
        },
        format="multipart",
    )
    assert response.status_code == 400, response.data
    assert response.data["code"] == "validation_error"
    assert "kind" in response.data["errors"]
