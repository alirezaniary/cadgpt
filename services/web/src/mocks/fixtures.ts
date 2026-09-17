/**
 * The data the preview workbench renders against.
 *
 * Every value here is typed as the wire shape the app actually consumes (`@/api/types`),
 * which is what stops these from drifting into a shape the server stopped returning: a
 * renamed or retyped field fails `pnpm typecheck` here exactly as it would in a component.
 *
 * Dates are fixed strings rather than `Date.now()` offsets, so two exports taken a week
 * apart differ only where the UI actually changed.
 *
 * The report's prose -- `disclosure_title`, `disclosure_text`, `reason_label`,
 * `requirement_text`, `applicability_text` -- is written in Persian on purpose. That
 * prose is composed by the server in the reader's language (`docs/decisions.md`, "Report
 * prose belongs to the server"), never by the frontend, so a fixture that carried English
 * there would be showing something the fa build can never receive. The workbench's
 * language toolbar switches the *interface* strings; this prose stays as the server would
 * have sent it. `applicability_description` -- the field it supersedes, kept only as the
 * fallback the server itself renders from -- stays in English here on purpose: it is
 * upstream's own unlocalized sentence, never what the UI shows.
 */

import type {
  CheckRunDetail,
  CheckRunSummary,
  Media,
  Page,
  Project,
  Report,
  Review,
  RulePack,
  RulePackSelectionEntry,
  RuleSet,
  Tenant,
  User,
} from "@/api/types";

export function page<T>(results: T[]): Page<T> {
  return {
    count: results.length,
    page: 1,
    pages: 1,
    size: 20,
    next: null,
    previous: null,
    results,
  };
}

export const user: User = {
  uuid: "6f1b7c62-2b8e-4f3a-9a1e-2c7d5e8f1a01",
  email: "s.hosseini@parsdesign.ir",
  full_name: "سارا حسینی",
  language: "fa",
  created_at: "2026-06-14T08:30:00Z",
};

export const tenant: Tenant = {
  uuid: "b2c3d4e5-1111-4a2b-8c3d-4e5f60718293",
  name: "دفتر معماری پارس",
  slug: "pars-design",
  language: "fa",
  timezone: "Asia/Tehran",
  role: "owner",
  created_at: "2026-06-14T08:31:00Z",
};

/** A second workspace, so the account menu's switcher has something to switch between --
 * it renders only when the tenant list has more than one row (`App.tsx`). */
export const secondTenant: Tenant = {
  uuid: "c3d4e5f6-2222-4b3c-9d4e-5f6071829304",
  name: "مهندسین مشاور آرمان",
  slug: "arman-consult",
  language: "fa",
  timezone: "Asia/Tehran",
  role: "member",
  created_at: "2026-07-02T11:05:00Z",
};

export const projects: Project[] = [
  {
    uuid: "11111111-1111-4111-8111-111111111111",
    name: "برج مسکونی نیاوران",
    review_count: 4,
    created_at: "2026-07-21T06:45:00Z",
  },
  {
    uuid: "22222222-2222-4222-8222-222222222222",
    name: "مجتمع اداری سعادت‌آباد",
    review_count: 1,
    created_at: "2026-08-03T13:20:00Z",
  },
  {
    uuid: "33333333-3333-4333-8333-333333333333",
    name: "بازسازی ساختمان کارگاهی",
    review_count: 0,
    created_at: "2026-08-29T09:10:00Z",
  },
];

/** `projects[0]`, but as a value the type checker knows is defined --
 * `noUncheckedIndexedAccess` makes every index access `T | undefined`. */
export const project: Project = {
  uuid: "11111111-1111-4111-8111-111111111111",
  name: "برج مسکونی نیاوران",
  review_count: 4,
  created_at: "2026-07-21T06:45:00Z",
};

export const emptyProject: Project = {
  uuid: "33333333-3333-4333-8333-333333333333",
  name: "بازسازی ساختمان کارگاهی",
  review_count: 0,
  created_at: "2026-08-29T09:10:00Z",
};

