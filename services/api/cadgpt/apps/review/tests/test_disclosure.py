"""disclosure_title / disclosure_text: the I7 disclosure sentence, server-rendered.

Translated wording is proven against the real running API in two languages
(`docs/tasks/T-0029-say-what-was-checked.md`'s evidence), the same way
`test_requirements.py` defers `requirement_text`'s bilingual proof -- this process's `.po`
catalogue is not compiled to `.mo` outside the container build
(`deploy/docker/api.Dockerfile`), so `gettext` here returns the English source string
verbatim. What this file proves is the interpolation and the wording contract: the
filename is taken from the argument, never hardcoded, and the text never uses the word
"clean" to describe a result that could be FAIL or INDETERMINATE.
"""

from __future__ import annotations

from cadgpt.apps.review.disclosure import disclosure_text, disclosure_title


def test_the_title_is_nonempty() -> None:
    assert disclosure_title().strip()


def test_the_text_names_the_given_filename_not_a_hardcoded_one() -> None:
    text = disclosure_text("three_doors.ifc")
    assert "three_doors.ifc" in text

    other = disclosure_text("Block A - level 00.ifc")
    assert "Block A - level 00.ifc" in other
    assert "three_doors.ifc" not in other


def test_the_text_states_the_model_was_checked_not_the_drawing_set() -> None:
    text = disclosure_text("three_doors.ifc")
    assert "drawing set" in text


def test_the_text_names_a_concrete_divergence_not_an_abstract_disclaimer() -> None:
    # An abstract disclaimer reads as boilerplate; a concrete one reads as information
    # (task requirement). At least one of the named examples must be present.
    text = disclosure_text("three_doors.ifc")
    assert any(example in text for example in ("schedule", "titleblock", "view"))


def test_the_text_never_calls_the_result_clean() -> None:
    # A FAIL or all-INDETERMINATE report is a live counterexample to "a clean result" --
    # the word must not appear, in either direction of the I7 misreading it would invite.
    text = disclosure_text("three_doors.ifc")
    assert "clean" not in text.lower()
