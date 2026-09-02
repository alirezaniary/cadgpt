"""Authentication and the authenticated user's own record.

Login, refresh and logout are separate views rather than a viewset: they are not CRUD over
a resource, and pretending they are produces routes nobody can read.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal, cast

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from cadgpt.apps.account.api.v1.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ValidationError


def _access_lifetime() -> timedelta:
    return cast(timedelta, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])


def _refresh_lifetime() -> timedelta:
    return cast(timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])


def _token_response(user: User, *, status_code: int = status.HTTP_200_OK) -> Response:
    refresh = RefreshToken.for_user(user)
    access_seconds = int(_access_lifetime().total_seconds())
    body = TokenPairSerializer(
        {
            "access": str(refresh.access_token),
            "expires_in": access_seconds,
            "user": user,
        }
    ).data
    response = Response(body, status=status_code)
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(_refresh_lifetime().total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=cast(
            "Literal['Lax', 'Strict', 'None'] | None", settings.REFRESH_COOKIE_SAMESITE
        ),
        path=settings.REFRESH_COOKIE_PATH,
    )
    return response


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "auth"
    serializer_class = RegisterSerializer

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "auth"
    serializer_class = LoginSerializer

    @extend_schema(request=LoginSerializer, responses={200: TokenPairSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active:
            # One message for a wrong password and an unknown address alike: the
            # difference between them is an account-enumeration oracle.
            raise ValidationError(_("The email address or password is not correct."))
        return _token_response(user)


class RefreshView(APIView):
    """Exchange the refresh cookie for a new access token, rotating the refresh token."""

    permission_classes = (AllowAny,)
    throttle_scope = "auth"

    @extend_schema(request=None, responses={200: TokenPairSerializer})
    def post(self, request: Request) -> Response:
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            raise ValidationError(_("No session to refresh."))
        try:
            token = RefreshToken(cast(Any, raw))
            user_uuid = token["sub"]
        except (TokenError, KeyError) as exc:
            raise ValidationError(_("The session has expired. Sign in again.")) from exc

        user = User.objects.filter(uuid=user_uuid, is_active=True).first()
        if user is None:
            raise ValidationError(_("The session has expired. Sign in again."))
        return _token_response(user)


class LogoutView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:  # noqa: ARG002
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH
        )
        return response


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: UserSerializer})
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(cast("User", request.user)).data)

    @extend_schema(request=UserUpdateSerializer, responses={200: UserSerializer})
    def patch(self, request: Request) -> Response:
        user = cast("User", request.user)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_scope = "auth"

    @extend_schema(request=ChangePasswordSerializer, responses={200: None})
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(cast("User", request.user), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