function model(name: string, bytes: number, uuid: string): Media {
  return {
    uuid,
    kind: "ifc_model",
    original_name: name,
    content_type: "application/x-step",
    size_bytes: bytes,
    checksum_sha256: "9f2c4a1b8e7d6c5b4a39281706f5e4d3c2b1a0998877665544332211000ffeedd",
    created_at: "2026-08-30T10:00:00Z",
  };
}

export const rulePacks: RulePack[] = [
  {
    uuid: "aaaa1111-0000-4000-8000-000000000001",
    name: "مقررات ملی ساختمان — مبحث چهارم",
    description: "الزامات عمومی ساختمان: ارتفاع، اشغال، دسترسی.",
    jurisdiction: "IR",
    region: "ملی",
    version: "1399",
    title: "National Building Regulations — Part 4",
    author: "وزارت راه و شهرسازی",
    specification_count: 18,
    source_citation: "مقررات ملی ساختمان ایران، مبحث چهارم، ویرایش ۱۳۹۹",
    created_at: "2026-05-02T07:00:00Z",
  },
  {
    uuid: "aaaa1111-0000-4000-8000-000000000002",
    name: "مقررات ملی ساختمان — مبحث سوم (حفاظت در برابر حریق)",
    description: "مسیرهای خروج، درهای مقاوم حریق، پلکان فرار.",
    jurisdiction: "IR",
    region: "ملی",
    version: "1395",
    title: "National Building Regulations — Part 3",
    author: "وزارت راه و شهرسازی",
    specification_count: 24,
    source_citation: "مقررات ملی ساختمان ایران، مبحث سوم، ویرایش ۱۳۹۵",
    created_at: "2026-05-02T07:00:00Z",
  },
  {
    uuid: "aaaa1111-0000-4000-8000-000000000003",
    name: "ضوابط شهرسازی شهرداری تهران",
    description: "تراکم، سطح اشغال، پارکینگ و عقب‌نشینی.",
    jurisdiction: "IR",
    region: "تهران",
    version: "1402",
    title: "Tehran Municipal Planning Rules",
    author: "شهرداری تهران",
    specification_count: 11,
    source_citation: "ضوابط و مقررات طرح تفصیلی شهر تهران، ۱۴۰۲",
    created_at: "2026-06-18T07:00:00Z",
  },
  {
    uuid: "aaaa1111-0000-4000-8000-000000000004",
    name: "چک‌لیست کنترل نقشه — معماری",
    description: "چک‌لیست سازمان نظام مهندسی برای کنترل نقشه‌های معماری.",
    jurisdiction: "IR",
    region: "تهران",
    version: "1401",
    title: "Plan Control Checklist — Architecture",
    author: "سازمان نظام مهندسی ساختمان",
    specification_count: 9,
    source_citation: "چک‌لیست کنترل نقشه معماری، سازمان نظام مهندسی، ۱۴۰۱",
    created_at: "2026-06-18T07:00:00Z",
  },
];

