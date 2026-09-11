import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";

import type { EntityOutcome, RequirementOutcome, Report } from "@/api/types";
import { ReportView } from "@/components/ReportView";
import i18n from "@/i18n";
import * as fx from "@/mocks/fixtures";

/**
 * The report on its own, outside the review page -- useful when the thing under review is
 * the document itself rather than the screen around it.
 */
const meta = {
  title: "Components/Report",
  component: ReportView,
  decorators: [
    (Story) => (
      <main className="page">
        <Story />
      </main>
    ),
  ],
} satisfies Meta<typeof ReportView>;

export default meta;
type Story = StoryObj<typeof meta>;

/** All three verdicts, an omitted-entities tail, and two specifications that established
 * nothing -- so the coverage line reads "4 of 6" rather than the "6 of 6" a naive sum
 * would always produce. */
export const Full: Story = {
  args: { report: fx.report, rulePackSelection: fx.detail(fx.succeededRun, fx.report).rule_pack_selection },
};

/** A run against an uploaded rule set carries no catalogue citation, so the "rule packs
 * checked" block is absent rather than empty. */
export const WithoutPackCitation: Story = {
  args: { report: fx.report, rulePackSelection: [] },
};

/**
 * T-0034. `fx.report` already carries a real engine-shaped omission tail on two
 * requirements (`entities_omitted: 8, 4` -- T-0025's own fixture, not written for this
 * story) but none of its requirements mix FAIL and INDETERMINATE entities, so unchecking a
 * filter box always hides either none or all of a requirement's rows -- it cannot exercise
 * the "some but not all" signal this task adds.
 *
 * T-0034 review round 2 (F3). The one change below is exactly that mix, made the way
 * `check.py` could actually produce it: the door-width requirement's kept entities are
 * already at this fixture's `entity_limit` (3, see the comment on `fx.report`), so turning
 * one FAIL row INDETERMINATE has to *replace* a kept entity, never append a fourth --
 * appending would itemise more entities than the limit `entities_omitted: 8` implies,
 * which is the exact shape of inconsistency F3 found. `failed`/`indeterminate` move by one
 * in the same direction as the swapped row, so `failed + indeterminate` (11) still equals
 * `entities.length + entities_omitted` (3 + 8) after the change, exactly as it did before.
 * Nothing else about the fixture changes, and the wording asserted below is never typed
 * out here -- it is read back off the numbers this object already states
 * (`entities_omitted`, array lengths), the same computation `ReportView` itself performs,
 * so the assertion cannot have been written to match a payload tuned to produce it.
 */
const withMixedRequirement: Report = ((): Report => {
  return {
    ...fx.report,
    specifications: fx.report.specifications.map((spec, specIndex) => {
      if (specIndex !== 0) return spec;
      return {
        ...spec,
        requirements: spec.requirements.map((requirement, requirementIndex) => {
          if (requirementIndex !== 0) return requirement;
          return {
            ...requirement,
            failed: requirement.failed - 1,
            indeterminate: requirement.indeterminate + 1,
            entities: [
              // The first two kept FAIL entities are untouched; the third is replaced,
              // not appended to, so `entities.length` stays at this requirement's
              // `entity_limit` (see `fx.report`'s own comment on why that must hold).
              ...requirement.entities.slice(0, -1),
              {
                global_id: "4Nq1Zr$8pT2vXeR6cMdWlY",
                ifc_class: "IfcDoor",
                status: "INDETERMINATE",
                reason_code: "ATTRIBUTE_EMPTY",
                reason_label: "این ویژگی در مدل ثبت نشده است",
                detail: "OverallWidth",
              } satisfies EntityOutcome,
            ],
          };
        }),
      };
    }),
  };
})();

/** `report.specifications[0].requirements[0]` / `[1].requirements[0]` are the door-width
 * and stairs requirements this fixture has always had -- throwing rather than returning
 * `undefined` if that shape ever moves, so this story fails loudly instead of asserting
 * against nothing. */
function requirementAt(report: Report, specIndex: number, requirementIndex: number): RequirementOutcome {
  const requirement = report.specifications[specIndex]?.requirements[requirementIndex];
  if (!requirement) throw new Error(`fixture shape assumption broken at spec ${specIndex}`);
  return requirement;
}

/** How many findings exist, how many of them were itemised, and how many the filter is
 * hiding -- three numbers, asserted from the fixture's own counts, never collapsed into
 * two and never hand-typed to match the wording.
 *
 * T-0034 review round 2 (F1). `toHaveTextContent(String(n))` is an unanchored substring
 * match: it passes as long as `n` appears anywhere in the element, which cannot tell "the
 * omitted total landed in the filter's hidden-count slot" from "the filter's hidden count
 * is correct" -- exactly the defect this task exists to remove, reintroduced by mutation
 * and caught by nothing. Every assertion below instead builds the *entire* expected
 * sentence with `i18n.t` -- the same catalogue entry and interpolation `ReportView` itself
 * calls -- and compares the whole string. A bug that puts the wrong number in the wrong
 * `{{placeholder}}` renders a sentence that cannot equal one built from the correct
 * numbers in the correct slots, so a swap or a conflation fails this test even when every
 * number involved happens to also appear somewhere else on the page. The explicit
 * negative assertions after each comparison are belt-and-suspenders: they fail loudly,
 * with a readable message, on the two mutations the review round found, rather than
 * relying solely on a whole-string mismatch to point at the same bug. */
