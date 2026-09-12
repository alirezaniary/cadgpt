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

/** The changelist's container for reviews (T-0073) -- `ProjectSerializer`'s exact shape:
 * `uuid`, `name`, `review_count` (annotated on the list query, falling back to a live
 * count for an instance with no reviews yet), `created_at`. */
export interface Project {
  uuid: string;
  name: string;
  review_count: number;
  created_at: string;
}

/** A shipped pack from the catalogue (T-0030) -- belongs to no tenant, every tenant reads
 * the same rows. Selected at check-request time rather than at review creation; see
 * `RulePackSelectionEntry`. Deliberately has no `source_file` (T-0042): the server no
 * longer serialises it -- nothing here ever fetched a pack's IDS bytes, so the field was
 * a raw storage URL with no consumer, not a download route worth authenticating. */
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
  /** What this pack cites as its authority (`RulePack.source_citation`), captured here at
   * dispatch time for the same reason every other field on this entry is (T-0031's own
   * reproducibility guarantee) -- a live lookup against the catalogue's current row could
   * show wording this run never actually asserted under. Optional because a selection
   * entry recorded before T-0049 has no such key at all. This is what
   * `SpecificationOutcome.rule_pack` on a finding resolves to, by matching `uuid`. */
  source_citation?: string;
}

/** The minimal identity a finding needs to point back at the pack that produced it
 * (`SpecificationOutcome.rule_pack`, T-0049) -- uuid, name and version, enough to resolve
 * to the matching `RulePackSelectionEntry` above (by `uuid`) rather than duplicating its
 * `jurisdiction` / `region` / `source_citation` on every specification. */
export interface SpecificationRulePackRef {
  uuid: string;
  name: string;
  version: string;
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
  /** T-0039: the attribute or property *name* itself, restricted rather than stated
   * literally (`<xs:restriction>` under `<ids:name>`/`<ids:baseName>`) -- the sibling of
   * `comparisons` for the name rather than the value. Empty whenever `name` above is
   * populated: a facet's name is either stated literally or restricted, never both.
   * Optional because a report stored before `REPORT_SCHEMA_VERSION` 4 has no such key. */
  name_comparisons?: Comparison[];
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
  /** Why *this requirement* evaluated no entities -- `null` when it genuinely evaluated
   * entities (`passed`/`failed`/`indeterminate` are not all zero), reusing the same
   * specification-level reason `judge()` decided one level up (`reason_code` on
   * `SpecificationOutcome`, T-0037). Optional because a report stored before
   * `REPORT_SCHEMA_VERSION` 3 has no `reason_code` key on a requirement at all. */
  reason_code?: string | null;
  /** `reason_code` rendered into the reader's language by the service, the same way
   * `SpecificationOutcome.reason_label` and `EntityOutcome.reason_label` already are.
   * `null` for both "no reason" and "report predates this field" -- see `reason_code`. */
  reason_label?: string | null;
  /** T-0037 review round 2 (F1): why the *specification this requirement belongs to*
   * never established that it applies at all (today, only a schema mismatch), even
   * though this requirement genuinely evaluated real entities and reached a real
   * `status` on them. Distinct from `reason_code` on purpose -- reusing `reason_code`
   * here would claim this requirement evaluated nothing, which would be false: `passed`
   * / `failed` / `indeterminate` are real counts from a real evaluation. `null` when the
   * specification's own applicability was established, or when `reason_code` above is
   * already set (that case already explains the row; see the engine's own comment on
   * this field, `cadgpt_engine.report.RequirementOutcome.applicability_caveat`).
   * Optional because a report stored before this field existed has no key at all. */
  applicability_caveat?: string | null;
  /** `applicability_caveat` rendered into the reader's language, the same way
   * `reason_label` is for `reason_code`. */
  applicability_caveat_label?: string | null;
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
   * data") -- kept as the fallback `applicability_text` (below) renders from when it
   * cannot be built. Absent for a report stored before this field existed. */
  applicability_description?: string;
  /** `applicability_description`, localized server-side into the reader's language
   * (T-0039) -- the field to render. Always present: `presentation.localize_report`
   * computes it from `applicability_facets` when available, or from
   * `applicability_description` itself otherwise, the same fallback shape
   * `requirement_text` already has beside `description`. */
  applicability_text: string;
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
  /** T-0049: which pack asserted this specification -- absent for a run against an
   * uploaded `RuleSet` (never combined from several packs to begin with, so there is
   * nothing to attribute) and for a document stored before this field existed alike.
   * Present for every specification a catalogue run's `_attribute_specifications`
   * (the service, not the engine -- it must not learn what a `RulePack` is) actually
   * attributed. Resolve `uuid` against the run's own `rule_pack_selection` for this
   * pack's `jurisdiction`, `region` and `source_citation`. */
  rule_pack?: SpecificationRulePackRef;
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
  /** The generated Markdown report's download route (T-0032), `null` until generation
   * completes -- an authenticated path, never a bare storage URL (`docs/tasks/
   * T-0042-the-catalogue-hands-out-a-storage-url.md` is exactly the mistake this avoids).
   * Fetch it with the same authenticated client as everything else here, not a plain
   * `<a href>`: the API takes a bearer token, not a cookie. */
  report_file_url: string | null;
  /** Blank until generation is attempted and fails for a reason a retry will not change
   * (T-0051) -- today, only the rendered report exceeding what the server can store. A
   * succeeded run with this blank *and* `report_file_url` null has simply not been
   * generated yet; `useGenerateReportFile` asks again. Distinguishes "not generated yet"
   * from "cannot be generated", which `report_file_url` alone cannot: both are null for
   * it. */
  report_generation_error: string;
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
