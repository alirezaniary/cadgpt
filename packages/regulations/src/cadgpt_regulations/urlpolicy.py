"""Exact-origin URL validation and transport-equivalent URL comparison."""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

from cadgpt_regulations.errors import CatalogError

_PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
OFFICIAL_INBR_ORIGINS = frozenset(
    {
        "https://inbr.ir",
        "https://inbr.s3.ir-thr-at1.arvanstorage.ir",
    }
)


def canonical_origin(url: str) -> str:
    """Return a strict origin, rejecting URL features that weaken origin checks."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise CatalogError(f"unsupported URL scheme for acquisition: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise CatalogError(f"acquisition URL cannot contain user information: {url}")
    if parsed.fragment:
        raise CatalogError(f"acquisition URL cannot contain a fragment: {url}")
    if parsed.hostname is None:
        raise CatalogError(f"acquisition URL has no host: {url}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CatalogError(f"acquisition URL has an invalid port: {url}") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    authority = host if port in {None, default_port} else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def validate_acquisition_url(url: str, allowed_origins: frozenset[str]) -> None:
    """Require an exact configured origin before any network request is made."""
    origin = canonical_origin(url)
    if origin not in allowed_origins:
        raise CatalogError(f"acquisition URL origin is not approved: {origin}")


def validate_official_origins(allowed_origins: frozenset[str]) -> None:
    """Prevent a caller-supplied catalog from expanding the network trust boundary."""
    if not allowed_origins or not allowed_origins <= OFFICIAL_INBR_ORIGINS:
        raise CatalogError(
            "acquisition origins must be configured official HTTPS INBR origins"
        )


def normalize_transport_url(url: str) -> str:
    """Normalize Unicode and percent-escape case without decoding reserved separators."""
    parsed = urlsplit(url)
    host = parsed.hostname.lower() if parsed.hostname is not None else ""
    raw_userinfo, separator, _ = parsed.netloc.rpartition("@")
    userinfo = f"{raw_userinfo}@" if separator else ""
    try:
        port = parsed.port
    except ValueError:
        netloc = parsed.netloc
    else:
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        authority = host if port in {None, default_port} else f"{host}:{port}"
        netloc = f"{userinfo}{authority}"
    path = quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="%:@!$&'()*+,;=/?-._~")
    fragment = quote(parsed.fragment, safe="%:@!$&'()*+,;=/?-._~")
    path = _PERCENT_ESCAPE.sub(lambda match: match.group(0).upper(), path)
    query = _PERCENT_ESCAPE.sub(lambda match: match.group(0).upper(), query)
    fragment = _PERCENT_ESCAPE.sub(lambda match: match.group(0).upper(), fragment)
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, fragment))
