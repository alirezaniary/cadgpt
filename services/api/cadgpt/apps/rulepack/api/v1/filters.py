from __future__ import annotations

import django_filters

from cadgpt.apps.rulepack.models import RuleSet


class RuleSetFilterSet(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains")
    author = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = RuleSet
        fields = ("name", "author")
