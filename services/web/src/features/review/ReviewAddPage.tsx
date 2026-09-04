/**
 * A review's add form: name and model file only. No rule-set picker here -- per
 * `docs/decisions.md`'s 2026-09-04 entry, rule-set upload is removed from the UI
 * entirely, so every review created here has no `rule_set` of its own and always takes
 * the catalogue path, chosen per check request on the review's own detail page.
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useCreateReview } from "@/api/queries";
import { useSession } from "@/app/session-context";
import { formatBytes, MAX_MODEL_UPLOAD_BYTES } from "@/lib/limits";

export function ReviewAddPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const navigate = useNavigate();
  const { projectUuid } = useParams({ from: "/projects/$projectUuid/reviews/new" });

  const createReview = useCreateReview(slug);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File)) return;
    try {
      const review = await createReview.mutateAsync({
        file,
        name: String(form.get("name") ?? ""),
        project: projectUuid,
      });
      await navigate({
        to: "/projects/$projectUuid/reviews/$reviewUuid",
        params: { projectUuid, reviewUuid: review.uuid },
      });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("error.generic"));
    }
  }

  return (
    <main className="page">
      <form className="card" onSubmit={onSubmit}>
        <h1>{t("review.new")}</h1>

        <div className="field">
          <label htmlFor="review-name">{t("review.name")}</label>
          <input id="review-name" name="name" required />
        </div>

        <div className="field">
          <label htmlFor="review-file">{t("review.model")}</label>
          <input
            id="review-file"
            name="file"
            type="file"
            accept=".ifc,.ifcxml,.ifczip"
            required
          />
          <span className="muted" data-testid="model-size-limit">
            {t("review.modelSizeLimit", { limit: formatBytes(MAX_MODEL_UPLOAD_BYTES) })}
          </span>
        </div>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={createReview.isPending}>
          {t("review.create")}
        </button>
      </form>
    </main>
  );
}
