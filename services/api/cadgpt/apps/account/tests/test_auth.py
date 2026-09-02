"""Authentication over the real HTTP stack, issuing real tokens.

Written after a bug that every other test missed: the rest of the suite authenticates
with `force_authenticate`, which never issues a token, so a misconfigured token lifetime
type-checked, started cleanly, and failed on the first real sign-in. These tests go
through the actual endpoints so the credential path is exercised the way a browser
exercises it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from cadgpt.apps.account.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_signing_in_issues_a_usable_access_token(client: APIClient, owner: User) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"email": owner.email, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.data
    access = response.data["access"]
    lifetime = cast(timedelta, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])
    assert response.data["expires_in"] == int(lifetime.total_seconds())

    # The token must actually authenticate a subsequent request.
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = client.get("/api/v1/me/")
    assert me.status_code == 200
    assert me.data["email"] == owner.email


def test_the_refresh_token_is_httponly_and_never_in_the_body(
    client: APIClient, owner: User
) -> None:
    """An XSS must not be able to lift a credential that outlives the page."""
    response = client.post(
        "/api/v1/auth/login/",
        {"email": owner.email, "password": PASSWORD},
        format="json",
    )
    assert "refresh" not in response.data

    cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["path"] == settings.REFRESH_COOKIE_PATH
    assert cookie["samesite"] == settings.REFRESH_COOKIE_SAMESITE


def test_the_refresh_cookie_alone_mints_a_new_access_token(
    client: APIClient, owner: User
) -> None:
    """This is what lets the access token live only in memory and survive a reload."""
    client.post(
        "/api/v1/auth/login/",
        {"email": owner.email, "password": PASSWORD},
        format="json",
    )
    refreshed = client.post("/api/v1/auth/refresh/")
    assert refreshed.status_code == 200
    assert refreshed.data["access"]
    assert refreshed.data["user"]["email"] == owner.email


def test_signing_out_clears_the_refresh_cookie(client: APIClient, owner: User) -> None:
    client.post(
        "/api/v1/auth/login/",
        {"email": owner.email, "password": PASSWORD},
        format="json",
    )
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.post("/api/v1/auth/refresh/").status_code == 400


def test_a_wrong_password_and_an_unknown_address_are_the_same_refusal(
    client: APIClient, owner: User
) -> None:
    """Distinguishing them turns the login form into an account-enumeration oracle."""
    wrong = client.post(
        "/api/v1/auth/login/",
        {"email": owner.email, "password": "not-the-password"},
        format="json",
    )
    unknown = client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@example.test", "password": PASSWORD},
        format="json",
    )
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_a_weak_password_is_refused_with_the_reasons(client: APIClient, db: Any) -> None:
    response = client.post(
        "/api/v1/auth/register/",
        {"email": "new@example.test", "password": "short"},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["errors"]["password"]