/**
 * A report with all three verdicts present, an omitted-entities tail, and two
 * specifications that established nothing -- one from a schema mismatch, one that matched
 * no subjects. Those two are what `ReportView`'s coverage block subtracts, so a report
 * fixture without them would render a coverage line that reads "N of N" and prove nothing.
 *
 * T-0034 review round 2 (F3). `entities`/`entities_omitted` are shaped the way
 * `cadgpt_engine.check._requirement` actually produces them, not typed to look plausible:
 * `outcomes = tuple(_outcome(...) for f in facet.failures)` never contains a `PASS` row
 * (`check.py:137`), and `entities = outcomes[:entity_limit]` / `entities_omitted =
 * max(0, len(outcomes) - entity_limit)` (`check.py:159-160`) together mean a requirement
 * with `entities_omitted > 0` always itemises *exactly* `entity_limit` entities, never more
 * and never fewer. This fixture picks one `entity_limit = 3` (a fixture-only stand-in for
 * `CHECK_ENTITY_LIMIT`, `services/api/cadgpt/config/settings/base.py:323` -- unrelated to
 * its real deployed value, which would make every array here unreadably long) and holds
 * every requirement in the object to it: the door-width requirement below keeps exactly 3
 * FAIL entities (the PASS row a previous version of this fixture mixed in is gone -- a
 * passing entity is never among `outcomes`, so it could never legitimately appear beside
 * failures here), the stairs requirement keeps exactly 3 INDETERMINATE entities, and the
 * spaces requirement -- which failed and indeterminate-classified nothing -- carries
 * `entities_omitted: 0`, because `len(outcomes) = failed + indeterminate = 0` leaves
 * nothing for any limit to cap.
 *
 * T-0049: the door-width and stairs specifications carry `rule_pack` pointing at
 * `DEFAULT_SELECTION[0]` (مبحث چهارم); the spaces and ramp specifications point at
 * `DEFAULT_SELECTION[1]` (مبحث سوم) -- two packs, each actually producing findings, so a
 * mis-wired attribution (every finding pointing at the same pack, say) would be visible
 * in the workbench. The elevator specification carries no `rule_pack` at all, exactly as
 * a report stored before this field existed would -- the fallback the workbench must
 * degrade through, not just the attributed case.
 */
