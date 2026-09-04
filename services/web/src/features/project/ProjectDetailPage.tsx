/**
 * Inside one project: its own name as a heading, and the reviews that live under it --
 * Django admin's detail-view shape, one level in from `ProjectsListPage`. Reviews come
 * from `useReviews(tenant, projectUuid)`, T-0073's `ReviewFilterSet` `project` filter.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useProject, useReviews } from "@/api/queries";
import { useSession } from "@/app/session-context";
import { StatusPill } from "@/components/StatusPill";
import { formatDate } from "@/lib/dates";

export function ProjectDetailPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const navigate = useNavigate();
  const { projectUuid } = useParams({ from: "/projects/$projectUuid" });

  const project = useProject(slug, projectUuid);
  const reviews = useReviews(slug, projectUuid);
  const rows = reviews.data?.results ?? [];

  return (
    <main className="page">
      <section className="card">
        <div className="page__head">
          <h1>{project.data?.name ?? "…"}</h1>
          <Link
            to="/projects/$projectUuid/reviews/new"
            params={{ projectUuid }}
            className="button-link"
          >
            {t("review.new")}
          </Link>
        </div>

        {(project.isError || reviews.isError) && <p className="error">{t("error.generic")}</p>}

        {rows.length === 0 && !reviews.isLoading && <p className="muted">{t("review.empty")}</p>}

        {rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("review.name")}</th>
                <th>{t("review.modelFile")}</th>
                <th>{t("review.statusColumn")}</th>
                <th>{t("review.outcomeColumn")}</th>
                <th>{t("review.latestRun")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((review) => {
                const latest = review.latest_run;
                return (
                  <tr
                    key={review.uuid}
                    onClick={() =>
                      void navigate({
                        to: "/projects/$projectUuid/reviews/$reviewUuid",
                        params: { projectUuid, reviewUuid: review.uuid },
                      })
                    }
                  >
                    <td>
                      <Link
                        to="/projects/$projectUuid/reviews/$reviewUuid"
                        params={{ projectUuid, reviewUuid: review.uuid }}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {review.name}
                      </Link>
                    </td>
                    <td className="ltr muted">{review.model_file.original_name}</td>
                    <td>{latest ? t(`status.${latest.status}`) : t("review.neverRun")}</td>
                    <td>{latest?.outcome ? <StatusPill status={latest.outcome} /> : null}</td>
                    <td className="muted">{latest ? formatDate(latest.created_at) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
