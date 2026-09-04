/**
 * The route tree, in code (no file-based routing plugin is installed, so this is written
 * out by hand). `App` is the root route's own component -- it keeps deciding what to
 * render for "not signed in" / "no workspace yet" (T-0067) exactly as it always has, and
 * for a signed-in user with a workspace it renders the topbar/account-menu shell around
 * an `<Outlet />` where `ReviewsPage`'s whole tree used to sit directly.
 *
 * Static segments always match before a sibling `$param` segment at the same depth, which
 * is what lets `/projects/new` and `/projects/$projectUuid/reviews/new` sit next to their
 * dynamic siblings without an explicit priority list.
 */

import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";

import { App } from "@/app/App";
import { ProjectAddPage } from "@/features/project/ProjectAddPage";
import { ProjectDetailPage } from "@/features/project/ProjectDetailPage";
import { ProjectsListPage } from "@/features/project/ProjectsListPage";
import { ReviewAddPage } from "@/features/review/ReviewAddPage";
import { ReviewDetailPage } from "@/features/review/ReviewDetailPage";

const rootRoute = createRootRoute({ component: App });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/projects" });
  },
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects",
  component: ProjectsListPage,
});

const projectNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/new",
  component: ProjectAddPage,
});

const projectDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectUuid",
  component: ProjectDetailPage,
});

const reviewNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectUuid/reviews/new",
  component: ReviewAddPage,
});

const reviewDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$projectUuid/reviews/$reviewUuid",
  component: ReviewDetailPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  projectsRoute,
  projectNewRoute,
  projectDetailRoute,
  reviewNewRoute,
  reviewDetailRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
