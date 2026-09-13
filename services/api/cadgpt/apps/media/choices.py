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
    #: Enforced, not just documented: `UPLOADABLE_KINDS` below excludes it, and
    #: `MediaUploadSerializer.kind` is restricted to that set (T-0054) -- a client
    #: `POST`ing `kind=report` is refused at validation, before `MediaService` ever
    #: sees it.
    REPORT = "report", _("Generated report")


#: Kinds a tenant may upload through `POST /api/v1/media/`. Every `MediaKind` reaches
#: storage through `MediaService.store` -- the generator calls it directly with
#: `kind=MediaKind.REPORT` the same way an upload calls it with `IFC_MODEL` or
#: `IDS_RULESET` -- but only this subset may originate from a client request.
UPLOADABLE_KINDS: tuple[MediaKind, ...] = tuple(
    kind for kind in MediaKind if kind != MediaKind.REPORT
)
