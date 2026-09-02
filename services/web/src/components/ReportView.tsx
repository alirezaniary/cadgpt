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

import type { EntityOutcome, Report, SpecificationOutcome, Status } from "@/api/types";
import { StatusPill } from "@/components/StatusPill";

/** FAIL first, then INDETERMINATE, then PASS. INDETERMINATE never sorts under PASS. */
const SEVERITY_RANK: Record<Status, number> = { FAIL: 0, INDETERMINATE: 1, PASS: 2 };

/** Stable sort by three-valued severity: equal-severity items keep the rule author's order. */
function bySeverity<T extends { status: Status }>(items: readonly T[]): T[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => SEVERITY_RANK[a.item.status] - SEVERITY_RANK[b.item.status] || a.index - b.index)
    .map(({ item }) => item);
}

/** Reason codes `judge()` (`packages/engine/src/cadgpt_engine/check.py`) assigns only when a
 * specification's own applicability meant it established no compliance at all — a schema
 * mismatch, or an optional-cardinality specification that matched zero subjects. These are the
 * only two reason codes `judge()` pairs with an applicability other than `APPLIES`.
 *
 * A `matched == 0` specification that came back FAIL (`NO_SUBJECTS_BUT_REQUIRED` — a required
 * element is absent) or PASS (`NO_SUBJECTS_AND_PROHIBITED` — a prohibited element is confirmed
 * absent) is deliberately excluded: those are real, established verdicts the engine reached by
 * judging the model, not an absence of evidence, and naming either here beside "established
 * nothing" would contradict the very verdict rendered a few lines below it. Reading the reason
 * code the engine already assigned, rather than re-deriving `matched`/cardinality logic here,
 * is what keeps this predicate from silently diverging from `judge()` the next time it changes. */
const NOTHING_ESTABLISHED_REASONS: ReadonlySet<string> = new Set([
  "SCHEMA_MISMATCH",
  "NO_SUBJECTS_NOTHING_CHECKED",
]);

function establishedNothing(spec: SpecificationOutcome): boolean {
  return spec.reason_code !== null && NOTHING_ESTABLISHED_REASONS.has(spec.reason_code);
}

interface EntityFilter {
  FAIL: boolean;
  INDETERMINATE: boolean;
}

const ALL_VISIBLE: EntityFilter = { FAIL: true, INDETERMINATE: true };

function isVisible(entity: EntityOutcome, filter: EntityFilter): boolean {
  return entity.status === "PASS" ? true : filter[entity.status];
}

export function ReportView({ report }: { report: Report }) {
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
  const filterActive = !filter.FAIL || !filter.INDETERMINATE;
  const visibleCount = allEntities.filter((e) => isVisible(e, filter)).length;

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

      <div className="filter" role="group" aria-label={t("report.filter.label")}>
        <span className="filter__label">{t("report.filter.label")}</span>
        <label className="filter__option">
          <input
            type="checkbox"
            checked={filter.FAIL}
            onChange={(e) => setFilter((f) => ({ ...f, FAIL: e.target.checked }))}
          />
          {t("status.FAIL")}
        </label>
        <label className="filter__option">
          <input
            type="checkbox"
            checked={filter.INDETERMINATE}
            onChange={(e) => setFilter((f) => ({ ...f, INDETERMINATE: e.target.checked }))}
          />
          {t("status.INDETERMINATE")}
        </label>
      </div>
      {filterActive && (
        <p className="notice" data-testid="filter-banner">
          {t("report.filter.showing", { shown: visibleCount, total: allEntities.length })}
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
            <p className="muted">
              {t("report.matched", { count: spec.matched })} · {spec.cardinality}
            </p>
            {spec.applicability_description && (
              <p className="muted" data-testid="applicability">
                {spec.applicability_description}
              </p>
            )}
            {spec.reason_label && <p className="notice">{spec.reason_label}</p>}

            {spec.requirements.map((requirement, requirementIndex) => {
              const orderedEntities = bySeverity(requirement.entities);
              const visibleEntities = orderedEntities.filter((e) => isVisible(e, filter));
              return (
                <div key={requirementIndex} className="requirement">
                  <p className="requirement__description" data-testid="requirement-text">
                    {requirement.requirement_text ?? requirement.description}
                  </p>
                  {visibleEntities.length > 0 && (
                    <table className="entities">
                      <tbody>
                        {visibleEntities.map((entity) => (
                          <tr
                            key={`${entity.global_id}-${entity.reason_code}`}
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
                  )}
                  {orderedEntities.length > 0 && visibleEntities.length === 0 && (
                    <p className="notice" data-testid="requirement-all-hidden">
                      {t("report.filter.allHidden")}
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
