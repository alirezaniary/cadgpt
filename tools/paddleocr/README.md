# Isolated PaddleOCR Lab

This directory contains the optional GPU OCR runtime used by the regulations package.
Native PDF text remains primary; Paddle is invoked only for pages classified as requiring OCR.

The wrapper is intentionally conservative for this laptop:

- PP-OCRv5 mobile detection and Persian/Arabic recognition;
- GPU execution on `gpu:0` with a small CPU thread pool;
- a 300-second hard timeout per page;
- one image per invocation, never a whole PDF or book;
- model files cached outside the repository by Paddle (normally under `~/.paddlex`).

Create the environment separately from the project workspace:

```sh
uv venv tools/paddleocr/.venv --python 3.12
uv pip install --python tools/paddleocr/.venv/bin/python \
  -r tools/paddleocr/requirements.txt
```

`paddlepaddle==3.3.1` must be the CUDA-enabled wheel for the host's CUDA version.
The wrapper and production worker fail closed when `paddle.is_compiled_with_cuda()` is false;
a CPU wheel is never silently used for OCR.

Run a bounded smoke test with one page image:

```sh
tools/paddleocr/run-safe.sh /path/to/page.png --output /tmp/paddle-result.json
```

The isolated wrapper is for smoke tests. Production transcription uses the long-lived
`PaddleGpuWorker`, records raw Paddle output and ordered RTL lines, and stores it in the
page evidence package.