export const report: Report = {
  schema_version: 5,
  engine_version: "0.4.1",
  ifc_filename: "niavaran-tower-A3.ifc",
  ifc_schema: "IFC4",
  ids_title: "مقررات ملی ساختمان — مبحث چهارم",
  disclosure_title: "این گزارش چه چیزی را بررسی کرده است",
  disclosure_text:
    "بررسی روی مدل niavaran-tower-A3.ifc انجام شده است. نقشه‌های ارائه‌شده برای پروانه بررسی نشده‌اند و این گزارش درباره مطابقت آن‌ها چیزی نمی‌گوید.",
  status: "FAIL",
  specifications_passed: 1,
  specifications_failed: 1,
  specifications_indeterminate: 2,
  passed: 34,
  failed: 11,
  indeterminate: 7,
  specifications: [
    {
      name: "درهای خروج باید دارای عرض حداقل ۹۰ سانتی‌متر باشند",
      rule_pack: {
        uuid: "aaaa1111-0000-4000-8000-000000000001",
        name: "مقررات ملی ساختمان — مبحث چهارم",
        version: "1399",
      },
      description: "All IFCDOOR data must have OverallWidth >= 900",
      applicability_description: "All IFCDOOR data must be an exit door type",
      applicability_text: "همه درهای دارای نوع خروج",
      instructions: "عرض بازشو از داخل چارچوب اندازه‌گیری می‌شود.",
      applicability: "APPLIES",
      status: "FAIL",
      cardinality: "required",
      matched: 20,
      reason_code: null,
      reason_label: null,
      established_nothing: false,
      passed: 9,
      failed: 11,
      indeterminate: 0,
      requirements: [
        {
          description: "OverallWidth >= 900",
          basis: {
            facet_type: "attribute",
            name: "OverallWidth",
            cardinality: "required",
            comparisons: [{ operator: ">=", value: "900" }],
          },
          requirement_text: "ویژگی OverallWidth باید بزرگ‌تر یا مساوی ۹۰۰ باشد",
          status: "FAIL",
          passed: 9,
          failed: 11,
          indeterminate: 0,
          entities: [
            {
              global_id: "2O2Fr$t4X7Zf8NOew3FLKU",
              ifc_class: "IfcDoor",
              status: "FAIL",
              reason_code: "VALUE_OUT_OF_BOUNDS",
              reason_label: "مقدار خارج از محدوده مجاز است",
              detail: "OverallWidth = 820",
            },
            {
              global_id: "1kTvXnbbzCWw8lcMd1dR4o",
              ifc_class: "IfcDoor",
              status: "FAIL",
              reason_code: "VALUE_OUT_OF_BOUNDS",
              reason_label: "مقدار خارج از محدوده مجاز است",
              detail: "OverallWidth = 750",
            },
            {
              global_id: "3ZYW5Q$rL5xO9pJ2mBvA1c",
              ifc_class: "IfcDoor",
              status: "FAIL",
              reason_code: "VALUE_OUT_OF_BOUNDS",
              reason_label: "مقدار خارج از محدوده مجاز است",
              detail: "OverallWidth = 860",
            },
          ],
          // 3 kept (== this fixture's entity_limit) + 8 omitted = 11 total failing
          // entities, matching `failed: 11` above exactly -- `check.py`'s `entities` is a
          // prefix of `outcomes`, never a mix that includes a passing entity.
          entities_omitted: 8,
        },
      ],
    },
    {
      name: "پله‌های فرار باید دارای دست‌انداز باشند",
      rule_pack: {
        uuid: "aaaa1111-0000-4000-8000-000000000001",
        name: "مقررات ملی ساختمان — مبحث چهارم",
        version: "1399",
      },
      description: "All IFCSTAIR data must have Pset_StairCommon.HandrailProvided",
      applicability_description: "All IFCSTAIR data must be an escape stair",
      applicability_text: "همه پله‌های فرار",
      instructions: "",
      applicability: "APPLIES",
      status: "INDETERMINATE",
      cardinality: "required",
      matched: 7,
      reason_code: null,
      reason_label: null,
      established_nothing: false,
      passed: 0,
      failed: 0,
      indeterminate: 7,
      requirements: [
        {
          description: "Pset_StairCommon.HandrailProvided must exist",
          basis: {
            facet_type: "property",
            name: "HandrailProvided",
            cardinality: "required",
            comparisons: [],
          },
          requirement_text: "ویژگی Pset_StairCommon.HandrailProvided باید موجود باشد",
          status: "INDETERMINATE",
          passed: 0,
          failed: 0,
          indeterminate: 7,
          entities: [
            {
              global_id: "3Xq8Lm2ZTCUvKp7nR4sYbW",
              ifc_class: "IfcStair",
              status: "INDETERMINATE",
              reason_code: "PROPERTY_MISSING",
              reason_label: "ویژگی در مدل ثبت نشده است",
              detail: "Pset_StairCommon",
            },
            {
              global_id: "1Bd7Kp4WQAErTn9mX2vZcU",
              ifc_class: "IfcStair",
              status: "INDETERMINATE",
              reason_code: "PROPERTY_MISSING",
              reason_label: "ویژگی در مدل ثبت نشده است",
              detail: "Pset_StairCommon",
            },
            {
              global_id: "5Fq9Rp2XZBEwUo1nY3wDaV",
              ifc_class: "IfcStair",
              status: "INDETERMINATE",
              reason_code: "PROPERTY_MISSING",
              reason_label: "ویژگی در مدل ثبت نشده است",
              detail: "Pset_StairCommon",
            },
          ],
          // 3 kept (== this fixture's entity_limit) + 4 omitted = 7 total indeterminate
          // entities, matching `indeterminate: 7` above exactly.
          entities_omitted: 4,
        },
      ],
    },
    {
      name: "فضاها باید دارای نام باشند",
      rule_pack: {
        uuid: "aaaa1111-0000-4000-8000-000000000002",
        name: "مقررات ملی ساختمان — مبحث سوم (حفاظت در برابر حریق)",
        version: "1395",
      },
      description: "All IFCSPACE data must have Name",
      applicability_description: "All IFCSPACE data",
      applicability_text: "همه فضاها",
      instructions: "",
      applicability: "APPLIES",
      status: "PASS",
      cardinality: "required",
      matched: 25,
      reason_code: null,
      reason_label: null,
      established_nothing: false,
      passed: 25,
      failed: 0,
      indeterminate: 0,
      requirements: [
        {
          description: "Name must exist",
          basis: {
            facet_type: "attribute",
            name: "Name",
            cardinality: "required",
            comparisons: [],
          },
          requirement_text: "ویژگی Name باید موجود باشد",
          status: "PASS",
          passed: 25,
          failed: 0,
          indeterminate: 0,
          // Every subject passed: `failed = indeterminate = 0`, so `len(outcomes) = 0` and
          // nothing is left for any limit to cap -- `entities_omitted` must be 0 here, not
          // a number implying a limit this requirement's own counts contradict.
          entities: [],
          entities_omitted: 0,
        },
      ],
    },
    {
      name: "پارکینگ‌ها باید دارای شیب مجاز باشند",
      rule_pack: {
        uuid: "aaaa1111-0000-4000-8000-000000000002",
        name: "مقررات ملی ساختمان — مبحث سوم (حفاظت در برابر حریق)",
        version: "1395",
      },
      description: "All IFCRAMP data must have Pset_RampCommon.Slope <= 15",
      applicability_text: "",
      instructions: "",
      applicability: "UNDETERMINED_APPLICABILITY",
      status: "INDETERMINATE",
      cardinality: "required",
      matched: 0,
      reason_code: "SCHEMA_MISMATCH",
      reason_label: "این مشخصه برای شمای IFC این مدل تعریف نشده است",
      established_nothing: true,
      passed: 0,
      failed: 0,
      indeterminate: 0,
      requirements: [],
    },
    {
      name: "آسانسورها باید دارای ابعاد حداقلی کابین باشند",
      description: "All IFCTRANSPORTELEMENT data must have Pset_TransportElementCommon",
      applicability_text: "",
      instructions: "",
      applicability: "DOES_NOT_APPLY",
      status: "INDETERMINATE",
      cardinality: "optional",
      matched: 0,
      reason_code: "NO_SUBJECTS_NOTHING_CHECKED",
      reason_label: "هیچ عنصری با این مشخصه مطابقت نداشت؛ چیزی بررسی نشد",
      established_nothing: true,
      passed: 0,
      failed: 0,
      indeterminate: 0,
      requirements: [],
    },
  ],
};

