"""Tenant lifecycle and membership."""

from __future__ import annotations

from typing import cast

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from cadgpt.apps.base.services import BaseService, BaseTenantAwareService
from cadgpt.apps.tenancy.choices import MembershipRole
from cadgpt.apps.tenancy.models import Membership, Tenant


class TenantProvisioningService(BaseService):
    """Creating a tenant is the one operation that cannot already have one."""

    def create(self, *, name: str, slug: str, owner: User, language: str = "en") -> Tenant:
        """A tenant and its first owner are created together or not at all.

        A tenant with no owner is unreachable by anyone and can only be repaired by hand,
        so the two writes share a transaction.
        """
        try:
            with transaction.atomic():
                tenant = Tenant.objects.create_tenant(
                    name=name, slug=slug, language=language
                )
                Membership.objects.grant(
                    tenant=tenant, user=owner, role=MembershipRole.OWNER
                )
        except IntegrityError as exc:
            raise ConflictError(_("A tenant with this identifier already exists.")) from exc

        self.log.info("tenant_created", tenant_id=str(tenant.uuid), owner=str(owner.uuid))
        return tenant


class MembershipService(BaseTenantAwareService):
    """Who belongs to this tenant, and with what role."""

    def resolve_for(self, user: User) -> Membership:
        """The membership that authorizes `user` here, or a refusal.

        Returned rather than a boolean, because the caller needs the role too and a second
        query to fetch it is a second chance to fetch the wrong one.
        """
        membership = cast(
            "Membership | None",
            Membership.objects.active().in_tenant(self.tenant.pk).of_user(user.pk).first(),
        )
        if membership is None:
            raise PermissionDeniedError(_("You are not a member of this workspace."))
        return membership

    def add(self, *, user: User, role: str, actor_membership: Membership) -> Membership:
        if not actor_membership.has_at_least(MembershipRole.ADMIN):
            raise PermissionDeniedError(_("Only an administrator may add members."))
        if role == MembershipRole.OWNER and not actor_membership.has_at_least(
            MembershipRole.OWNER
        ):
            raise PermissionDeniedError(_("Only an owner may grant ownership."))
        try:
            membership = Membership.objects.grant(tenant=self.tenant, user=user, role=role)
        except IntegrityError as exc:
            raise ConflictError(_("This person is already a member.")) from exc
        self.log.info("membership_granted", user_id=str(user.uuid), role=role)
        return membership

    def revoke(self, *, membership_uuid: str, actor_membership: Membership) -> None:
        if not actor_membership.has_at_least(MembershipRole.ADMIN):
            raise PermissionDeniedError(_("Only an administrator may remove members."))

        membership = (
            Membership.objects.in_tenant(self.tenant.pk)
            .filter(uuid=membership_uuid)
            .first()
        )
        if membership is None:
            raise NotFoundError(_("That membership does not exist."))
        if membership.role == MembershipRole.OWNER:
            remaining = (
                Membership.objects.active()
                .in_tenant(self.tenant.pk)
                .filter(role=MembershipRole.OWNER)
                .exclude(pk=membership.pk)
                .exists()
            )
            if not remaining:
                # A tenant with no owner cannot grant anyone else access to itself.
                raise ConflictError(_("A workspace must keep at least one owner."))

        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        self.log.info("membership_revoked", membership_id=str(membership.uuid))
