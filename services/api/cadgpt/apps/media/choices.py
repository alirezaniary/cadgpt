from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class MediaKind(models.TextChoices):
    """What a stored file is for. Decides which extensions and limits apply."""

    IFC_MODEL = "ifc_model", _("IFC model")
    IDS_RULESET = "ids_ruleset", _("IDS rule set")
    #: A generated Markdown report (T-0032). Written by the server, never uploaded --
    #: stored through the same tenant-scoped path as everything else here so a
    #: generated artifact is subject to the same isolation as an upload.
    REPORT = "report", _("Generated report")