function run(overrides: Partial<CheckRunSummary> & { uuid: string }): CheckRunSummary {
  return {
    status: "succeeded",
    outcome: "",
    engine_version: "0.4.1",
    specifications_passed: 0,
    specifications_failed: 0,
    specifications_indeterminate: 0,
    passed: 0,
    failed: 0,
    indeterminate: 0,
    failure_reason: "",
    failure_detail: "",
    queued_at: null,
    started_at: null,
    finished_at: null,
    duration_seconds: null,
    report_file_url: null,
    report_generation_error: "",
    report_generation_detail: "",
    created_at: "2026-09-05T12:00:00Z",
    ...overrides,
  };
}

export const succeededRun: CheckRunSummary = run({
  uuid: "dddd0001-0000-4000-8000-000000000001",
  status: "succeeded",
  outcome: "FAIL",
  specifications_passed: 1,
  specifications_failed: 1,
  specifications_indeterminate: 2,
  passed: 34,
  failed: 3,
  indeterminate: 7,
  queued_at: "2026-09-05T12:00:00Z",
  started_at: "2026-09-05T12:00:03Z",
  finished_at: "2026-09-05T12:01:47Z",
  duration_seconds: 104,
  report_file_url:
    "/api/v1/reviews/cccc0001-0000-4000-8000-000000000001/runs/dddd0001-0000-4000-8000-000000000001/report-file/",
  created_at: "2026-09-05T12:00:00Z",
});

export const runningRun: CheckRunSummary = run({
  uuid: "dddd0002-0000-4000-8000-000000000002",
  status: "running",
  queued_at: "2026-09-06T08:14:00Z",
  started_at: "2026-09-06T08:14:06Z",
  created_at: "2026-09-06T08:14:00Z",
});

export const failedRun: CheckRunSummary = run({
  uuid: "dddd0003-0000-4000-8000-000000000003",
  status: "failed",
  failure_reason: "RESOURCE_EXHAUSTED",
  failure_detail: "بررسی این مدل از حافظه در دسترس فراتر رفت.",
  queued_at: "2026-09-04T17:31:00Z",
  started_at: "2026-09-04T17:31:04Z",
  finished_at: "2026-09-04T17:33:52Z",
  duration_seconds: 168,
  created_at: "2026-09-04T17:31:00Z",
});

