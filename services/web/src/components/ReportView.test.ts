/**
 * T-0035. `bySeverity` is a pure function over a payload -- a browser is not the right
 * instrument for its one defect (an out-of-vocabulary `status` silently disabling severity
 * ordering for the *entire* list, not just the unrecognised row), so this is a plain
 * Vitest unit test, not a Storybook story: `EntityFilter` (`isVisible` in ReportView.tsx)
 * has no key for a status outside `Status`'s three members either, and would filter such a
 * row out of the rendered DOM entirely before the sort defect could ever be observed
 * on-screen. Run via the `unit` Vitest project (`vitest.config.ts`), wired into
 * `pnpm run verify` as `test-unit`.
 */
import { describe, expect, it } from "vitest";

import type { Status } from "@/api/types";
import { bySeverity } from "@/components/ReportView";

interface Row {
  status: Status;
  id: string;
}

describe("bySeverity", () => {
  it("keeps FAIL leading, and never drops the row, when a status outside the vocabulary is present", () => {
    // "WEIRD" is not a member of `Status` and this build's own encoder could never produce
    // it -- but a report is a persisted document a *newer* engine may have written, and
    // `REPORT_SCHEMA_VERSION` exists precisely because that gap is expected. Before the
    // fix: `SEVERITY_RANK["WEIRD"]` is `undefined`, `undefined - n` is `NaN`, and
    // `NaN || (a.index - b.index)` makes the *whole* comparator fall through to index
    // order -- unsorting every row, not just this one. This list is deliberately shuffled
    // so that index order alone would put a PASS ahead of the FAIL.
    const shuffled: Row[] = [
      { status: "PASS", id: "pass-1" },
      { status: "WEIRD" as unknown as Status, id: "unknown-1" },
      { status: "PASS", id: "pass-2" },
      { status: "FAIL", id: "fail-1" },
      { status: "INDETERMINATE", id: "indeterminate-1" },
    ];

    const sorted = bySeverity(shuffled);

    // Not silently dropped: every row, including the unrecognised one, survives the sort.
    expect(sorted).toHaveLength(shuffled.length);
    expect(sorted.map((row) => row.id)).toContain("unknown-1");

    // FAIL still leads the list -- the whole point of severity ordering (T-0025) -- even
    // though a row this build cannot classify sits beside it.
    expect(sorted[0]?.status).toBe("FAIL");

    // The unknown row must never rank as more urgent than a FAIL this build *did*
    // establish: it cannot sort ahead of the FAIL row.
    const failIndex = sorted.findIndex((row) => row.status === "FAIL");
    const unknownIndex = sorted.findIndex((row) => row.id === "unknown-1");
    expect(failIndex).toBe(0);
    expect(unknownIndex).toBeGreaterThan(failIndex);
  });

  it("is a stable sort: equal-severity rows keep the input order", () => {
    const rows: Row[] = [
      { status: "PASS", id: "pass-a" },
      { status: "FAIL", id: "fail-a" },
      { status: "PASS", id: "pass-b" },
      { status: "FAIL", id: "fail-b" },
    ];

    const sorted = bySeverity(rows);

    expect(sorted.map((row) => row.id)).toEqual(["fail-a", "fail-b", "pass-a", "pass-b"]);
  });
});
