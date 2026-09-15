"""Lazy PaddleOCR GPU adapter used by the regulation transcription stage.

Paddle is intentionally imported only when an OCR page is encountered.  This keeps
native-text-only operations usable on machines that do not have the optional GPU
runtime installed, while one worker instance keeps the detector/recognizer loaded
for the complete run.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.jsonio import JsonObject


@dataclass(frozen=True)
class PaddleOutput:
    """Ordered OCR records derived from one Paddle result."""

    tokens: list[JsonObject]
    lines: list[JsonObject]
    raw_text: str
    raw_result: JsonObject


def paddle_runtime(*, device: str = "gpu:0", require_gpu: bool = False) -> JsonObject:
    """Return an attested Paddle runtime identity without loading OCR models."""
    paddleocr_version = _package_version("paddleocr")
    paddle_version = _package_version("paddlepaddle-gpu") or _package_version(
        "paddlepaddle"
    )
    cuda_available = False
    if paddle_version is not None:
        try:
            import paddle  # type: ignore[import-not-found]

            cuda_available = bool(paddle.is_compiled_with_cuda())
        except (AttributeError, ImportError, RuntimeError, ValueError):
            cuda_available = False
    if require_gpu and (paddleocr_version is None or paddle_version is None):
        raise TranscriptionError(
            "PaddleOCR GPU requires installed paddleocr and paddlepaddle packages"
        )
    if require_gpu and not cuda_available:
        raise TranscriptionError("PaddlePaddle is not compiled with CUDA support")
    return {
        "paddleocr": paddleocr_version or "unavailable",
        "paddlepaddle": paddle_version or "unavailable",
        "paddle_cuda": cuda_available,
        "paddle_device": device,
        "paddle_det_model": "PP-OCRv5_mobile_det",
        "paddle_rec_model": "arabic_PP-OCRv5_mobile_rec",
    }


class PaddleGpuWorker:
    """One long-lived PP-OCRv5 worker.

    Paddle's Python objects are not promised to be thread-safe, so calls are made
    by the transcription coordinator in document/page order.  Loading is lazy so
    native-only documents never initialize CUDA or download model files.
    """

    def __init__(
        self,
        *,
        device: str = "gpu:0",
        detection_limit_side_len: int = 1536,
        recognition_batch_size: int = 8,
    ) -> None:
        self.device = device
        self.detection_limit_side_len = detection_limit_side_len
        self.recognition_batch_size = recognition_batch_size
        self._ocr: Any | None = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        # These settings prevent a single page from fanning out a second CPU pool.
        threads = str(min(4, os.cpu_count() or 1))
        for key in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "PADDLE_NUM_THREADS",
        ):
            os.environ.setdefault(key, threads)
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            import paddle
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except (ImportError, PackageNotFoundError) as exc:
            raise TranscriptionError(
                "PaddleOCR is not installed; install tools/paddleocr/requirements.txt "
                "with a CUDA-enabled PaddlePaddle wheel"
            ) from exc
        if self.device.startswith("gpu"):
            if not paddle.is_compiled_with_cuda():
                raise TranscriptionError("PaddlePaddle is not compiled with CUDA support")
            paddle.set_device(self.device)
        try:
            self._ocr = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="arabic_PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_recognition_batch_size=self.recognition_batch_size,
                text_det_limit_side_len=self.detection_limit_side_len,
                device=self.device,
                enable_mkldnn=False,
            )
        except Exception as exc:
            raise TranscriptionError(
                "PaddleOCR model initialization failed: "
                f"{type(exc).__name__}"
            ) from exc
        return self._ocr

    def run(
        self, image: Path, *, page_id: str, timeout_seconds: int | None = None
    ) -> PaddleOutput:
        if not image.is_file() or image.is_symlink():
            raise TranscriptionError(f"Paddle input is not a regular file: {image}")
        started = time.monotonic()
        try:
            with self._lock:
                result = next(iter(self._load().predict(str(image))))
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(
                f"PaddleOCR inference failed: {type(exc).__name__}"
            ) from exc
        if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
            raise TranscriptionError(
                f"PaddleOCR exceeded the {timeout_seconds}-second page timeout"
            )
        fields = {
            key: _json_value(result[key])
            for key in ("rec_texts", "rec_scores", "rec_boxes", "dt_polys", "rec_polys")
            if key in result
        }
        return _parse_result(fields, page_id=page_id)


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _json_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def _parse_result(result: JsonObject, *, page_id: str) -> PaddleOutput:
    texts = [str(value) for value in cast(list[Any], result.get("rec_texts", []))]
    scores = cast(list[Any], result.get("rec_scores", []))
    boxes = cast(list[Any], result.get("rec_boxes", result.get("rec_polys", [])))
    raw_tokens: list[tuple[str, list[int], int]] = []
    for index, text in enumerate(texts):
        value = text.strip()
        if not value:
            continue
        bbox = _bbox(boxes[index] if index < len(boxes) else [0, 0, 0, 0])
        score = float(scores[index]) if index < len(scores) else 0.0
        confidence = max(0, min(10000, round(score * 10000)))
        raw_tokens.append((value, bbox, confidence))

    # Paddle detections are not guaranteed to be RTL ordered.  Group by vertical
    # proximity, then read Persian lines from right to left within each row.
    raw_tokens.sort(key=lambda item: (item[1][1], item[1][0]))
    grouped: list[list[tuple[str, list[int], int]]] = []
    for token in raw_tokens:
        center = (token[1][1] + token[1][3]) / 2
        height = max(1, token[1][3] - token[1][1])
        selected: list[tuple[str, list[int], int]] | None = None
        for candidate in reversed(grouped[-3:]):
            candidate_center = (
                sum((item[1][1] + item[1][3]) / 2 for item in candidate)
                / len(candidate)
            )
            candidate_height = max(
                1,
                max(item[1][3] for item in candidate)
                - min(item[1][1] for item in candidate),
            )
            if abs(center - candidate_center) <= max(height, candidate_height) * 0.6:
                selected = candidate
                break
        if selected is None:
            grouped.append([token])
        else:
            selected.append(token)
    grouped.sort(key=lambda group: min(item[1][1] for item in group))

    tokens: list[JsonObject] = []
    lines: list[JsonObject] = []
    for line_index, group in enumerate(grouped):
        group.sort(key=lambda item: item[1][0], reverse=True)
        line_ids: list[str] = []
        line_confidences: list[int] = []
        for text, bbox, confidence in group:
            token_index = len(tokens)
            span_id = f"{page_id}:ocr:word:{token_index:06d}"
            tokens.append(
                {
                    "span_id": span_id,
                    "raw_text": text,
                    "bbox": bbox,
                    "confidence_permyriad": confidence,
                    "block": 0,
                    "paragraph": 0,
                    "line": line_index,
                }
            )
            line_ids.append(span_id)
            line_confidences.append(confidence)
        left = min(item[1][0] for item in group)
        top = min(item[1][1] for item in group)
        right = max(item[1][2] for item in group)
        bottom = max(item[1][3] for item in group)
        lines.append(
            {
                "span_id": f"{page_id}:ocr:line:{line_index:06d}",
                "raw_text": " ".join(item[0] for item in group),
                "bbox": [left, top, right, bottom],
                "confidence_permyriad": (
                    sum(line_confidences) // len(line_confidences)
                    if line_confidences
                    else 0
                ),
                "token_span_ids": line_ids,
            }
        )
    return PaddleOutput(
        tokens=tokens,
        lines=lines,
        raw_text="\n".join(cast(str, line["raw_text"]) for line in lines),
        raw_result=result,
    )


def _bbox(value: Any) -> list[int]:
    values = _json_value(value)
    if isinstance(values, list) and len(values) == 4 and all(
        isinstance(item, (int, float)) for item in values
    ):
        return [max(0, round(float(item))) for item in values]
    points: list[tuple[float, float]] = []
    if isinstance(values, list):
        for point in values:
            if isinstance(point, list) and len(point) >= 2:
                try:
                    points.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError):
                    continue
    if not points:
        return [0, 0, 0, 0]
    return [
        max(0, round(min(point[0] for point in points))),
        max(0, round(min(point[1] for point in points))),
        max(0, round(max(point[0] for point in points))),
        max(0, round(max(point[1] for point in points))),
    ]
