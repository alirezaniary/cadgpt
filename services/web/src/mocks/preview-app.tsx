/**
 * The real application, mounted at a chosen route.
 *
 * This is deliberately the same tree `src/main.tsx` builds -- `QueryClientProvider`,
 * `SessionProvider`, `RouterProvider` over the same `routeTree` -- with two differences,
 * both about isolation rather than behaviour: the history is in-memory so a story can
 * start three levels deep without touching the address bar, and both the client and the
 * router are created per mount so one story's cache and location cannot leak into the
 * next.
 *
 * Nothing here stands in for a page. `App` still decides between sign-in, the
 * first-workspace screen and the shell; the router still resolves the route; the session
 * still comes from `/auth/refresh/`. A story chooses a screen by choosing a route and a
 * set of MSW handlers, which is why these previews cannot drift from what the app does --
 * they *are* what the app does.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { useState } from "react";

import { routeTree } from "@/app/router";
import { SessionProvider } from "@/app/session";

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

  const [router] = useState(() =>
    createRouter({ routeTree, history: createMemoryHistory({ initialEntries: [route] }) }),
  );

  return (
    <QueryClientProvider client={client}>
      <SessionProvider>
        <RouterProvider router={router} />
      </SessionProvider>
    </QueryClientProvider>
  );
}
