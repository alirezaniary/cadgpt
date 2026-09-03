FROM ubuntu@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG DEBIAN_FRONTEND=noninteractive
ARG TESSDATA_COMMIT=e12c65a915945e4c28e237a9b52bc4a8f39a0cec

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        python3.12 \
        python3-pip \
        python3.12-venv \
        tesseract-ocr=5.3.4-1build5 \
    && rm -rf /var/lib/apt/lists/* \
    && python3.12 -m pip install --break-system-packages --no-cache-dir uv==0.8.14

RUN mkdir --parents /opt/tessdata-best \
    && curl --fail --location --retry 3 \
        --output /opt/tessdata-best/fas.traineddata \
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/${TESSDATA_COMMIT}/fas.traineddata" \
    && curl --fail --location --retry 3 \
        --output /opt/tessdata-best/eng.traineddata \
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/${TESSDATA_COMMIT}/eng.traineddata" \
    && curl --fail --location --retry 3 \
        --output /opt/tessdata-best/osd.traineddata \
        "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/${TESSDATA_COMMIT}/osd.traineddata" \
    && printf '%s  %s\n' \
        99e420969b5ddd2cb135b416316a7ed417c59c4faf9e0d28941348f6448114df \
        /opt/tessdata-best/fas.traineddata \
        8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba \
        /opt/tessdata-best/eng.traineddata \
        9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff \
        /opt/tessdata-best/osd.traineddata \
        | sha256sum --check --strict

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services/api/pyproject.toml ./services/api/pyproject.toml
RUN uv sync --frozen --package cadgpt-regulations --no-dev --no-editable

RUN useradd --create-home --uid 10001 regulations \
    && chown --recursive regulations:regulations /app

ENV PATH=/app/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV TESSDATA_PREFIX=/opt/tessdata-best
USER regulations

ENTRYPOINT ["cadgpt-regulations"]
