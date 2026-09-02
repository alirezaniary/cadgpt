/**
 * The working screen: register a rule set, upload a model, run a check, read the report.
 *
 * Everything that takes time is asynchronous by construction. Starting a check returns a
 * queued run immediately and the page polls it; nothing here waits on a request that
 * could take minutes.
 */

import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { isTerminal } from "@/api/types";
import {
  useCheckRun,
  useCreateReview,
  useCreateRuleSet,
  useReviews,
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
  const createRuleSet = useCreateRuleSet(slug);
  const createReview = useCreateReview(slug);
  const startCheck = useStartCheck(slug);

  const [openReview, setOpenReview] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCheckRun(openReview ?? "", openRun);

  function report(caught: unknown) {
    setError(caught instanceof ApiError ? caught.message : t("error.generic"));
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

  async function onCheck(reviewUuid: string) {
    setError(null);
    try {
      const queued = await startCheck.mutateAsync(reviewUuid);
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
          <select name="rule_set" required defaultValue="">
            <option value="" disabled>
              {t("review.ruleSet")}
            </option>
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
                    <button
                      type="button"
                      onClick={() => void onCheck(review.uuid)}
                      disabled={busy || startCheck.isPending}
                    >
                      {busy ? t("review.checking") : t("review.check")}
                    </button>
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

      {run.data?.report && <ReportView report={run.data.report} />}
    </main>
  );
}
