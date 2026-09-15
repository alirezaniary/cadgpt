-- Rebuildable PostgreSQL projection for the page-first INBR transcript workflow.
--
-- Immutable PDFs, native/Paddle extraction payloads, complete Luna responses,
-- extraction responses, and compiled release files remain in content-addressed
-- storage. This projection keeps only queryable document/page/rule records.
-- There are deliberately no run, source-span, legal-assertion, evidence, or
-- release-membership tables. Raw and previous pipeline runs are file history.

CREATE TABLE IF NOT EXISTS pdf_document (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_key TEXT NOT NULL UNIQUE,
    pdf_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    storage_uri TEXT,
    volume_number INTEGER,
    edition_year INTEGER,
    edition_code TEXT NOT NULL,
    title_fa TEXT,
    source_sha256 CHAR(64) NOT NULL UNIQUE
        CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    file_size_bytes BIGINT CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0),
    page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (volume_number IS NULL OR volume_number > 0),
    CHECK (edition_year IS NULL OR edition_year > 0),
    CHECK (document_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'),
    CHECK (edition_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$')
);

CREATE TABLE IF NOT EXISTS pdf_page (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_key TEXT NOT NULL REFERENCES pdf_document(document_key) ON DELETE CASCADE,
    page_key TEXT NOT NULL UNIQUE,
    pdf_page_number INTEGER NOT NULL CHECK (pdf_page_number > 0),
    printed_page_label TEXT,

    -- The route describes which extraction is the current usable text source.
    extraction_route TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_route IN (
            'pending', 'native', 'paddle', 'native_plus_paddle', 'blank'
        )),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'extracted', 'transcribed', 'failed')),

    native_text TEXT,
    native_layout_json JSONB,
    native_text_sha256 CHAR(64)
        CHECK (native_text_sha256 IS NULL OR native_text_sha256 ~ '^[0-9a-f]{64}$'),

    paddle_text TEXT,
    paddle_result_json JSONB,
    paddle_text_sha256 CHAR(64)
        CHECK (paddle_text_sha256 IS NULL OR paddle_text_sha256 ~ '^[0-9a-f]{64}$'),

    -- This is the page-specific object selected from Luna's complete response.
    luna_transcript_json JSONB,
    luna_transcript_text TEXT,
    luna_transcript_sha256 CHAR(64)
        CHECK (
            luna_transcript_sha256 IS NULL
            OR luna_transcript_sha256 ~ '^[0-9a-f]{64}$'
        ),
    -- The complete ten-page response is retained once in file/object storage.
    luna_response_uri TEXT,
    luna_response_sha256 CHAR(64)
        CHECK (
            luna_response_sha256 IS NULL
            OR luna_response_sha256 ~ '^[0-9a-f]{64}$'
        ),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_key, page_key),
    UNIQUE (document_key, pdf_page_number)
);

CREATE INDEX IF NOT EXISTS pdf_page_document_page_idx
    ON pdf_page (document_key, pdf_page_number);
CREATE INDEX IF NOT EXISTS pdf_page_luna_hash_idx
    ON pdf_page (luna_transcript_sha256);

CREATE TABLE IF NOT EXISTS rule_candidate (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_key TEXT NOT NULL UNIQUE,
    document_key TEXT NOT NULL REFERENCES pdf_document(document_key),
    primary_page_key TEXT NOT NULL,

    -- The record key points into the page's Luna transcript JSON. A rule can
    -- cite more than one page when a sentence crosses a page boundary.
    source_record_key TEXT NOT NULL,
    source_record_type TEXT,
    source_page_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(source_page_ids) = 'array'),
    source_text_fa TEXT,
    source_text_sha256 CHAR(64)
        CHECK (source_text_sha256 IS NULL OR source_text_sha256 ~ '^[0-9a-f]{64}$'),
    transcript_sha256 CHAR(64)
        CHECK (transcript_sha256 IS NULL OR transcript_sha256 ~ '^[0-9a-f]{64}$'),

    -- The complete extraction response is a file; this row stores its identity.
    extraction_file_uri TEXT,
    extraction_file_sha256 CHAR(64)
        CHECK (
            extraction_file_sha256 IS NULL
            OR extraction_file_sha256 ~ '^[0-9a-f]{64}$'
        ),
    extraction_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- IDS-shaped candidate payload. It is validated against the IDS facet model
    -- (entity, partOf, classification, attribute, property, material) before
    -- compilation; the JSON remains flexible for derived/unsupported rules.
    rule_key TEXT,
    implementation_type TEXT
        CHECK (implementation_type IS NULL OR implementation_type IN (
            'native_ids', 'derived_ids', 'decision_table',
            'formula_evaluator', 'unsupported'
        )),
    semantic_fingerprint CHAR(64)
        CHECK (
            semantic_fingerprint IS NULL
            OR semantic_fingerprint ~ '^[0-9a-f]{64}$'
        ),
    ids_specification JSONB,

    -- Compiled artifacts are immutable files; hashes make the projection auditable.
    ids_xml_uri TEXT,
    ids_xml_sha256 CHAR(64)
        CHECK (ids_xml_sha256 IS NULL OR ids_xml_sha256 ~ '^[0-9a-f]{64}$'),
    sidecar_uri TEXT,
    sidecar_sha256 CHAR(64)
        CHECK (sidecar_sha256 IS NULL OR sidecar_sha256 ~ '^[0-9a-f]{64}$'),
    compiler_version TEXT,

    status TEXT NOT NULL DEFAULT 'extracted'
        CHECK (status IN (
            'extracted', 'validated', 'compiled', 'deferred', 'rejected'
        )),
    reason_code TEXT,
    validation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (candidate_key ~ '^[A-Za-z0-9][A-Za-z0-9._-]*$'),
    FOREIGN KEY (document_key, primary_page_key)
        REFERENCES pdf_page (document_key, page_key)
);

CREATE INDEX IF NOT EXISTS rule_candidate_document_idx
    ON rule_candidate (document_key, primary_page_key);
CREATE INDEX IF NOT EXISTS rule_candidate_status_idx
    ON rule_candidate (status, implementation_type);
CREATE INDEX IF NOT EXISTS rule_candidate_fingerprint_idx
    ON rule_candidate (semantic_fingerprint);
