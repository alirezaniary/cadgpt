/**
 * The way out: a Django-admin-style trail -- Projects > {project} > {review} -- so a
 * user three route levels into a review's detail page (T-0074's
 * workspace -> projects -> reviews shape) has a one-click path back to any ancestor,
 * not just the browser's own back button. Hidden on `/projects` itself, since the
 * changelist there already carries the same "Projects" heading.
 */

import { type ReactNode } from "react";
import { Link, useParams, useRouterState } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useProject, useReview } from "@/api/queries";
import { useSession } from "@/app/session-context";

function Separator() {
  return (
    <span className="breadcrumbs__sep" aria-hidden="true">
      /
    </span>
  );
}

export function Breadcrumbs() {
  const { t } = useTranslation();
  const { tenant } = useSession();
  const slug = tenant?.slug ?? null;
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const { projectUuid, reviewUuid } = useParams({ strict: false });

  const project = useProject(slug, projectUuid ?? "");
  const review = useReview(slug, reviewUuid ?? "");

  if (pathname === "/projects") return null;

  // `activeOptions={{ exact: true }}` stops the router's own active-link handling from
  // stamping `aria-current="page"` on an ancestor crumb just because the current path
  // starts with it -- only the trail's own trailing `<span>` may claim that.
  const projectsCrumb = (
    <Link to="/projects" activeOptions={{ exact: true }}>
      {t("project.title")}
    </Link>
  );

  let items: ReactNode[];

  if (pathname === "/projects/new") {
    items = [projectsCrumb, <span aria-current="page">{t("project.new")}</span>];
  } else if (!projectUuid) {
    // Every other route carries a projectUuid -- nothing to render for a route the
    // tree doesn't have.
    return null;
  } else if (pathname === `/projects/${projectUuid}`) {
    items = [projectsCrumb, <span aria-current="page">{project.data?.name ?? "…"}</span>];
  } else {
    const projectCrumb = (
      <Link
        to="/projects/$projectUuid"
        params={{ projectUuid }}
        activeOptions={{ exact: true }}
      >
        {project.data?.name ?? "…"}
      </Link>
    );
    items = pathname.endsWith("/reviews/new")
      ? [projectsCrumb, projectCrumb, <span aria-current="page">{t("review.new")}</span>]
      : [projectsCrumb, projectCrumb, <span aria-current="page">{review.data?.name ?? "…"}</span>];
  }

  return (
    <nav className="breadcrumbs" aria-label={t("nav.breadcrumb")}>
      {items.map((item, index) => (
        <span className="breadcrumbs__item" key={index}>
          {item}
          {index < items.length - 1 && <Separator />}
        </span>
      ))}
    </nav>
  );
}