export const FilteredWithOmissionsAndAPartialRequirement: Story = {
  args: { report: withMixedRequirement, rulePackSelection: [] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const allRequirements = withMixedRequirement.specifications.flatMap((s) => s.requirements);
    const totalOmitted = allRequirements.reduce((sum, r) => sum + r.entities_omitted, 0);
    const totalItemised = allRequirements.flatMap((r) => r.entities).length;

    // Present before any filter is touched: the cap is a fact about the run, not about
    // the filter, and a reader who unchecks nothing must still see it.
    const omittedNotice = await waitFor(() => canvas.getByTestId("filter-omitted-total"));
    const expectedOmittedNotice = i18n.t("report.filter.omittedTotal", {
      omitted: totalOmitted,
      itemised: totalItemised,
    });
    await expect(omittedNotice).toHaveTextContent(expectedOmittedNotice);

    const indeterminateBox = canvas.getByRole("checkbox", { name: "نامشخص" });
    await userEvent.click(indeterminateBox);

    // The global banner: itemised and filter-hidden are two different numbers, and
    // neither is the omitted total above.
    const banner = await waitFor(() => canvas.getByTestId("filter-banner"));
    const doorRequirementNow = requirementAt(withMixedRequirement, 0, 0);
    const doorOrdered = doorRequirementNow.entities.length;
    const doorHidden = doorRequirementNow.entities.filter((e) => e.status === "INDETERMINATE").length;
    const doorVisible = doorOrdered - doorHidden;
    const stairsRequirement = requirementAt(withMixedRequirement, 1, 0);
    const shown = doorVisible; // the stairs requirement's entities are all INDETERMINATE, now fully hidden
    const hiddenByFilter = totalItemised - shown;
    const expectedBanner = i18n.t("report.filter.showing", {
      shown,
      itemised: totalItemised,
      hidden: hiddenByFilter,
    });
    await expect(banner).toHaveTextContent(expectedBanner);
    // Belt-and-suspenders (F1): construct the two concrete wrong sentences the review
    // round actually produced by mutation -- the engine's omitted total re-attributed to
    // the filter's hidden count, and shown/hidden swapped -- and assert the banner is
    // neither, rather than relying only on a mismatch against the correct sentence to
    // point at the right cause. Both guards require the two numbers being swapped to
    // actually differ in this fixture, or the negative assertion would be vacuous.
    expect(totalOmitted, "fixture must be able to distinguish omitted from hidden").not.toBe(hiddenByFilter);
    const omittedMistakenForHidden = i18n.t("report.filter.showing", {
      shown,
      itemised: totalItemised,
      hidden: totalOmitted,
    });
    expect(banner.textContent).not.toBe(omittedMistakenForHidden);

    expect(shown, "fixture must be able to distinguish shown from hidden").not.toBe(hiddenByFilter);
    const shownHiddenSwapped = i18n.t("report.filter.showing", {
      shown: hiddenByFilter,
      itemised: totalItemised,
      hidden: shown,
    });
    expect(banner.textContent).not.toBe(shownHiddenSwapped);

    // The door-width requirement: some rows hidden, not all -- the new local signal.
    const partial = await waitFor(() => canvas.getByTestId("requirement-partially-hidden"));
    const expectedPartial = i18n.t("report.filter.partiallyHidden", {
      hidden: doorHidden,
      total: doorOrdered,
    });
    await expect(partial).toHaveTextContent(expectedPartial);

    // The stairs requirement: every row was INDETERMINATE, so it still reads "all hidden",
    // the case this task deliberately left alone.
    expect(stairsRequirement.entities.every((e) => e.status === "INDETERMINATE")).toBe(true);
    await expect(canvas.getAllByTestId("requirement-all-hidden").length).toBeGreaterThan(0);
  },
};

/**
 * T-0035. `entity.global_id` is `string | null` for a non-rooted IFC entity, so two rows in
 * one requirement can share both a null `global_id` and the same `reason_code` -- the row
 * key built from those two fields alone collides. Two such rows sit in the door-width
 * requirement below (replacing two of its three kept entities, which this fixture's own
 * comment already establishes are exactly at `entity_limit`): `keyed-a` stays `FAIL`
 * exactly as the entity it replaces was, so `requirement.failed`/`indeterminate` need no
 * adjustment for it; `keyed-b` moves from the `FAIL` it replaces to `INDETERMINATE`, so
 * `failed`/`indeterminate` move by one in the same direction the existing
 * `withMixedRequirement` fixture above already establishes is safe.
 */
