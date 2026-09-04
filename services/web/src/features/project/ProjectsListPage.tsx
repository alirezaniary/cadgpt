/**
 * The changelist's outermost level: every project the tenant owns (T-0074). Django
 * admin's shape, not the old single-page dashboard -- a list, an add form reached through
 * its own button, and a detail view reached by clicking a row.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useProjects } from "@/api/queries";
import { useSession } from "@/app/session-context";
import { formatDate } from "@/lib/dates";

export function ProjectsListPage() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const navigate = useNavigate();

  const projects = useProjects(slug);
  const rows = projects.data?.results ?? [];

  return (
    <main className="page">
      <section className="card">
        <div className="page__head">
          <h1>{t("project.title")}</h1>
          <Link to="/projects/new" className="button-link">
            {t("project.new")}
          </Link>
        </div>

        {projects.isError && <p className="error">{t("error.generic")}</p>}

        {rows.length === 0 && !projects.isLoading && (
          <p className="muted">{t("project.empty")}</p>
        )}

        {rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("project.name")}</th>
                <th>{t("project.reviewCount")}</th>
                <th>{t("project.createdAt")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((project) => (
                <tr
                  key={project.uuid}
                  onClick={() => void navigate({ to: "/projects/$projectUuid", params: { projectUuid: project.uuid } })}
                >
                  <td>
                    <Link
                      to="/projects/$projectUuid"
                      params={{ projectUuid: project.uuid }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td>{project.review_count}</td>
                  <td className="muted">{formatDate(project.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
