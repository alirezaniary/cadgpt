from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class MembershipRole(models.TextChoices):
    """What a person may do inside one tenant.

    Roles are ordered by capability and compared through `RANK` below, so a permission
    asks "at least admin?" rather than enumerating every role that qualifies -- which is
    how a newly added role silently fails to be granted something it should have.
    """

    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Administrator")
    MEMBER = "member", _("Member")
    VIEWER = "viewer", _("Viewer")


#: Higher rank means more capability. The only place role precedence is written down.
ROLE_RANK: dict[str, int] = {
    MembershipRole.VIEWER: 0,
    MembershipRole.MEMBER: 10,
    MembershipRole.ADMIN: 20,
    MembershipRole.OWNER: 30,
}
