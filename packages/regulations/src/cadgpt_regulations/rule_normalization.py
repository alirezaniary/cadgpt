"""Lossless Persian token normalization for rule compilation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from cadgpt_regulations.transcription import ascii_digit_view, normalize_search_text


class RuleNormalizationError(ValueError):
    """Raised when a Persian token cannot be normalized without guessing."""


_UNIT_MAP = {
    "mm": "mm",
    "میلی متر": "mm",
    "میلی‌متر": "mm",
    "میلیمتر": "mm",
    "cm": "cm",
    "سانتی متر": "cm",
    "سانتی‌متر": "cm",
    "سانتیمتر": "cm",
    "m": "m",
    "متر": "m",
    "m2": "m2",
    "m²": "m2",
    "متر مربع": "m2",
    "مترمربع": "m2",
    "m3": "m3",
    "m³": "m3",
    "متر مکعب": "m3",
    "مترمکعب": "m3",
    "kpa": "kPa",
    "کیلوپاسکال": "kPa",
    "کیلو پاسکال": "kPa",
    "mpa": "MPa",
    "مگاپاسکال": "MPa",
    "°c": "Cel",
    "درجه سلسیوس": "Cel",
}
_NUMBER = re.compile(r"^[+-]?[0-9]+(?:[.,\u066b][0-9]+)?$")


@dataclass(frozen=True, slots=True)
class NormalizedRuleToken:
    original_fa: str
    normalized_fa: str
    ascii_view: str
    numeric_value: Decimal | None
    unit_ucum: str | None


def normalize_rule_token(
    value_fa: str, *, unit_fa: str | None = None
) -> NormalizedRuleToken:
    """Return deterministic views while retaining the exact Persian input."""
    if not isinstance(value_fa, str) or not value_fa.strip():
        raise RuleNormalizationError("value_fa must be a non-empty string")
    normalized, _ = normalize_search_text(unicodedata.normalize("NFKC", value_fa))
    ascii_view = ascii_digit_view(normalized)
    numeric = None
    if _NUMBER.fullmatch(ascii_view):
        try:
            numeric = Decimal(ascii_view.replace(",", ".").replace("\u066b", "."))
        except InvalidOperation as exc:
            raise RuleNormalizationError("numeric token is invalid") from exc
    unit = None
    if unit_fa is not None:
        if not isinstance(unit_fa, str) or not unit_fa.strip():
            raise RuleNormalizationError("unit_fa must be null or a non-empty string")
        unit_key, _ = normalize_search_text(unicodedata.normalize("NFKC", unit_fa))
        unit_key = " ".join(ascii_digit_view(unit_key).split()).casefold()
        unit = _UNIT_MAP.get(unit_key)
        if unit is None:
            raise RuleNormalizationError(f"ambiguous or unsupported unit: {unit_fa}")
    return NormalizedRuleToken(
        original_fa=value_fa,
        normalized_fa=normalized,
        ascii_view=ascii_view,
        numeric_value=numeric,
        unit_ucum=unit,
    )
