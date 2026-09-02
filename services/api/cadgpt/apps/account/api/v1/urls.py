from __future__ import annotations

from django.urls import path

from cadgpt.apps.account.api.v1.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
)

app_name = "account-v1"

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/password/", ChangePasswordView.as_view(), name="change-password"),
    path("me/", MeView.as_view(), name="me"),
]
