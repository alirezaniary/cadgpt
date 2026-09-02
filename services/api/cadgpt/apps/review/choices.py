from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class CheckRunStatus(models.TextChoices):
    """Where one evaluation is in its life.

    Stored as readable words rather than abbreviations. The value appears in the HTTP API,
    in logs and in a database a person debugs at three in the morning; the bytes saved by
    a three-letter code are not worth what they cost to read.
    """

    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    SUCCEEDED = "succeeded", _("Succeeded")
    FAILED = "failed", _("Failed")


#: A run in one of these will never change again. The task returns early when it sees one,
#: which is what makes the task safe to deliver twice.
TERMINAL_STATUSES = frozenset({CheckRunStatus.SUCCEEDED, CheckRunStatus.FAILED})


class CheckRunFailure(models.TextChoices):
    """Why a run did not produce a report. Distinct from any finding about the model.

    A rejected input and a crashed worker are different events with different remedies,
    and collapsing them into one 'failed' would leave the user with nothing to act on.
    """

    INVALID_MODEL = "invalid_model", _("The model file could not be read")
    INVALID_RULE_SET = "invalid_rule_set", _("The rule set could not be read")
    STALLED = "stalled", _("The check stopped responding and was ended")
    INTERNAL_ERROR = "internal_error", _("The check failed unexpectedly")


class OutcomeStatus(models.TextChoices):
    """The three-valued result, mirrored from the engine for filtering and for the schema.

    INDETERMINATE is never mapped to PASS -- not in a count, a summary, a filter or an API
    response. It is the product's whole value over the raw checker.
    """

    PASS = "PASS", _("Pass")
    FAIL = "FAIL", _("Fail")
    INDETERMINATE = "INDETERMINATE", _("Indeterminate")


OUTCOME_STATUS_CHOICES = OutcomeStatus.choices