/** A failure with no `failure_detail` -- `INTERNAL_ERROR` wraps whatever exception the
 * evaluator raised, and an exception raised with no message stringifies to `""`
 * (`services/api/cadgpt/apps/review/services/execution.py`, `CheckRunExecutor.execute`'s
 * `except Exception` branch). `failure_reason` is still guaranteed non-blank -- the
 * `failed_run_states_a_reason` constraint enforces that at the database -- so this is the
 * one field genuinely optional on a failed run, per T-0081. */
export const failedRunNoDetail: CheckRunSummary = run({
  uuid: "dddd0005-0000-4000-8000-000000000005",
  status: "failed",
  failure_reason: "INTERNAL_ERROR",
  failure_detail: "",
  queued_at: "2026-09-07T10:11:00Z",
  started_at: "2026-09-07T10:11:03Z",
  finished_at: "2026-09-07T10:11:19Z",
  duration_seconds: 16,
  created_at: "2026-09-07T10:11:00Z",
});

/** The older run in the history table, so "open a run that is not the newest" is
 * something the workbench can actually be clicked through. */
export const earlierRun: CheckRunSummary = run({
  uuid: "dddd0004-0000-4000-8000-000000000004",
  status: "succeeded",
  outcome: "FAIL",
  specifications_passed: 0,
  specifications_failed: 2,
  specifications_indeterminate: 2,
  passed: 21,
  failed: 9,
  indeterminate: 7,
  queued_at: "2026-09-01T09:02:00Z",
  started_at: "2026-09-01T09:02:05Z",
  finished_at: "2026-09-01T09:03:31Z",
  duration_seconds: 86,
  report_file_url:
    "/api/v1/reviews/cccc0001-0000-4000-8000-000000000001/runs/dddd0004-0000-4000-8000-000000000004/report-file/",
  created_at: "2026-09-01T09:02:00Z",
});

/** The default catalogue citation every fixture run carries, unless the run belongs to a
 * review with an uploaded `rule_set` -- that shape's real `rule_pack_selection` is always
 * `[]` (`_resolve_selection`, `review.py:148`), so `handlers.ts`'s run-detail handler
 * passes `[]` explicitly for it instead of this default.
 *
 * Two entries, not one (T-0049): `fx.report`'s specifications are split across both
 * (see the comment on `report` below), which is what makes a mis-wired attribution
 * visible in the workbench rather than trivially correct -- the same reason the live
 * two-pack proof this task's evidence rests on uses two packs that both produce
 * findings, not one. */
const DEFAULT_SELECTION: RulePackSelectionEntry[] = [
  {
    uuid: "aaaa1111-0000-4000-8000-000000000001",
    name: "مقررات ملی ساختمان — مبحث چهارم",
    jurisdiction: "IR",
    region: "ملی",
    version: "1399",
    specification_count: 18,
    checksum_sha256: "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f809",
    source_citation: "مقررات ملی ساختمان ایران، مبحث چهارم، ویرایش ۱۳۹۹",
  },
  {
    uuid: "aaaa1111-0000-4000-8000-000000000002",
    name: "مقررات ملی ساختمان — مبحث سوم (حفاظت در برابر حریق)",
    jurisdiction: "IR",
    region: "ملی",
    version: "1395",
    specification_count: 24,
    checksum_sha256: "2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8092",
    source_citation: "مقررات ملی ساختمان ایران، مبحث سوم، ویرایش ۱۳۹۵",
  },
];

export function detail(
  summary: CheckRunSummary,
  body: Report | null,
  selection: RulePackSelectionEntry[] = DEFAULT_SELECTION,
): CheckRunDetail {
  return {
    ...summary,
    report: body,
    model_checksum: "9f2c4a1b8e7d6c5b4a39281706f5e4d3c2b1a0998877665544332211000ffeedd",
    rule_set_checksum: "",
    rule_pack_selection: selection,
  };
}

