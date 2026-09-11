/**
 * The route tree, in code (no file-based routing plugin is installed, so this is written
 * out by hand).
 *
 * Auth lives in the tree, not in a component branching on session state. Two pathless
 * layout routes divide it: `guestRoute` holds `/login` and `/register` and turns an
 * already-signed-in visitor away; `appRoute` holds everything else, turns a signed-out
 * visitor away, and renders the topbar/breadcrumbs shell around whichever page matched.
 * Neither contributes a URL segment -- `/projects/$projectUuid` is registered, matched and
 * linked to at exactly that path -- so the address bar says what is on screen and nothing
 * else has to keep the two in agreement.
 *
 * The guards can be this blunt (no "is the session known yet?" branch) because of an
 * invariant enforced one level up: `AuthedRouter` in `main.tsx` -- and its counterpart in
 * `mocks/preview-app.tsx` -- does not mount `RouterProvider` at all until
 * `useSession().ready` is true. The router therefore never runs a `beforeLoad` against an
 * unresolved session, which is what stops a hard refresh from bouncing a genuinely
 * signed-in user to `/login` for the instant before the refresh-cookie check in
 * `session.tsx` settles. `context.auth` is passed down as a `RouterProvider` prop (applied
 * during render, before the first load) and re-read by re-running `beforeLoad` on
 * `router.invalidate()` whenever the user changes.
 *
 * That is also why neither sign-in nor sign-out navigates by hand: clearing the session is
 * what moves the URL, because `requireSignedIn` cannot hold `/projects` open for a user
 * who is no longer there. Navigating explicitly alongside it would race the state flush
 * and could land on `/login` while `context.auth.user` still held the outgoing user, whose
 * own guard would bounce it straight back.
 *
 * Static segments always match before a sibling `$param` segment at the same depth, which
 * is what lets `/projects/new` and `/projects/$projectUuid/reviews/new` sit next to their
 * dynamic siblings without an explicit priority list.
 *
 * One trap worth naming, because it reads as a bug in the pathless layout and is not. A
 * route has two identifiers and they are not the same string: its *path* (`fullPath`),
 * which is the URL and which a layout route contributes nothing to, and its *id*, which is
 * the position in the tree and which every ancestor does contribute to. So `Link to` and
 * `navigate({ to })` take `"/projects/$projectUuid"`, while `useParams({ from })` -- which
 * addresses a route, not a URL -- takes `"/_app/projects/$projectUuid"`. The layout ids
 * here are spelled with TanStack's own leading underscore so that prefix is recognisable
 * on sight as a tree position rather than a segment anyone can navigate to.
 */

import { createRootRouteWithContext, createRoute, createRouter, redirect } from "@tanstack/react-router";

import type { User } from "@/api/types";
import { ProtectedShell } from "@/app/ProtectedShell";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { SignInPage } from "@/features/auth/SignInPage";
import { ProjectAddPage } from "@/features/project/ProjectAddPage";
import { ProjectDetailPage } from "@/features/project/ProjectDetailPage";
import { ProjectsListPage } from "@/features/project/ProjectsListPage";
import { ReviewAddPage } from "@/features/review/ReviewAddPage";
import { ReviewDetailPage } from "@/features/review/ReviewDetailPage";

export interface RouterContext {
  auth: { user: User | null };
}

/** `createRouter` requires a context up front, but no `beforeLoad` ever observes this
 * value: both entry points pass the resolved session as a `RouterProvider` prop, which
 * `router.update` merges in during render -- before the first `load()`, which the
 * Transitioner only issues from a layout effect. */
export const unresolvedContext: RouterContext = { auth: { user: null } };

const rootRoute = createRootRouteWithContext<RouterContext>()();

/** Returning the narrowed user is what lets `ProtectedShell` take a `User` rather than a
 * `User | null` it would have to re-check: past the `throw`, the type says what the guard
 * just established. */
function requireSignedIn({ context }: { context: RouterContext }) {
  if (!context.auth.user) throw redirect({ to: "/login", replace: true });
  return { user: context.auth.user };
}

function requireSignedOut({ context }: { context: RouterContext }) {
  if (context.auth.user) throw redirect({ to: "/projects", replace: true });
}

/** Every guard redirect replaces rather than pushes. A pushed entry would be one the back
 * button returns to only to be redirected out of again, which reads as a stuck button. */
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: ({ context }) => {
    throw redirect({ to: context.auth.user ? "/projects" : "/login", replace: true });
  },
});

const guestRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "_guest",
  beforeLoad: requireSignedOut,
});

const loginRoute = createRoute({
  getParentRoute: () => guestRoute,
  path: "/login",
  component: SignInPage,
});

const registerRoute = createRoute({
  getParentRoute: () => guestRoute,
  path: "/register",
  component: RegisterPage,
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "_app",
  beforeLoad: requireSignedIn,
  component: ProtectedShell,
});

const projectsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects",
  component: ProjectsListPage,
});

const projectNewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/new",
  component: ProjectAddPage,
});

const projectDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectUuid",
  component: ProjectDetailPage,
});

const reviewNewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectUuid/reviews/new",
  component: ReviewAddPage,
});

const reviewDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/projects/$projectUuid/reviews/$reviewUuid",
  component: ReviewDetailPage,
});

/** Exported so the preview workbench (`mocks/preview-app.tsx`) can build its own router
 * over the *same* tree with a memory history, one fresh instance per story. Sharing the
 * singleton below instead would carry one story's location and cache into the next. */
export const routeTree = rootRoute.addChildren([
  indexRoute,
  guestRoute.addChildren([loginRoute, registerRoute]),
  appRoute.addChildren([
    projectsRoute,
    projectNewRoute,
    projectDetailRoute,
    reviewNewRoute,
    reviewDetailRoute,
  ]),
]);

export const router = createRouter({ routeTree, context: unresolvedContext });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
