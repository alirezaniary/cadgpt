"""Review business logic, split by lifecycle stage.

`review` creates the work and asks for it to be done. `execution` does it, and is the only
module a Celery worker enters. `presentation` renders a stored report for a reader.
`report_generation` renders that same report to the Markdown file that leaves the building
(T-0032), dispatched from `execution` the moment a run succeeds.
"""

from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.review.services.presentation import localize_report
from cadgpt.apps.review.services.report_generation import ReportGenerationService
from cadgpt.apps.review.services.review import ReviewService

__all__ = [
    "CheckRunExecutor",
    "ReportGenerationService",
    "ReviewService",
    "localize_report",
]
