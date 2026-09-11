/**
 * The real application, mounted at a chosen route.
 *
 * This is deliberately the same tree `src/main.tsx` builds -- `QueryClientProvider`,
 * `SessionProvider`, `RouterProvider` over the same `routeTree`, behind the same
 * wait-for-the-session gate -- with two differences, both about isolation rather than
 * behaviour: the history is in-memory so a story can start three levels deep without
 * touching the address bar, and both the client and the router are created per mount so
 * one story's cache and location cannot leak into the next.
 *
 * Nothing here stands in for a page. `router.tsx`'s guards still decide between the
 * sign-in screen and the shell, so a story that mocks `authenticated: false` and asks for
 * `/projects` is *redirected* to `/login` exactly as a real visitor would be -- these
 * previews cannot drift from what the app does, because they are what the app does.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { routeTree, unresolvedContext } from "@/app/router";
import { SessionProvider } from "@/app/session";
import { useSession } from "@/app/session-context";

function createPreviewRouter(route: string) {
  return createRouter({
    routeTree,
    context: unresolvedContext,
    history: createMemoryHistory({ initialEntries: [route] }),
  });
}

type PreviewRouter = ReturnType<typeof createPreviewRouter>;

/** Same job, and the same reasoning, as `main.tsx`'s own `AuthedRouter` -- over whichever
 * per-story router `AppAt` created instead of the production singleton. It has to sit
 * beside `RouterProvider` and inside `SessionProvider`, which is why it cannot live in
 * `router.tsx` with the guards it feeds. */
function AuthedRouterFor({ router }: { router: PreviewRouter }) {
  const { user, ready } = useSession();

  // Gated on `ready` for the same reason as `main.tsx` -- a router acts on a guard
  // redirect when invalidated whether or not it is being rendered, so invalidating before
  // the session resolves would move the (here in-memory) location using the placeholder
  // context.
  useEffect(() => {
    if (!ready) return;
    void router.invalidate();
  }, [router, user, ready]);

  if (!ready) return <main className="centered" />;
  return <RouterProvider router={router} context={{ auth: { user } }} />;
}

export function AppAt({ route }: { route: string }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // `main.tsx`'s own defaults, except `retry`: production retries once, which
            // in a workbench only means an error story sits blank for a second before
            // telling the truth about itself.
            refetchOnWindowFocus: false,
            staleTime: 30_000,
            retry: false,
          },
        },
      }),
  );

  const [router] = useState(() => createPreviewRouter(route));

  return (
    <QueryClientProvider client={client}>
      <SessionProvider>
        <AuthedRouterFor router={router} />
      </SessionProvider>
    </QueryClientProvider>
  );
}
