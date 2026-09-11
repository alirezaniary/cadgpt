import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";

import { router } from "@/app/router";
import { SessionProvider } from "@/app/session";
import { useSession } from "@/app/session-context";
import "@/i18n";
import "@/styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A model check is not something a window focus should re-trigger, and a report
      // that has been produced does not change.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

/**
 * Holds the invariant the route guards in `router.tsx` are written against: the router is
 * never rendered while the session is unknown.
 *
 * Until `ready`, `/v1/auth/refresh/` is still deciding whether the cookie in this browser
 * names a signed-in user, and there is no answer a guard could be given that isn't a
 * guess -- "signed out" would bounce a real session to `/login` on every hard refresh.
 * Withholding `RouterProvider` for that window means no `beforeLoad` ever has to model it,
 * at the cost of the same blank frame the app already showed there.
 *
 * After that, `context` is a prop rather than a `router.update` call in an effect, because
 * `RouterProvider` applies it during render -- ahead of the initial `load()`, which the
 * router only issues from a layout effect. `router.update` alone does not re-run a match
 * that is already committed, so `invalidate` is what re-runs `beforeLoad` when the user
 * changes later, and is therefore what moves the URL on sign-in and sign-out.
 */
function AuthedRouter() {
  const { user, ready } = useSession();

  // `ready` gates this, not just the render below. `router` owns the browser history from
  // the moment it is constructed, so `invalidate()` makes it load -- and act on a guard
  // redirect -- whether or not anything is rendering it. Firing while the session is still
  // unresolved therefore evaluated `beforeLoad` against the placeholder context and pushed
  // the address bar to `/login` behind the blank frame, which is the exact flash not
  // mounting `RouterProvider` was supposed to prevent. Caught by `e2e/routing.spec.ts`
  // against the real container; no unit or story test saw it.
  useEffect(() => {
    if (!ready) return;
    void router.invalidate();
  }, [user, ready]);

  if (!ready) return <main className="centered" />;
  return <RouterProvider router={router} context={{ auth: { user } }} />;
}

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <AuthedRouter />
      </SessionProvider>
    </QueryClientProvider>
  </StrictMode>,
);
