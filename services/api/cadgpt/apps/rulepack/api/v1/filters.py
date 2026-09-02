from __future__ import annotations

import django_filters

from cadgpt.apps.rulepack.models import RulePack, RuleSet


class RuleSetFilterSet(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr="icontains")
    author = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = RuleSet
        fields = ("name", "author")


class RulePackFilterSet(django_filters.FilterSet):
    """Selection filters, per `prd.md` §5.5: a pack is chosen by jurisdiction, region
    and version, not searched by free text.
    """

    jurisdiction = django_filters.CharFilter(lookup_expr="iexact")
    region = django_filters.CharFilter(lookup_expr="iexact")
    version = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = RulePack
        fields = ("jurisdiction", "region", "version")
