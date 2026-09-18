"""Run one bounded PP-OCRv5 page on the configured CUDA device."""

from __future__ import annotations

import argparse
import json
import os
import resource
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any


def _limit_process() -> None:
    # Keep an experiment from exhausting the desktop while loading Paddle models.
    # A dense page can legitimately need more than 55 CPU-seconds on this laptop.
    # The shell wrapper still imposes a wall-clock timeout and low scheduler priority.
    cpu_limit = 720
    with suppress(OSError, ValueError):
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 5))


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.image.is_file() or args.image.is_symlink():
        raise SystemExit(f"input is not a regular file: {args.image}")

    # Limit host-side thread fan-out while Paddle uses the GPU.
    thread_count = str(min(4, os.cpu_count() or 1))
    os.environ.setdefault("OMP_NUM_THREADS", thread_count)
    os.environ.setdefault("MKL_NUM_THREADS", thread_count)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", thread_count)
    os.environ.setdefault("NUMEXPR_NUM_THREADS", thread_count)
    os.environ.setdefault("PADDLE_NUM_THREADS", thread_count)
    os.environ.setdefault("FLAGS_use_onednn", "0")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    _limit_process()

    import paddle
    from paddleocr import PaddleOCR

    if not paddle.is_compiled_with_cuda():
        raise SystemExit("GPU PaddlePaddle build is not available")
    device = os.environ.get("PADDLE_DEVICE", "gpu:0")
    paddle.set_device(device)
    with suppress(AttributeError, RuntimeError, ValueError):
        paddle.set_flags({"FLAGS_use_onednn": False, "FLAGS_use_mkldnn": False})

    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="arabic_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_recognition_batch_size=int(
            os.environ.get("PADDLE_TEXT_REC_BATCH_SIZE", "4")
        ),
        text_det_limit_side_len=int(
            os.environ.get("PADDLE_TEXT_DET_LIMIT_SIDE_LEN", "960")
        ),
        device=device,
        enable_mkldnn=False,
    )
    result = next(iter(ocr.predict(str(args.image))))
    result_fields = {
        key: result[key]
        for key in ("rec_texts", "rec_scores", "rec_boxes", "dt_polys", "rec_polys")
        if key in result
    }
    payload = {
        "engine": {
            "name": "paddleocr",
            "version": "3.7.0",
            "ocr_version": "PP-OCRv5",
            "device": device,
        },
        "image": str(args.image),
        "result": _json_value(result_fields),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=args.output.parent, delete=False
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
