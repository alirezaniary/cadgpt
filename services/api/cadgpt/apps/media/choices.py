from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class MediaKind(models.TextChoices):
    """What a stored file is for. Decides which extensions and limits apply."""

    IFC_MODEL = "ifc_model", _("IFC model")
    IDS_RULESET = "ids_ruleset", _("IDS rule set")
