from __future__ import annotations

import django_filters

from cadgpt.apps.review.choices import CheckRunStatus, OutcomeStatus
from cadgpt.apps.review.models import CheckRun, Review


class ReviewFilterSet(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains")
    rule_set = django_filters.UUIDFilter(field_name="rule_set__uuid")
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )

    class Meta:
        model = Review
        fields = ("name", "rule_set", "created_after")


class CheckRunFilterSet(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=CheckRunStatus.choices)
    outcome = django_filters.ChoiceFilter(choices=OutcomeStatus.choices)

    class Meta:
        model = CheckRun
        fields = ("status", "outcome")
