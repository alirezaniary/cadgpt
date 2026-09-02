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

export interface EntityOutcome {
  global_id: string | null;
  ifc_class: string;
  status: Status;
  reason_code: string;
  reason_label: string | null;
  detail: string;
}

export interface RequirementOutcome {
  description: string;
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
}

export interface Review {
  uuid: string;
  name: string;
  model_file: Media;
  rule_set: RuleSet;
  latest_run: CheckRunSummary | null;
  created_at: string;
  updated_at: string;
}

/** A run that will never change again. Polling stops here. */
export function isTerminal(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed";
}
