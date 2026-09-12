/**
 * A finished report.
 *
 * A disclosure is presented before coverage, which is presented before findings: "what
 * artifact did this check at all" is the prior question to "how much of the rule set was
 * evaluated" (`prd.md` 5.7, I7). `report.disclosure_title` / `report.disclosure_text` are
 * rendered as given, the same way `reason_label` and `requirement_text` are: this is report
 * prose, and report prose is composed server-side, in the reader's language, by
 * `cadgpt.apps.review.disclosure` (`docs/decisions.md`, "Report prose belongs to the
 * server, not to the frontend catalogue") -- never assembled here from an i18n key and a
 * raw filename. Coverage then states the size of the effective rule set, not just what
 * came out of it, and names every specification that established nothing (prd.md 5.7, I7).
 * Findings are then grouped by severity — FAIL, then
 * INDETERMINATE, then PASS, stably — so the pile where the model carried the datum and
 * broke the rule is read first, and an unknown is never buried under a pass
 * (`docs/decisions.md`, "Severity, for a report built on IDS, is the three-valued
 * status"). The status filter only ever offers FAIL and INDETERMINATE: passing entities
 * are counted but never itemised (`EntityOutcome`), so a PASS filter would always render
 * an empty list and read as "no passes found" — the inversion of the truth. The three
 * counts are counts of the run and never move when the filter changes.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type {
  EntityOutcome,
  Report,
  RulePackSelectionEntry,
  SpecificationOutcome,
  SpecificationRulePackRef,
  Status,
} from "@/api/types";
import { StatusPill } from "@/components/StatusPill";

/** FAIL first, then INDETERMINATE, then PASS. INDETERMINATE never sorts under PASS --
 * `SEVERITY_RANK` in `cadgpt_engine.status` (T-0052), which owns this ordering because it
 * is an ordering of `Status`, the engine's own vocabulary
 * (`docs/decisions.md`, "Severity, for a report built on IDS, is the three-valued
 * status"). `report_markdown.py` imports that constant directly; this module cannot
 * import Python, so it keeps its own copy for the client-side sort every render needs
 * (including the `UNKNOWN_STATUS_RANK` fallback just below, a forward-compatibility case
 * with no wire representation the server could hand down instead).
 * `test_report_markdown.py`'s `test_report_view_severity_rank_matches_the_engine` reads
 * this literal back out of this file and fails the build the moment the three known ranks
 * disagree with the engine's. */
const SEVERITY_RANK: Record<Status, number> = { FAIL: 0, INDETERMINATE: 1, PASS: 2 };

/** T-0035. A report is a persisted document that a *newer* engine may have written and an
 * *older* frontend may be reading back -- `REPORT_SCHEMA_VERSION` exists precisely because
 * that gap is expected. A status this build has never heard of is exactly the shape of an
 * established, unestablished-ness -- neither compliant (`PASS`) nor a compliance failure
 * this build actually determined (`FAIL`) -- so it is ranked exactly where INDETERMINATE
 * already sits: never above (more urgent than) a `FAIL` this build *did* establish, and
 * never buried under a `PASS`, which would silently assert compliance nobody checked. This
 * is the default `SEVERITY_RANK[status]` falls back to via `??` when `status` is not one of
 * the three keys the `Record` above declares -- without it, the lookup is `undefined`,
 * `undefined - n` is `NaN`, and `NaN || (a.index - b.index)` makes the *entire* comparator
 * fall through to index order, not just the unrecognised row (found by T-0025 review Q2). */
const UNKNOWN_STATUS_RANK = SEVERITY_RANK.INDETERMINATE;

/** Stable sort by three-valued severity: equal-severity items keep the rule author's order.
 * Exported for the unit test that feeds it a status outside `Status`'s vocabulary -- the
 * one shape a same-file story test cannot exercise, because `EntityFilter` has no key for
 * an unrecognised status either and would filter such a row out of the DOM entirely. */
export function bySeverity<T extends { status: Status }>(items: readonly T[]): T[] {
  const rank = (status: Status): number => SEVERITY_RANK[status] ?? UNKNOWN_STATUS_RANK;
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => rank(a.item.status) - rank(b.item.status) || a.index - b.index)
    .map(({ item }) => item);
}