const withDuplicateKeyEntities: Report = ((): Report => {
  return {
    ...fx.report,
    specifications: fx.report.specifications.map((spec, specIndex) => {
      if (specIndex !== 0) return spec;
      return {
        ...spec,
        requirements: spec.requirements.map((requirement, requirementIndex) => {
          if (requirementIndex !== 0) return requirement;
          return {
            ...requirement,
            failed: requirement.failed - 1,
            indeterminate: requirement.indeterminate + 1,
            entities: [
              // The first kept entity is untouched; the other two -- both `FAIL` in the
              // base fixture -- are replaced (not appended) so `entities.length` stays at
              // this requirement's `entity_limit`.
              requirement.entities[0]!,
              {
                global_id: null,
                ifc_class: "IfcDoor",
                status: "FAIL",
                reason_code: "SAME_REASON_CODE",
                reason_label: null,
                detail: "keyed-a",
              },
              {
                global_id: null,
                ifc_class: "IfcDoor",
                status: "INDETERMINATE",
                reason_code: "SAME_REASON_CODE",
                reason_label: null,
                detail: "keyed-b",
              },
            ],
          };
        }),
      };
    }),
  };
})();

/** Before the fix, `keyed-a` and `keyed-b` above render the identical React key
 * (`null-SAME_REASON_CODE`) -- two siblings in the same list with the same key, which
 * React's own reconciler rejects with a "same key" warning and is then free to resolve
 * however it likes, including reusing one row's already-mounted DOM node for the other
 * row's data across a reconciliation. Unchecking, then rechecking, the INDETERMINATE
 * filter forces exactly that: `keyed-b` (INDETERMINATE) leaves and re-enters the rendered
 * list while `keyed-a` (FAIL) stays put throughout, so a reconciler confused about which
 * row is which has two chances to show a stale or duplicated row instead of the one the
 * filter asked for. Spying on `console.error` catches the warning React itself emits the
 * moment it sees the collision, which is the one signal that survives even where the
 * rendered *text* happens to still come out right by luck of this particular row markup
 * being purely derived from props with no per-row state of its own. */
export const DuplicateGlobalIdKeysSurviveAFilterToggle: Story = {
  args: { report: withDuplicateKeyEntities, rulePackSelection: [] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const keyWarnings: unknown[][] = [];
    const originalConsoleError = console.error;
    console.error = (...args: unknown[]) => {
      keyWarnings.push(args);
      originalConsoleError(...args);
    };

    try {
      // Both rows present from the start: the default filter shows FAIL and
      // INDETERMINATE alike.
      await waitFor(() => expect(canvas.getByText("keyed-a")).toBeInTheDocument());
      expect(canvas.getByText("keyed-b")).toBeInTheDocument();

      const indeterminateBox = canvas.getByRole("checkbox", { name: "نامشخص" });

      // Hide INDETERMINATE: `keyed-b` leaves the rendered list, `keyed-a` (FAIL) must
      // stay -- and keep its own row, not `keyed-b`'s stale content.
      await userEvent.click(indeterminateBox);
      await waitFor(() => expect(canvas.queryByText("keyed-b")).not.toBeInTheDocument());
      expect(canvas.getByText("keyed-a")).toBeInTheDocument();

      // Show INDETERMINATE again: both rows must come back, each with its own content --
      // not one row duplicated under two labels, not one row lost.
      await userEvent.click(indeterminateBox);
      await waitFor(() => expect(canvas.getByText("keyed-b")).toBeInTheDocument());
      expect(canvas.getByText("keyed-a")).toBeInTheDocument();
      expect(canvas.getAllByText(/^keyed-[ab]$/).length).toBe(2);

      // The defect's own signature: React warns the instant it renders two siblings with
      // the same key. None of the renders above may have logged one.
      const sameKeyWarning = keyWarnings.find((args) =>
        args.some((arg) => typeof arg === "string" && arg.includes("same key")),
      );
      expect(sameKeyWarning, `console.error was called with: ${JSON.stringify(keyWarnings)}`).toBeUndefined();
    } finally {
      console.error = originalConsoleError;
    }
  },
};

/**
 * Everything passed. The indeterminate count is still rendered, still in its own column,
 * still at the same weight -- a clean report is three zeros and a total, never two
 * columns.
 */
export const NothingToReport: Story = {
  args: {
    rulePackSelection: [],
    report: ((): Report => {
      const passing = fx.report.specifications.filter((spec) => spec.status === "PASS");
      return {
        ...fx.report,
        status: "PASS",
        specifications_passed: passing.length,
        specifications_failed: 0,
        specifications_indeterminate: 0,
        passed: 25,
        failed: 0,
        indeterminate: 0,
        specifications: passing,
      };
    })(),
  },
};
