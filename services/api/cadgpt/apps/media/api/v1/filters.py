from __future__ import annotations

import django_filters

from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media


class MediaFilterSet(django_filters.FilterSet):
    """All filtering goes through a FilterSet, never through query-string parsing."""

    kind = django_filters.ChoiceFilter(choices=MediaKind.choices)
    checksum = django_filters.CharFilter(field_name="checksum_sha256", lookup_expr="iexact")

    class Meta:
        model = Media
        fields = ("kind", "checksum")
