"""Tenancy: who a row belongs to, and who may see it.

One backend instance serves many independent firms. Their models are unpublished work and
must never meet. Isolation here is a foreign key plus a scoped queryset, enforced in the
code path rather than by the database -- see `docs/decisions.md`, and see
`tests/test_tenant_isolation.py`, which is the guard that makes it real.
"""
