"""Serializer bases.

A serializer validates a payload and renders a response. It does not create anything and
does not decide anything: `create()` and `update()` delegate to a service, which is where
the rules live and where a Celery task can reach them too.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers


class ProblemDetailSerializer(serializers.Serializer[Any]):
    """The error body, declared so it appears in the generated OpenAPI schema.

    The field-level errors are declared through `Meta` rather than as an attribute named
    `errors`, because `Serializer.errors` is already a property on the base class and
    shadowing it would break validation on any serializer that inherited this one.
    """

    type = serializers.CharField()
    status = serializers.IntegerField()
    code = serializers.CharField()
    detail = serializers.CharField()
    field_errors = serializers.DictField(required=False, source="errors")
    request_id = serializers.CharField(required=False)