function reviewOf(
  uuid: string,
  name: string,
  file: string,
  bytes: number,
  latest: CheckRunSummary | null,
  created: string,
): Review {
  return {
    uuid,
    name,
    model_file: model(file, bytes, `eeee${uuid.slice(4)}`),
    rule_set: null,
    latest_run: latest,
    created_at: created,
    updated_at: created,
  };
}

export const checkedReview: Review = reviewOf(
  "cccc0001-0000-4000-8000-000000000001",
  "کنترل معماری — فاز ۲",
  "niavaran-tower-A3.ifc",
  48_233_984,
  succeededRun,
  "2026-08-30T10:02:00Z",
);

export const runningReview: Review = reviewOf(
  "cccc0002-0000-4000-8000-000000000002",
  "کنترل حریق — بازنگری اول",
  "niavaran-tower-fire.ifc",
  51_118_080,
  runningRun,
  "2026-09-06T08:13:00Z",
);

export const failedReview: Review = reviewOf(
  "cccc0003-0000-4000-8000-000000000003",
  "کنترل سازه — مدل کامل",
  "niavaran-tower-full.ifc",
  412_663_808,
  failedRun,
  "2026-09-04T17:30:00Z",
);

export const failedReviewNoDetail: Review = reviewOf(
  "cccc0005-0000-4000-8000-000000000005",
  "کنترل تاسیسات — بازبینی نهایی",
  "niavaran-tower-mep.ifc",
  9_664_512,
  failedRunNoDetail,
  "2026-09-07T10:10:00Z",
);

/** An uploaded rule set (T-0048 F3), rather than a catalogue selection -- the review it
 * belongs to has `rule_set` set and `rule_pack_selection` empty for every one of its
 * runs. */
export const uploadedRuleSet: RuleSet = {
  uuid: "ffff0001-0000-4000-8000-000000000001",
  name: "مقررات دسترسی معلولان",
  description: "",
  title: "Accessible doors",
  author: "",
  version: "1.0",
  specification_count: 4,
  source_file: {
    uuid: "eeee0006-0000-4000-8000-000000000006",
    kind: "ids_ruleset",
    original_name: "accessible-doors.ids",
    content_type: "application/xml",
    size_bytes: 4_096,
    checksum_sha256: "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f809",
    created_at: "2026-08-20T09:00:00Z",
  },
  created_at: "2026-08-20T09:00:00Z",
};

export const failedRunRuleSet: CheckRunSummary = run({
  uuid: "dddd0006-0000-4000-8000-000000000006",
  status: "failed",
  failure_reason: "INVALID_RULE_SET",
  failure_detail: "فایل ذخیره‌شده برای این مجموعه‌قاعده قابل خواندن نبود.",
  queued_at: "2026-09-08T11:00:00Z",
  started_at: "2026-09-08T11:00:02Z",
  finished_at: "2026-09-08T11:00:05Z",
  duration_seconds: 3,
  created_at: "2026-09-08T11:00:00Z",
});

/** T-0048 F3: a failed run against an uploaded rule set. `rule_pack_selection` is empty
 * for this shape -- `handlers.ts`'s run-detail handler passes `[]` for it -- so the
 * failed-run card must name `rule_set` itself instead, not the (empty) pack list. */
export const failedReviewRuleSet: Review = {
  uuid: "cccc0006-0000-4000-8000-000000000006",
  name: "کنترل دسترسی — بازبینی نهایی",
  model_file: model("niavaran-tower-access.ifc", 12_582_912, "eeee0007-0000-4000-8000-000000000007"),
  rule_set: uploadedRuleSet,
  latest_run: failedRunRuleSet,
  created_at: "2026-09-08T10:59:00Z",
  updated_at: "2026-09-08T10:59:00Z",
};

export const neverRunReview: Review = reviewOf(
  "cccc0004-0000-4000-8000-000000000004",
  "کنترل معماری — فاز ۳",
  "niavaran-tower-A4.ifc",
  46_012_416,
  null,
  "2026-09-06T09:40:00Z",
);

export const reviews: Review[] = [
  runningReview,
  neverRunReview,
  checkedReview,
  failedReview,
];