/** T-0052: whether a specification established no compliance at all is no longer decided
 * here. It used to be a hand-copied set of reason codes (`judge()`,
 * `packages/engine/src/cadgpt_engine/check.py`) mirroring `_NOTHING_ESTABLISHED_REASONS`
 * in `report_markdown.py` -- two independent literals of the same three codes, with no
 * compiler or test enforcing they agreed, and they had already drifted once in wording
 * (`docs/tasks/T-0052-one-predicate-not-three-copies.md`). This module cannot import
 * Python, so it cannot consume `cadgpt_engine.established_nothing` the way
 * `report_markdown.py` now does directly; instead it reads `established_nothing`, the one
 * field `presentation.localize_report` computes from that same engine predicate and ships
 * on every specification (`SpecificationOutcome.established_nothing`, `api/types.ts`) --
 * the same "server sends the already-decided value, the screen never re-derives it"
 * pattern `reason_label` and `requirement_text` already established
 * (`docs/decisions.md`, "Report prose belongs to the server, not to the frontend
 * catalogue"). There is nothing left here to diverge from the engine. */
function establishedNothing(spec: SpecificationOutcome): boolean {
  return spec.established_nothing;
}

interface EntityFilter {
  FAIL: boolean;
  INDETERMINATE: boolean;
}

const ALL_VISIBLE: EntityFilter = { FAIL: true, INDETERMINATE: true };

function isVisible(entity: EntityOutcome, filter: EntityFilter): boolean {
  return entity.status === "PASS" ? true : filter[entity.status];
}

/**
 * The run's own citation (T-0031), rendered on its own so a run that never produced a
 * `Report` can still show it. Extracted out of `ReportView` for T-0048: a failed run has
 * no `report`, so `ReportView` never mounts for it, but `CheckRun.rule_pack_selection` is
 * recorded at dispatch time regardless of how the run ends -- "what was this supposed to
 * cover?" is exactly the question a failed run must still answer, most of all the run that
 * failed *because* a cited pack vanished (`RulePackCitationMismatchError` /
 * `CheckRunFailure.INVALID_RULE_SET`). `ReportView` below renders this same component so a
 * successful run's selection is not shown twice by two diverging implementations.
 */
