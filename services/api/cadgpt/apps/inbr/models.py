"""Django projection of the immutable INBR transcript corpus."""

# Nullable text fields mirror the existing PostgreSQL projection contract: absent source
# evidence is distinct from an empty string.
# ruff: noqa: DJ001

from __future__ import annotations

from typing import ClassVar

from django.db import models


class PdfDocument(models.Model):
    document_key = models.CharField(max_length=255, unique=True)
    pdf_name = models.TextField()
    file_path = models.TextField()
    storage_uri = models.TextField(blank=True, null=True)
    volume_number = models.PositiveIntegerField(blank=True, null=True)
    edition_year = models.PositiveIntegerField(blank=True, null=True)
    edition_code = models.CharField(max_length=255)
    title_fa = models.TextField(blank=True, null=True)
    source_sha256 = models.CharField(max_length=64, unique=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    page_count = models.PositiveIntegerField(blank=True, null=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pdf_document"

    def __str__(self) -> str:
        return self.document_key


class PdfPage(models.Model):
    document = models.ForeignKey(
        PdfDocument,
        db_column="document_key",
        on_delete=models.CASCADE,
        to_field="document_key",
        related_name="pages",
    )
    page_key = models.CharField(max_length=255, unique=True)
    pdf_page_number = models.PositiveIntegerField()
    printed_page_label = models.TextField(blank=True, null=True)
    extraction_route = models.CharField(max_length=32, default="pending")
    status = models.CharField(max_length=32, default="pending")
    native_text = models.TextField(blank=True, null=True)
    native_layout_json = models.JSONField(blank=True, null=True)
    native_text_sha256 = models.CharField(max_length=64, blank=True, null=True)
    paddle_text = models.TextField(blank=True, null=True)
    paddle_result_json = models.JSONField(blank=True, null=True)
    paddle_text_sha256 = models.CharField(max_length=64, blank=True, null=True)
    luna_transcript_json = models.JSONField(blank=True, null=True)
    luna_transcript_text = models.TextField(blank=True, null=True)
    luna_transcript_sha256 = models.CharField(max_length=64, blank=True, null=True)
    luna_response_uri = models.TextField(blank=True, null=True)
    luna_response_sha256 = models.CharField(max_length=64, blank=True, null=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pdf_page"
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("document", "pdf_page_number"),
                name="pdf_page_document_page_number_unique",
            ),
        ]
        indexes: ClassVar = [
            models.Index(
                fields=("document", "pdf_page_number"), name="pdf_page_document_page_idx"
            ),
            models.Index(fields=("luna_transcript_sha256",), name="pdf_page_luna_hash_idx"),
        ]

    def __str__(self) -> str:
        return self.page_key


class RuleCandidate(models.Model):
    document = models.ForeignKey(
        PdfDocument,
        db_column="document_key",
        on_delete=models.PROTECT,
        to_field="document_key",
        related_name="rule_candidates",
    )
    primary_page = models.ForeignKey(
        PdfPage,
        db_column="primary_page_key",
        on_delete=models.PROTECT,
        to_field="page_key",
        related_name="rule_candidates",
    )
    candidate_key = models.CharField(max_length=255, unique=True)
    source_record_key = models.TextField()
    source_record_type = models.TextField(blank=True, null=True)
    source_page_ids = models.JSONField(default=list)
    source_text_fa = models.TextField(blank=True, null=True)
    source_text_sha256 = models.CharField(max_length=64, blank=True, null=True)
    transcript_sha256 = models.CharField(max_length=64, blank=True, null=True)
    extraction_file_uri = models.TextField(blank=True, null=True)
    extraction_file_sha256 = models.CharField(max_length=64, blank=True, null=True)
    extraction_json = models.JSONField(default=dict)
    rule_key = models.TextField(blank=True, null=True)
    implementation_type = models.CharField(max_length=32, blank=True, null=True)
    semantic_fingerprint = models.CharField(max_length=64, blank=True, null=True)
    ids_specification = models.JSONField(blank=True, null=True)
    ids_xml_uri = models.TextField(blank=True, null=True)
    ids_xml_sha256 = models.CharField(max_length=64, blank=True, null=True)
    sidecar_uri = models.TextField(blank=True, null=True)
    sidecar_sha256 = models.CharField(max_length=64, blank=True, null=True)
    compiler_version = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=32, default="extracted")
    reason_code = models.TextField(blank=True, null=True)
    validation_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rule_candidate"
        indexes: ClassVar = [
            models.Index(
                fields=("document", "primary_page"), name="rule_candidate_document_idx"
            ),
            models.Index(
                fields=("status", "implementation_type"), name="rule_candidate_status_idx"
            ),
            models.Index(
                fields=("semantic_fingerprint",), name="rule_candidate_fingerprint_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.candidate_key
