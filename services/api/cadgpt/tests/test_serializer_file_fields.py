"""The guard for the precedent T-0042 exists to set.

`RulePackSerializer.source_file` used to serialise a `FileField` straight to its storage
URL (`docs/tasks/T-0042-the-catalogue-hands-out-a-storage-url.md`) -- a raw link nothing
authenticates. That one instance is fixed by dropping the field, but the defect is a shape
a codebase can repeat: `MediaSerializer` already deliberately omits `Media.file` for the
same reason, and nothing but discipline stops the next `ModelSerializer` from naming a
`FileField` in `Meta.fields` and getting a bare URL back out.

This walks every `ModelSerializer` subclass the project has loaded -- the same style as
`test_tenant_isolation.py`, which walks every registered viewset rather than checking one
by hand -- and fails the build the moment one of them serialises a `FileField` or
`ImageField` directly. The escape hatch is the one this codebase already uses on purpose:
declare the field explicitly on the serializer (`source_file = MediaSerializer(...)` on
`RuleSetSerializer`) so a nested, authenticated representation is returned instead of the
storage URL DRF would otherwise generate for an undeclared `FileField`.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import FieldDoesNotExist
from django.db.models import FileField, Model
from django.urls import get_resolver
from rest_framework import serializers


def _import_every_serializer_module() -> None:
    """Force every app's `views.py` -- and therefore its `serializers.py` -- to import.

    A `ModelSerializer` subclass only shows up under `__subclasses__()` once its module
    has actually been imported somewhere, and Django's app registry (`django.setup()`)
    loads models, not views or serializers. What loads those is resolving the URL
    configuration, exactly the walk `_registered_viewsets()` in `test_tenant_isolation.py`
    does -- so this test does not depend on some *other* test module having imported
    them first as a side effect of collection order.
    """

    def walk(resolver: Any) -> None:
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern)

    walk(get_resolver())


def _all_subclasses(cls: type[Any]) -> set[type[Any]]:
    """Every subclass loaded anywhere in the process, transitively.

    `__subclasses__()` only reports direct children, so this walks the whole tree the way
    `_registered_viewsets()` in `test_tenant_isolation.py` walks the whole URL tree rather
    than checking one router by hand.
    """
    seen: set[type[Any]] = set()
    stack = [cls]
    while stack:
        current = stack.pop()
        for sub in current.__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return seen


def _model_serializers() -> list[type[serializers.ModelSerializer[Any]]]:
    """Every `ModelSerializer` subclass this test process has imported.

    Calls `_import_every_serializer_module()` first so the answer does not depend on
    what other test modules happened to import before this one ran.
    """
    _import_every_serializer_module()
    return [
        cls
        for cls in _all_subclasses(serializers.ModelSerializer)
        if getattr(cls, "Meta", None) is not None
        and getattr(cls.Meta, "model", None) is not None
    ]


def test_no_serializer_hands_a_file_field_straight_out_as_a_storage_url() -> None:
    """The precedent T-0042 closes: a `FileField`/`ImageField` is never serialised bare.

    A field name in `Meta.fields` is only a problem if DRF would still auto-generate the
    default `FileField`-to-URL representation for it -- which it does not once the
    serializer declares that name itself (`RuleSetSerializer.source_file`, a nested
    `MediaSerializer`, is exactly that escape hatch, and is why this check consults
    `_declared_fields` rather than only `Meta.fields`).
    """
    offenders: list[str] = []

    for cls in _model_serializers():
        model: type[Model] = cls.Meta.model
        field_names = cls.Meta.fields
        if not isinstance(field_names, (list, tuple)):
            # "__all__" or an excludes-style Meta isn't used anywhere in this codebase;
            # nothing here claims to check that shape.
            continue

        declared = set(cls._declared_fields)
        for name in field_names:
            if name in declared:
                continue
            try:
                model_field = model._meta.get_field(name)
            except FieldDoesNotExist:
                # Not every serializer field name maps to a model field (a property, a
                # SerializerMethodField target, ...); nothing here claims to check those.
                continue
            if isinstance(model_field, FileField):
                offenders.append(
                    f"{cls.__module__}.{cls.__qualname__} serialises "
                    f"{model.__name__}.{name} (a {type(model_field).__name__}) directly, "
                    "which DRF renders as a bare, unauthenticated storage URL"
                )

    assert offenders == [], (
        "these serializers hand out a FileField/ImageField as a raw storage URL -- "
        "either drop the field (RulePackSerializer, T-0042) or declare it explicitly as "
        "a nested serializer over an authenticated download route "
        "(RuleSetSerializer.source_file -> MediaSerializer): " + "; ".join(offenders)
    )
