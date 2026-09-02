/**
 * The wire shapes, mirroring the server's serializers.
 *
 * `pnpm run generate:api` regenerates `schema.d.ts` from the OpenAPI document the server
 * publishes, and these aliases are what the app imports. Hand-written types would drift
 * from the API the moment someone renamed a field on the server and nothing would fail.
 */

export type Status = "PASS" | "FAIL" | "INDETERMINATE";
export type Applicability = "APPLIES" | "DOES_NOT_APPLY" | "UNDETERMINED_APPLICABILITY";
export type RunStatus = "pending" | "running" | "succeeded" | "failed";

export interface Page<T> {
  count: number;
  page: number;
  pages: number;
  size: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface User {
  uuid: string;
  email: string;
  full_name: string;
  language: string;
  created_at: string;
}

export interface Tenant {
  uuid: string;
  name: string;
  slug: string;
  language: string;
  timezone: string;
  role: string | null;
  created_at: string;
}

export interface Media {
  uuid: string;
  kind: "ifc_model" | "ids_ruleset";
  original_name: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  created_at: string;
}

export interface RuleSet {
  uuid: string;
  name: string;
  description: string;
  title: string;
  author: string;
  version: string;
  specification_count: number;
  source_file: Media;
  created_at: string;
}

/** A shipped pack from the catalogue (T-0030) -- belongs to no tenant, every tenant reads
 * the same rows. Selected at check-request time rather than at review creation; see
 * `RulePackSelectionEntry`. */
export interface RulePack {
  uuid: string;
  name: string;
  description: string;
  jurisdiction: string;
  region: string;
  version: string;
  title: string;
  author: string;
  specification_count: number;
  source_citation: string;
  source_file: string;
  created_at: string;
}

/** One pack's citation as recorded on a `CheckRunDetail`, captured at dispatch time --
 * never re-derived from the live catalogue, so a later catalogue edit cannot redefine what
 * an already-dispatched run is understood to have checked (T-0031). */
export interface RulePackSelectionEntry {
  uuid: string;
  name: string;
  jurisdiction: string;
  region: string;
  version: string;
  specification_count: number;
  checksum_sha256: string;
}

export interface EntityOutcome {
  global_id: string | null;
  ifc_class: string;
  status: Status;
  reason_code: string;
  reason_label: string | null;
  detail: string;
}

export interface Comparison {
  operator: string;
  value: string;
}

/**
 * The requirement's own facet, as data rather than English -- `description`'s structured
 * counterpart. Optional because a report stored before `REPORT_SCHEMA_VERSION` 2 has no
 * `basis` key at all: `description` is the fallback for exactly that case.
 */
export interface RequirementBasis {
  facet_type: string;
  name: string | null;
  cardinality: string;
  comparisons: Comparison[];
}

export interface RequirementOutcome {
  /** ifctester's own English sentence. Kept as the fallback when `requirement_text` cannot
   * be built from `basis` -- an old document, or a facet type the service does not render. */
  description: string;
  /** The same fact as `description`, structured -- absent for a report stored before this
   * field existed. */
  basis?: RequirementBasis;
  /** `basis` rendered into the reader's language by the service, or `description` when it
   * could not be. Always present: this is the primary line to render, the way
   * `reason_label` is for a finding's cause. */
  requirement_text: string;
  status: Status;
  passed: number;
  failed: number;
  indeterminate: number;
  entities: EntityOutcome[];
  entities_omitted: number;
}

export interface SpecificationOutcome {
  name: string;
  description: string;
  /** ifctester's own rendering of what the applicability facets select (e.g. "All IFCDOOR
   * data") -- the report's subject line. Absent for a report stored before this field
   * existed. */
  applicability_description?: string;
  instructions: string;
  applicability: Applicability;
  status: Status;
  cardinality: string;
  matched: number;
  reason_code: string | null;
  reason_label: string | null;
  passed: number;
  failed: number;
  indeterminate: number;
  requirements: RequirementOutcome[];
}

export interface Report {
  schema_version: number;
  engine_version: string;
  ifc_filename: string;
  ifc_schema: string;
  ids_title: string;
  /** The I7 disclosure heading, server-rendered in the reader's language
   * (`cadgpt.apps.review.disclosure.disclosure_title`) -- prose, like `reason_label`,
   * never composed in the frontend. */
  disclosure_title: string;
  /** The I7 disclosure paragraph: what was checked (this model, by filename) and what
   * was not (the submitted drawing set). Server-rendered
   * (`cadgpt.apps.review.disclosure.disclosure_text`), `prd.md` 5.7. */
  disclosure_text: string;
  status: Status;
  specifications_passed: number;
  specifications_failed: number;
  specifications_indeterminate: number;
  passed: number;
  failed: number;
  indeterminate: number;
  specifications: SpecificationOutcome[];
}

export interface CheckRunSummary {
  uuid: string;
  status: RunStatus;
  outcome: Status | "";
  engine_version: string;
  specifications_passed: number;
  specifications_failed: number;
  specifications_indeterminate: number;
  passed: number;
  failed: number;
  indeterminate: number;
  failure_reason: string;
  failure_detail: string;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface CheckRunDetail extends CheckRunSummary {
  report: Report | null;
  model_checksum: string;
  rule_set_checksum: string;
  /** Empty for a run against `review.rule_set`; one entry per selected catalogue pack
   * otherwise (T-0031). */
  rule_pack_selection: RulePackSelectionEntry[];
}

export interface Review {
  uuid: string;
  name: string;
  model_file: Media;
  /** `null` for a review with no uploaded rule set of its own -- its checks are given a
   * catalogue selection per run instead (T-0031). */
  rule_set: RuleSet | null;
  latest_run: CheckRunSummary | null;
  created_at: string;
  updated_at: string;
}

/** A run that will never change again. Polling stops here. */
export function isTerminal(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed";
}
