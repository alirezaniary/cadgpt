/**
 * A review's own detail page: the catalogue picker and "run check" action, a list of
 * this review's past runs, and -- inline below that -- the currently-open run's report.
 * This is where the product owner's "detail of each review... the result and stuff"
 * lives, not on a tenant-wide dashboard.
 *
 * `onCheck`, `togglePack`, `catalogueFilter`, the report-file download/generate
 * handlers, and `ReportView`'s usage are moved here verbatim from the old
 * `ReviewsPage.tsx` (T-0074) -- one review's worth of that page's state, not a rewrite.
 */

import { useParams } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "@/api/client";
import {
  useCheckRun,
  useCheckRuns,
  useGenerateReportFile,
  useReview,
  useRulePacks,
  useStartCheck,
} from "@/api/queries";
import { isTerminal } from "@/api/types";
import { useSession } from "@/app/session-context";
import { ReportView } from "@/components/ReportView";
import { StatusPill } from "@/components/StatusPill";
import { formatDate } from "@/lib/dates";

export function ReviewDetailPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const { reviewUuid } = useParams({ from: "/projects/$projectUuid/reviews/$reviewUuid" });

  const review = useReview(slug, reviewUuid);
  const rulePacks = useRulePacks(slug);
  const runs = useCheckRuns(reviewUuid);
  const startCheck = useStartCheck(slug);
  const generateReportFile = useGenerateReportFile(slug);

  const [openRun, setOpenRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedPacks, setSelectedPacks] = useState<string[]>([]);
  const [catalogueFilter, setCatalogueFilter] = useState({
    jurisdiction: "",
    region: "",
    version: "",
  });

  // The most recent run opens itself once the run list first arrives, so the report is
  // visible without an extra click for the common case; a person can still open an
  // older run explicitly afterward.
  useEffect(() => {
    if (openRun !== null) return;
    const newest = runs.data?.results[0];
    if (newest) setOpenRun(newest.uuid);
  }, [runs.data, openRun]);

  const run = useCheckRun(reviewUuid, openRun);
  const currentReport = run.data?.report ?? null;
  const reportFileUrl = run.data?.report_file_url ?? null;
  const reportGenerationError = run.data?.report_generation_error ?? "";
  const reportFileMissing =
    run.data?.status === "succeeded" && !reportFileUrl && !reportGenerationError;

  const usesCatalogue = review.data ? review.data.rule_set === null : false;
  // The currently-open run's own status (`useCheckRun`, polled every 1.5s) is fresher
  // than the runs-history snapshot (`useCheckRuns`, polled every 2s and started on a
  // different clock) -- trusting the list here left the "run check" button reading
  // "Checking..." and the history row reading "Queued" for a couple of seconds after a
  // run had actually succeeded and its report was already rendering, caught by this
  // task's own real-path run against the live stack. Fall back to the list only when no
  // run is open yet (e.g. a review whose only run was started from elsewhere).
  const busy = openRun
    ? run.data
      ? !isTerminal(run.data.status)
      : true
    : (runs.data?.results.some((candidate) => !isTerminal(candidate.status)) ?? false);

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

  async function onGenerateReportFile() {
    if (!openRun) return;
    setError(null);
    try {
      await generateReportFile.mutateAsync({ reviewUuid, runUuid: openRun });
    } catch (caught) {
      report(caught);
    }
  }

  function togglePack(packUuid: string, checked: boolean) {
    setSelectedPacks((current) => {
      const picked = new Set(current);
      if (checked) picked.add(packUuid);
      else picked.delete(packUuid);
      return [...picked];
    });
  }

  async function onCheck(rulePacksForReview?: string[]) {
    setError(null);
    try {
      const queued = await startCheck.mutateAsync({ reviewUuid, rulePacks: rulePacksForReview });
      setOpenRun(queued.uuid);
    } catch (caught) {
      report(caught);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <h1>{review.data?.name ?? "…"}</h1>
        {review.data && <p className="muted ltr">{review.data.model_file.original_name}</p>}

        {error && <p className="error">{error}</p>}

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
                onChange={(e) => setCatalogueFilter((f) => ({ ...f, region: e.target.value }))}
              />
              <input
                placeholder={t("review.catalogue.version")}
                value={catalogueFilter.version}
                onChange={(e) => setCatalogueFilter((f) => ({ ...f, version: e.target.value }))}
              />
            </div>
            {filteredPacks.length === 0 && <p className="muted">{t("review.catalogue.empty")}</p>}
            <ul className="list">
              {filteredPacks.map((pack) => (
                <li key={pack.uuid}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selectedPacks.includes(pack.uuid)}
                      onChange={(e) => togglePack(pack.uuid, e.target.checked)}
                    />{" "}
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
              onClick={() => void onCheck(selectedPacks)}
              disabled={busy || selectedPacks.length === 0 || startCheck.isPending}
            >
              {busy ? t("review.checking") : t("review.catalogue.checkSelected")}
            </button>
          </div>
        )}
        {!usesCatalogue && (
          <button
            type="button"
            onClick={() => void onCheck()}
            disabled={busy || startCheck.isPending}
          >
            {busy ? t("review.checking") : t("review.check")}
          </button>
        )}
      </section>

      <section className="card">
        <h2>{t("run.history")}</h2>
        {(runs.data?.results.length ?? 0) === 0 && (
          <p className="muted">{t("review.neverRun")}</p>
        )}
        {(runs.data?.results.length ?? 0) > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("run.status")}</th>
                <th>{t("run.outcome")}</th>
                <th>{t("run.date")}</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.results ?? []).map((candidate) => (
                <tr
                  key={candidate.uuid}
                  className={candidate.uuid === openRun ? "active" : ""}
                  onClick={() => setOpenRun(candidate.uuid)}
                >
                  <td>{t(`status.${candidate.status}`)}</td>
                  <td>{candidate.outcome ? <StatusPill status={candidate.outcome} /> : null}</td>
                  <td className="muted">{formatDate(candidate.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
      {reportFileMissing && (
        <p className="muted">
          <span data-testid="report-file-pending">{t("report.notGeneratedYet")}</span>{" "}
          <button
            type="button"
            data-testid="report-file-generate"
            onClick={() => void onGenerateReportFile()}
            disabled={generateReportFile.isPending}
          >
            {t("report.generate")}
          </button>
        </p>
      )}
      {reportGenerationError && (
        <p className="error">
          <span data-testid="report-file-failed">{t("report.generationFailed")}</span>{" "}
          <button
            type="button"
            data-testid="report-file-generate"
            onClick={() => void onGenerateReportFile()}
            disabled={generateReportFile.isPending}
          >
            {t("report.generate")}
          </button>
        </p>
      )}
      {currentReport && (
        <ReportView report={currentReport} rulePackSelection={run.data?.rule_pack_selection ?? []} />
      )}
    </main>
  );
}
