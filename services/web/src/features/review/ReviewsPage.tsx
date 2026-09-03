/**
 * The working screen: register a rule set, upload a model, run a check, read the report.
 *
 * Everything that takes time is asynchronous by construction. Starting a check returns a
 * queued run immediately and the page polls it; nothing here waits on a request that
 * could take minutes.
 *
 * A review checks against either an uploaded rule set (unchanged since before T-0031) or
 * the shipped catalogue. The catalogue path is selected by leaving the rule set picker on
 * its first option at review-creation time; the actual packs are chosen per check, in the
 * picker rendered beside a review that has none of its own -- `docs/tasks/
 * T-0031-rule-selection-on-the-run.md`, "the API accepting a selection when a check is
 * requested".
 */

import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "@/api/client";
import { isTerminal } from "@/api/types";
import {
  useCheckRun,
  useCreateReview,
  useCreateRuleSet,
  useReviews,
  useRulePacks,
  useRuleSets,
  useStartCheck,
} from "@/api/queries";
import { useSession } from "@/app/session-context";
import { ReportView } from "@/components/ReportView";
import { StatusPill } from "@/components/StatusPill";

export function ReviewsPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;

  const reviews = useReviews(slug);
  const ruleSets = useRuleSets(slug);
  const rulePacks = useRulePacks(slug);
  const createRuleSet = useCreateRuleSet(slug);
  const createReview = useCreateReview(slug);
  const startCheck = useStartCheck(slug);

  const [openReview, setOpenReview] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The packs picked for each catalogue-only review, keyed by review uuid -- a selection
  // made per check request, not stored on the review (T-0031).
  const [selection, setSelection] = useState<Record<string, string[]>>({});
  const [catalogueFilter, setCatalogueFilter] = useState({
    jurisdiction: "",
    region: "",
    version: "",
  });

  const run = useCheckRun(openReview ?? "", openRun);
  const currentReport = run.data?.report ?? null;
  const reportFileUrl = run.data?.report_file_url ?? null;

  const filteredPacks = useMemo(() => {
    const packs = rulePacks.data?.results ?? [];
    return packs.filter(
      (pack) =>
        pack.jurisdiction.toLowerCase().includes(catalogueFilter.jurisdiction.toLowerCase()) &&
        pack.region.toLowerCase().includes(catalogueFilter.region.toLowerCase()) &&
        pack.version.toLowerCase().includes(catalogueFilter.version.toLowerCase()),
    );
  }, [rulePacks.data, catalogueFilter]);

  function report(caught: unknown) {
    setError(caught instanceof ApiError ? caught.message : t("error.generic"));
  }

  async function onDownloadReportFile(url: string) {
    setError(null);
    try {
      await api.download(url, "report.md");
    } catch (caught) {
      report(caught);
    }
  }

  async function onAddRuleSet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File)) return;
    try {
      await createRuleSet.mutateAsync({ file, name: String(form.get("name") ?? "") });
      event.currentTarget.reset();
    } catch (caught) {
      report(caught);
    }
  }

  async function onCreateReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File)) return;
    try {
      await createReview.mutateAsync({
        file,
        name: String(form.get("name") ?? ""),
        ruleSet: String(form.get("rule_set") ?? ""),
      });
      event.currentTarget.reset();
    } catch (caught) {
      report(caught);
    }
  }

  function togglePack(reviewUuid: string, packUuid: string, checked: boolean) {
    setSelection((current) => {
      const picked = new Set(current[reviewUuid] ?? []);
      if (checked) picked.add(packUuid);
      else picked.delete(packUuid);
      return { ...current, [reviewUuid]: [...picked] };
    });
  }

  async function onCheck(reviewUuid: string, rulePacksForReview?: string[]) {
    setError(null);
    try {
      const queued = await startCheck.mutateAsync({
        reviewUuid,
        rulePacks: rulePacksForReview,
      });
      setOpenReview(reviewUuid);
      setOpenRun(queued.uuid);
    } catch (caught) {
      report(caught);
    }
  }

  return (
    <main className="page">
      {error && <p className="error">{error}</p>}

      <section className="card">
        <h2>{t("ruleSet.title")}</h2>
        <ul className="list">
          {ruleSets.data?.results.map((ruleSet) => (
            <li key={ruleSet.uuid}>
              <strong>{ruleSet.name}</strong>
              <span className="muted">
                {" "}
                {t("ruleSet.specifications", { count: ruleSet.specification_count })}
              </span>
            </li>
          ))}
        </ul>
        <form className="row" onSubmit={onAddRuleSet}>
          <input name="name" placeholder={t("review.name")} required />
          <input name="file" type="file" accept=".ids,.xml" required />
          <button type="submit" disabled={createRuleSet.isPending}>
            {t("ruleSet.new")}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>{t("review.title")}</h2>
        <form className="row" onSubmit={onCreateReview}>
          <input name="name" placeholder={t("review.name")} required />
          <select name="rule_set" defaultValue="">
            <option value="">{t("review.ruleSetNone")}</option>
            {ruleSets.data?.results.map((ruleSet) => (
              <option key={ruleSet.uuid} value={ruleSet.uuid}>
                {ruleSet.name}
              </option>
            ))}
          </select>
          <input name="file" type="file" accept=".ifc,.ifcxml,.ifczip" required />
          <button type="submit" disabled={createReview.isPending}>
            {t("review.create")}
          </button>
        </form>

        {reviews.data?.results.length === 0 && <p className="muted">{t("review.empty")}</p>}

        <ul className="list">
          {reviews.data?.results.map((review) => {
            const latest = review.latest_run;
            const busy = latest !== null && !isTerminal(latest.status);
            const usesCatalogue = review.rule_set === null;
            const picked = selection[review.uuid] ?? [];

            return (
              <li key={review.uuid} className="review">
                <div className="review__head">
                  <div>
                    <strong>{review.name}</strong>
                    <p className="muted ltr">{review.model_file.original_name}</p>
                  </div>
                  <div className="review__state">
                    {latest ? (
                      <>
                        <span className="muted">{t(`status.${latest.status}`)}</span>
                        {latest.outcome && <StatusPill status={latest.outcome} />}
                      </>
                    ) : (
                      <span className="muted">{t("review.neverRun")}</span>
                    )}
                    {!usesCatalogue && (
                      <button
                        type="button"
                        onClick={() => void onCheck(review.uuid)}
                        disabled={busy || startCheck.isPending}
                      >
                        {busy ? t("review.checking") : t("review.check")}
                      </button>
                    )}
                    {latest && isTerminal(latest.status) && (
                      <button
                        type="button"
                        onClick={() => {
                          setOpenReview(review.uuid);
                          setOpenRun(latest.uuid);
                        }}
                      >
                        {t("report.summary")}
                      </button>
                    )}
                  </div>
                </div>

                {usesCatalogue && (
                  <div className="review__catalogue" data-testid="catalogue-picker">
                    <p className="muted">{t("review.catalogue.title")}</p>
                    <div className="row">
                      <input
                        placeholder={t("review.catalogue.jurisdiction")}
                        value={catalogueFilter.jurisdiction}
                        onChange={(e) =>
                          setCatalogueFilter((f) => ({ ...f, jurisdiction: e.target.value }))
                        }
                      />
                      <input
                        placeholder={t("review.catalogue.region")}
                        value={catalogueFilter.region}
                        onChange={(e) =>
                          setCatalogueFilter((f) => ({ ...f, region: e.target.value }))
                        }
                      />
                      <input
                        placeholder={t("review.catalogue.version")}
                        value={catalogueFilter.version}
                        onChange={(e) =>
                          setCatalogueFilter((f) => ({ ...f, version: e.target.value }))
                        }
                      />
                    </div>
                    {filteredPacks.length === 0 && (
                      <p className="muted">{t("review.catalogue.empty")}</p>
                    )}
                    <ul className="list">
                      {filteredPacks.map((pack) => (
                        <li key={pack.uuid}>
                          <label>
                            <input
                              type="checkbox"
                              checked={picked.includes(pack.uuid)}
                              onChange={(e) =>
                                togglePack(review.uuid, pack.uuid, e.target.checked)
                              }
                            />
                            {" "}
                            {pack.name}
                            <span className="muted">
                              {" "}
                              — {pack.jurisdiction}
                              {pack.region ? `/${pack.region}` : ""} v{pack.version}
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      onClick={() => void onCheck(review.uuid, picked)}
                      disabled={busy || picked.length === 0 || startCheck.isPending}
                    >
                      {busy ? t("review.checking") : t("review.catalogue.checkSelected")}
                    </button>
                  </div>
                )}

                {latest && latest.status === "succeeded" && (
                  <p className="muted">
                    {latest.passed} / {latest.failed} / {latest.indeterminate}
                  </p>
                )}
                {latest && latest.status === "failed" && (
                  <p className="error">{latest.failure_detail || latest.failure_reason}</p>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {reportFileUrl && (
        <p>
          <button
            type="button"
            data-testid="report-file-link"
            onClick={() => void onDownloadReportFile(reportFileUrl)}
          >
            {t("report.downloadFile")}
          </button>
        </p>
      )}
      {currentReport && (
        <ReportView
          report={currentReport}
          rulePackSelection={run.data?.rule_pack_selection ?? []}
        />
      )}
    </main>
  );
}