export function RulePackSelectionList({
  selection,
  heading,
}: {
  selection: RulePackSelectionEntry[];
  /**
   * T-0048 fix-now (F1): "were checked" is only true on the path that actually
   * produced a `Report` -- this component is also mounted on a failed run, which by
   * definition never reached that point, so the heading must be chosen by the caller
   * rather than hard-coded to the claim only one of the two callers can make.
   * `"checked"` is `ReportView`'s own call, where a `Report` exists as proof;
   * `"selected"` is the honest wording for a run that has none.
   */
  heading: "checked" | "selected";
}) {
  const { t } = useTranslation();
  if (selection.length === 0) {
    return null;
  }
  return (
    <section className="selection" data-testid="rule-pack-selection">
      <h4>
        {t(heading === "checked" ? "report.selection.title" : "report.selection.titleSelected")}
      </h4>
      <ul className="list">
        {selection.map((pack) => (
          <li key={pack.uuid}>
            {pack.name}
            <span className="muted">
              {" "}
              — {pack.jurisdiction}
              {pack.region ? `/${pack.region}` : ""} v{pack.version}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * T-0049: which pack asserted one finding, and (when reachable) what that pack cites as
 * its authority -- `prd.md` 5.7's "a finding carries the pack identity and version that
 * produced it," rendered beside the verdict itself, not only in the selection block at
 * the top of the report. `pack` is the finding's own minimal citation (uuid, name,
 * version -- `SpecificationOutcome.rule_pack`); `selection` is the run's own
 * `rule_pack_selection`, resolved by `uuid` for the jurisdiction, region and
 * `source_citation` that entry additionally carries, rather than duplicating them onto
 * every specification. An entry this run's own selection has no match for (unreachable
 * through `CheckRunExecutor` itself, which builds both from the same citations -- but a
 * stored report can be read back long after the run that wrote it) still shows the
 * pack's own name and version, with no jurisdiction/region and no source line.
 */
function SpecificationSource({
  pack,
  selection,
}: {
  pack: SpecificationRulePackRef;
  selection: RulePackSelectionEntry[];
}) {
  const { t } = useTranslation();
  const entry = selection.find((candidate) => candidate.uuid === pack.uuid);
  const region = entry?.region ? `/${entry.region}` : "";
  const locator = `${entry?.jurisdiction ?? ""}${region} v${pack.version}`.trim();
  return (
    <p className="muted" data-testid="spec-source">
      {t("report.specSource", { name: pack.name, locator })}
      {entry?.source_citation && (
        <span data-testid="spec-source-citation">
          {" — "}
          {entry.source_citation}
        </span>
      )}
    </p>
  );
}

export function ReportView({
  report,
  rulePackSelection,
}: {
  report: Report;
  /** The run's own citation (T-0031) -- empty for a run against an uploaded rule set,
   * one entry per pack for a catalogue run. Rendered here, not composed from the
   * catalogue's current state, so it keeps showing what the run actually checked even
   * after the catalogue moves on. */
  rulePackSelection?: RulePackSelectionEntry[];
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<EntityFilter>(ALL_VISIBLE);

  const orderedSpecs = useMemo(() => bySeverity(report.specifications), [report.specifications]);
  const nothingEstablished = useMemo(
    () => report.specifications.filter(establishedNothing),
    [report.specifications],
  );
  // F1: a specification that established nothing was never evaluated, whatever status it
  // came back with. `specifications_passed + specifications_failed + specifications_indeterminate`
  // is identically `specifications.length` for every report the engine can produce
  // (`check.py`'s `_specification` assigns exactly one of the three statuses to every
  // specification, and `_aggregate`'s fallback is INDETERMINATE, never a fourth outcome) — so
  // that sum could never have been a measurement of coverage; it always read "N of N" even
  // when most of the rule set matched nothing. Deriving `evaluated` from the same predicate
  // as the "established nothing" list below ties the two together by construction: they
  // cannot disagree on screen, because they are counted from the same set.
  const evaluated = report.specifications.length - nothingEstablished.length;

  const allEntities = useMemo(
    () => report.specifications.flatMap((s) => s.requirements.flatMap((r) => r.entities)),
    [report.specifications],
  );
  // T-0034: `allEntities` is only what the engine itemised -- `check.py`'s
  // `DEFAULT_ENTITY_LIMIT` already truncated each requirement's non-passing entities
  // before this component ever sees the report, and the remainder is `entities_omitted`,
  // summed here across every requirement. This is a fact about the run, not about the
  // filter: it is never zero because a filter hid something, and unchecking every box in
  // the filter above never brings a capped entity back into `allEntities`. Naming it
  // separately from the filter's own hidden count is the whole fix -- see the banner below.
  const totalOmitted = useMemo(
    () =>
      report.specifications.reduce(
        (specSum, s) =>
          specSum + s.requirements.reduce((reqSum, r) => reqSum + r.entities_omitted, 0),
        0,
      ),
    [report.specifications],
  );
  const filterActive = !filter.FAIL || !filter.INDETERMINATE;
  const visibleCount = allEntities.filter((e) => isVisible(e, filter)).length;
  const hiddenByFilter = allEntities.length - visibleCount;

  return (
    <section className="report">
      <header className="report__header">
        <div>
          <h3>{report.ids_title || report.ifc_filename}</h3>
          <p className="muted">
            {report.ifc_filename} · {t("report.schema", { schema: report.ifc_schema })} ·{" "}
            {t("report.engine", { version: report.engine_version })}
          </p>
        </div>
        <StatusPill status={report.status} />
      </header>

      <section className="disclosure" data-testid="disclosure">
        <h4>{report.disclosure_title}</h4>
        <p>{report.disclosure_text}</p>
      </section>

      <RulePackSelectionList selection={rulePackSelection ?? []} heading="checked" />

      <section className="coverage" data-testid="coverage">
        <h4>{t("report.coverage.title")}</h4>
        <p>{t("report.coverage.evaluated", { evaluated, total: report.specifications.length })}</p>

        <div className="counts">
          <div className="count count--pass">
            <span className="count__value">{report.passed}</span>
            <span className="count__label">{t("report.passed")}</span>
          </div>
          <div className="count count--fail">
            <span className="count__value">{report.failed}</span>
            <span className="count__label">{t("report.failed")}</span>
          </div>
          <div className="count count--indeterminate">
            <span className="count__value">{report.indeterminate}</span>
            <span className="count__label">{t("report.indeterminate")}</span>
          </div>
        </div>
        {report.indeterminate > 0 && <p className="notice">{t("report.indeterminateNote")}</p>}

        {nothingEstablished.length > 0 && (
          <div className="coverage__nothing" data-testid="coverage-nothing-established">
            <p>
              {t("report.coverage.nothingEstablished", { count: nothingEstablished.length })}
            </p>
            <ul>
              {nothingEstablished.map((spec, index) => (
                <li key={`${spec.name}-${index}`}>{spec.name || t("report.nothingChecked")}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <div
        className="filter"
        role="group"
        aria-label={t("report.filter.label")}
        data-testid="filter-controls"
      >
        <span className="filter__label">{t("report.filter.label")}</span>
        <label className="filter__option">
          <input
            type="checkbox"
            data-testid="filter-option-fail"
            checked={filter.FAIL}
            onChange={(e) => setFilter((f) => ({ ...f, FAIL: e.target.checked }))}
          />
          {t("status.FAIL")}
        </label>
        <label className="filter__option">
          <input
            type="checkbox"
            data-testid="filter-option-indeterminate"
            checked={filter.INDETERMINATE}
            onChange={(e) => setFilter((f) => ({ ...f, INDETERMINATE: e.target.checked }))}
          />
          {t("status.INDETERMINATE")}
        </label>
      </div>
      {/* T-0034: this fires whether or not a filter is active, because the cap is a fact
          about the run -- a reader who unchecks nothing must still learn it, not only the
          reader who happens to have the filter banner below on screen. */}
      {totalOmitted > 0 && (
        <p className="notice" data-testid="filter-omitted-total">
          {t("report.filter.omittedTotal", { omitted: totalOmitted, itemised: allEntities.length })}
        </p>
      )}
      {filterActive && (
        <p className="notice" data-testid="filter-banner">
          {t("report.filter.showing", {
            shown: visibleCount,
            itemised: allEntities.length,
            hidden: hiddenByFilter,
          })}
        </p>
      )}

      <h4>{t("report.specifications")}</h4>
      <ul className="specs">
        {orderedSpecs.map((spec, index) => (
          <li key={`${spec.name}-${index}`} className="spec">
            <div className="spec__head">
              <strong>{spec.name || t("report.nothingChecked")}</strong>
              <StatusPill status={spec.status} />
            </div>
            {/* T-0049: absent for a run against an uploaded `RuleSet` (never combined
                from several packs to begin with) and for a report stored before this
                field existed -- present for every specification a catalogue run's
                `_attribute_specifications` actually attributed. */}
            {spec.rule_pack && (
              <SpecificationSource pack={spec.rule_pack} selection={rulePackSelection ?? []} />
            )}
            <p className="muted">
              {t("report.matched", { count: spec.matched })} ·{" "}
              {/* `spec.cardinality` is ifctester's own machine token
                  (`get_usage()`: "required" | "optional" | "prohibited", a closed
                  vocabulary -- `packages/engine/.venv/.../ifctester/ids.py`'s
                  `Cardinality`). Rendered through a key per value, the same way
                  `StatusPill` renders `Status`, rather than interpolated raw -- an
                  English machine token is not report prose and must not sit
                  untranslated inside an otherwise-localized sentence (T-0036). */}
              <span data-testid="cardinality">{t(`report.cardinality.${spec.cardinality}`)}</span>
            </p>
            {/* T-0039: `applicability_text` is the server's localized rendering of
                `applicability_facets` (only the `Entity` facet type is rendered into a
                sentence; every other facet type, and a report stored before this field
                existed, falls back to `applicability_description` -- computed server-side,
                never here), the same "engine names it, service words it" split
                `requirement_text` already established. */}
            {spec.applicability_text && (
              <p className="muted" data-testid="applicability">
                {spec.applicability_text}
              </p>
            )}
            {spec.reason_label && <p className="notice">{spec.reason_label}</p>}

            {spec.requirements.map((requirement, requirementIndex) => {
              const orderedEntities = bySeverity(requirement.entities);
              // T-0035. `entity.global_id` is `string | null` for a non-rooted IFC entity,
              // so two rows in the same requirement can share both a null `global_id` and
              // the same `reason_code` -- the row key below cannot be built from entity
              // fields alone without colliding. Pairing each entity with its index in
              // `orderedEntities` *before* the filter below runs makes that index a stable,
              // unique tiebreaker: unique because no two elements of an array share a
              // position, and stable across a filter toggle because it is assigned once,
              // pre-filter, not recomputed from `visibleEntities`'s own (filter-dependent)
              // position.
              const visibleEntities = orderedEntities
                .map((entity, entityIndex) => ({ entity, entityIndex }))
                .filter(({ entity }) => isVisible(entity, filter));
              return (
                <div key={requirementIndex} className="requirement">
                  <div className="requirement__head">
                    <p className="requirement__description" data-testid="requirement-text">
                      {requirement.requirement_text ?? requirement.description}
                    </p>
                    <StatusPill status={requirement.status} />
                  </div>
                  {/* T-0037: a requirement that evaluated nothing -- a prohibited
                      specification matching zero subjects is a real example, PASS at
                      the specification level while every requirement beneath it reads
                      INDETERMINATE with all-zero counts -- explains itself here rather
                      than leaving a bare status beside a description to look like it
                      contradicts the verdict above it (docs/decisions.md, "A
                      requirement that evaluated nothing is explained, never
                      suppressed"). Rendered in words, from the server's own gettext
                      wording, never the bare code. */}
                  {requirement.reason_label && (
                    <p className="notice" data-testid="requirement-reason">
                      {requirement.reason_label}
                    </p>
                  )}
                  {/* T-0037 review round 2 (F1): a requirement can genuinely evaluate
                      real entities -- a real status, real non-zero counts -- while the
                      specification it belongs to never established that it applies at
                      all (a schema mismatch is the case that reaches this today).
                      Rendering that verdict with no caveat asserts a compliance this run
                      never established was even applicable (CLAUDE.md, "Never assert
                      compliance we did not establish"). Mutually exclusive with the
                      reason_label notice above by construction on the server
                      (cadgpt_engine.check._specification): at most one of the two is
                      ever set on the same requirement. */}
                  {requirement.applicability_caveat_label && (
                    <p className="notice" data-testid="requirement-applicability-caveat">
                      {requirement.applicability_caveat_label}
                    </p>
                  )}
                  {visibleEntities.length > 0 && (
                    <div className="entities-scroll">
                      <table className="entities">
                        <tbody>
                          {visibleEntities.map(({ entity, entityIndex }) => (
                            <tr
                              key={`${entity.global_id}-${entity.reason_code}-${entityIndex}`}
                              data-testid="entity-row"
                              data-status={entity.status}
                            >
                              <td>
                                <StatusPill status={entity.status} />
                              </td>
                              <td className="ltr">{entity.ifc_class}</td>
                              <td className="ltr mono">{entity.global_id}</td>
                              <td data-testid="reason" data-reason-code={entity.reason_code}>
                                {entity.reason_label ?? entity.reason_code}
                              </td>
                              <td className="ltr mono muted" data-testid="detail">
                                {entity.detail}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {orderedEntities.length > 0 && visibleEntities.length === 0 && (
                    <p className="notice" data-testid="requirement-all-hidden">
                      {t("report.filter.allHidden")}
                    </p>
                  )}
                  {/* T-0034: the global banner is off-screen the moment a reader scrolls
                      into a long list, and "every row hidden" above says nothing when only
                      some of a requirement's rows are -- a requirement showing 2 of 30 rows
                      must not read identically to one with 2 findings. Local, not derived
                      from the global filter state, so it stays correct per requirement. */}
                  {visibleEntities.length > 0 && visibleEntities.length < orderedEntities.length && (
                    <p className="notice" data-testid="requirement-partially-hidden">
                      {t("report.filter.partiallyHidden", {
                        hidden: orderedEntities.length - visibleEntities.length,
                        total: orderedEntities.length,
                      })}
                    </p>
                  )}
                  {requirement.entities_omitted > 0 && (
                    <p className="muted">
                      {t("report.omitted", { count: requirement.entities_omitted })}
                    </p>
                  )}
                </div>
              );
            })}
          </li>
        ))}
      </ul>
    </section>
  );
}
