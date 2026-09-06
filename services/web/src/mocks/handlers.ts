/**
 * The workbench's mock seam.
 *
 * It sits at the network, not inside a component: MSW intercepts `fetch`, so
 * `src/api/client.ts` runs completely unmodified -- the same bearer-token header, the same
 * 401-triggered refresh, the same `ProblemDetail` parsing, the same TanStack Query cache
 * and polling rules. Nothing in `src/` knows a story is rendering it. That is the whole
 * point: a preview that took fixture props instead would prove the components render, but
 * not that the app's real data path does.
 *
 * `scenario()` is backed by mutable arrays rather than fixed responses, so a POST is
 * visible to the GET that follows it. That is what makes the workbench walkable -- create
 * a project and it appears in the changelist, start a check and its run advances through
 * pending -> running -> succeeded on a real clock -- rather than a gallery of frozen
 * screens.
 */

import { HttpResponse, delay, http, type AnyHandler } from "msw";

import type {
  CheckRunDetail,
  CheckRunSummary,
  Media,
  Page,
  Project,
  Report,
  Review,
  Tenant,
  User,
} from "@/api/types";
import * as fx from "@/mocks/fixtures";

const API = "/api/v1";

function paged<T>(results: T[]): Page<T> {
  return { count: results.length, page: 1, pages: 1, size: 20, next: null, previous: null, results };
}

interface Problem {
  status: number;
  code: string;
  detail: string;
  errors?: Record<string, string[]>;
}

/** A `ProblemDetail` body in the exact shape `toError()` in `src/api/client.ts` parses. */
function problem(status: number, code: string, detail: string) {
  const body: Problem = { status, code, detail };
  return HttpResponse.json({ ...body, request_id: "req_wb_000000" }, { status });
}

// --- Session ---------------------------------------------------------------------------

interface SessionOptions {
  /** Tenants the signed-in user belongs to. Empty renders `CreateWorkspacePage`. */
  tenants?: Tenant[];
  /** When false, the refresh cookie fails and the app renders `SignInPage`. */
  authenticated?: boolean;
}

/**
 * `/auth/refresh/` is the hinge. `SessionProvider` calls it on mount and its outcome is
 * what decides between the signed-out and signed-in halves of `App` -- so a story picks a
 * screen by choosing what this returns, never by rendering a page component directly.
 */
export function session({ tenants = [fx.tenant], authenticated = true }: SessionOptions = {}): AnyHandler[] {
  const pair = { access: "workbench-access-token", expires_in: 900, user: fx.user };

  return [
    http.post(`${API}/auth/refresh/`, () =>
      authenticated ? HttpResponse.json(pair) : problem(401, "not_authenticated", "No session."),
    ),
    http.post(`${API}/auth/login/`, async ({ request }) => {
      const body = (await request.json()) as { email?: string; password?: string };
      if (!body.password || body.password.length < 4) {
        return problem(400, "invalid_credentials", "ایمیل یا گذرواژه نادرست است.");
      }
      return HttpResponse.json({ ...pair, user: { ...fx.user, email: body.email ?? fx.user.email } });
    }),
    http.post(`${API}/auth/register/`, async ({ request }) => {
      const body = (await request.json()) as { email?: string };
      const created: User = { ...fx.user, email: body.email ?? fx.user.email };
      return HttpResponse.json(created, { status: 201 });
    }),
    http.post(`${API}/auth/logout/`, () => new HttpResponse(null, { status: 204 })),
    http.get(`${API}/me/`, () => HttpResponse.json(fx.user)),
    http.get(`${API}/tenants/`, () => HttpResponse.json(paged(tenants))),
    http.post(`${API}/tenants/`, async ({ request }) => {
      const body = (await request.json()) as { name?: string; slug?: string };
      const created: Tenant = {
        ...fx.tenant,
        uuid: crypto.randomUUID(),
        name: body.name ?? fx.tenant.name,
        slug: body.slug ?? fx.tenant.slug,
      };
      return HttpResponse.json(created, { status: 201 });
    }),
  ];
}

// --- The tenant's data -------------------------------------------------------------------

interface ScenarioOptions {
  projects?: Project[];
  /** Reviews, keyed by the project uuid they belong to. */
  reviews?: Record<string, Review[]>;
  /** Runs, keyed by review uuid, newest first -- the order `CheckRunViewSet.list` returns. */
  runs?: Record<string, CheckRunSummary[]>;
  /** The report a succeeded run carries. */
  report?: Report;
}

/**
 * A tenant's whole data set, mutable for the length of one story. Every write endpoint the
 * UI can reach is implemented against the same arrays the reads come from, so the flows
 * that span two screens -- add a project and land on its detail page, upload a model and
 * land on the new review -- are walkable rather than described.
 */
export function scenario(options: ScenarioOptions = {}): AnyHandler[] {
  const projects = [...(options.projects ?? fx.projects)];
  const reviews: Record<string, Review[]> = {};
  for (const [key, value] of Object.entries(options.reviews ?? { [fx.project.uuid]: fx.reviews })) {
    reviews[key] = [...value];
  }
  const runs: Record<string, CheckRunSummary[]> = {};
  for (const [key, value] of Object.entries(
    options.runs ?? {
      [fx.checkedReview.uuid]: [fx.succeededRun, fx.earlierRun],
      [fx.runningReview.uuid]: [fx.runningRun],
      [fx.failedReview.uuid]: [fx.failedRun],
    },
  )) {
    runs[key] = [...value];
  }
  const report = options.report ?? fx.report;

  /** A check started from inside the workbench: real elapsed time decides its status, so
   * the "Checking…" button, the 1.5s run poll and the 2s list poll are all exercised the
   * way they are against a live worker, not simulated with a fixed response. */
  const started = new Map<string, number>();

  function advance(uuid: string): CheckRunSummary | null {
    const at = started.get(uuid);
    if (at === undefined) return null;
    const elapsed = Date.now() - at;
    if (elapsed < 2_000) return { ...fx.succeededRun, uuid, status: "pending", outcome: "", report_file_url: null };
    if (elapsed < 7_000) return { ...fx.succeededRun, uuid, status: "running", outcome: "", report_file_url: null };
    return { ...fx.succeededRun, uuid };
  }

  function findReview(uuid: string): Review | undefined {
    return Object.values(reviews)
      .flat()
      .find((candidate) => candidate.uuid === uuid);
  }

  function runFor(reviewUuid: string, runUuid: string): CheckRunSummary | undefined {
    return advance(runUuid) ?? (runs[reviewUuid] ?? []).find((candidate) => candidate.uuid === runUuid);
  }

  return [
    http.get(`${API}/rule-packs/`, () => HttpResponse.json(paged(fx.rulePacks))),

    http.get(`${API}/projects/`, () => HttpResponse.json(paged(projects))),
    http.get(`${API}/projects/:uuid/`, ({ params }) => {
      const found = projects.find((candidate) => candidate.uuid === params["uuid"]);
      return found ? HttpResponse.json(found) : problem(404, "not_found", "Project not found.");
    }),
    http.post(`${API}/projects/`, async ({ request }) => {
      const body = (await request.json()) as { name?: string };
      const created: Project = {
        uuid: crypto.randomUUID(),
        name: body.name ?? "",
        review_count: 0,
        created_at: new Date().toISOString(),
      };
      projects.unshift(created);
      reviews[created.uuid] = [];
      return HttpResponse.json(created, { status: 201 });
    }),

    http.get(`${API}/reviews/`, ({ request }) => {
      const projectUuid = new URL(request.url).searchParams.get("project") ?? "";
      const rows = (reviews[projectUuid] ?? []).map((review) => {
        const live = runs[review.uuid]?.[0];
        return live ? { ...review, latest_run: advance(live.uuid) ?? live } : review;
      });
      return HttpResponse.json(paged(rows));
    }),
    http.get(`${API}/reviews/:uuid/`, ({ params }) => {
      const found = findReview(String(params["uuid"]));
      return found ? HttpResponse.json(found) : problem(404, "not_found", "Review not found.");
    }),
    http.post(`${API}/reviews/`, async ({ request }) => {
      const body = (await request.json()) as { name?: string; project?: string };
      const projectUuid = body.project ?? "";
      const created: Review = {
        ...fx.neverRunReview,
        uuid: crypto.randomUUID(),
        name: body.name ?? "",
        latest_run: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      reviews[projectUuid] = [created, ...(reviews[projectUuid] ?? [])];
      runs[created.uuid] = [];
      const owner = projects.find((candidate) => candidate.uuid === projectUuid);
      if (owner) owner.review_count += 1;
      return HttpResponse.json(created, { status: 201 });
    }),

    http.post(`${API}/media/`, async ({ request }) => {
      const form = await request.formData();
      const file = form.get("file");
      const name = file instanceof File ? file.name : "model.ifc";
      const size = file instanceof File ? file.size : 0;
      const created: Media = { ...fx.checkedReview.model_file, uuid: crypto.randomUUID(), original_name: name, size_bytes: size };
      return HttpResponse.json(created, { status: 201 });
    }),

    http.get(`${API}/reviews/:uuid/runs/`, ({ params }) => {
      const reviewUuid = String(params["uuid"]);
      const rows = (runs[reviewUuid] ?? []).map((candidate) => advance(candidate.uuid) ?? candidate);
      return HttpResponse.json(paged(rows));
    }),
    http.get(`${API}/reviews/:uuid/runs/:runUuid/`, ({ params }) => {
      const found = runFor(String(params["uuid"]), String(params["runUuid"]));
      if (!found) return problem(404, "not_found", "Run not found.");
      const body: CheckRunDetail = fx.detail(found, found.status === "succeeded" ? report : null);
      return HttpResponse.json(body);
    }),
    http.post(`${API}/reviews/:uuid/check/`, ({ params }) => {
      const reviewUuid = String(params["uuid"]);
      const queued: CheckRunSummary = {
        ...fx.succeededRun,
        uuid: crypto.randomUUID(),
        status: "pending",
        outcome: "",
        report_file_url: null,
        created_at: new Date().toISOString(),
      };
      started.set(queued.uuid, Date.now());
      runs[reviewUuid] = [queued, ...(runs[reviewUuid] ?? [])];
      return HttpResponse.json(queued, { status: 202 });
    }),

    // GET serves the generated Markdown; POST is the T-0051 regeneration path. Same URL,
    // which is why both live here rather than one standing in for the other.
    http.get(`${API}/reviews/:uuid/runs/:runUuid/report-file/`, () =>
      HttpResponse.text(`# ${report.ids_title}\n\n${report.disclosure_title}\n\n${report.disclosure_text}\n`, {
        headers: { "Content-Type": "text/markdown; charset=utf-8" },
      }),
    ),
    http.post(`${API}/reviews/:uuid/runs/:runUuid/report-file/`, ({ params }) => {
      const reviewUuid = String(params["uuid"]);
      const runUuid = String(params["runUuid"]);
      const list = runs[reviewUuid] ?? [];
      const index = list.findIndex((candidate) => candidate.uuid === runUuid);
      const target = list[index];
      if (!target) return problem(404, "not_found", "Run not found.");
      const regenerated: CheckRunSummary = {
        ...target,
        report_file_url: `${API}/reviews/${reviewUuid}/runs/${runUuid}/report-file/`,
        report_generation_error: "",
      };
      list[index] = regenerated;
      return HttpResponse.json(regenerated);
    }),
  ];
}

// --- Overrides -------------------------------------------------------------------------
//
// Handlers passed to `worker.use()` are matched in order, so anything below is placed
// *first* in a story's list to shadow the scenario handler for the same route.

/** Never resolves, so the query stays `isLoading`. This is how a loading state is shown
 * honestly -- the component's own pending branch, not a screenshot of it. */
export function pending(path: string): AnyHandler {
  return http.get(path, async () => {
    await delay("infinite");
    return HttpResponse.json(null);
  });
}

export function failing(path: string, status = 500, detail = "سرویس در دسترس نیست."): AnyHandler {
  return http.get(path, () => problem(status, "server_error", detail));
}

export const paths = {
  projects: `${API}/projects/`,
  project: `${API}/projects/:uuid/`,
  reviews: `${API}/reviews/`,
  rulePacks: `${API}/rule-packs/`,
  runs: `${API}/reviews/:uuid/runs/`,
} as const;

/** The upload ceiling the server enforces (T-0063/T-0064), as the 413 the form must render. */
export function uploadTooLarge(): AnyHandler {
  return http.post(`${API}/media/`, () =>
    problem(413, "payload_too_large", "حجم فایل از حد مجاز بیشتر است."),
  );
}

/** A succeeded run whose report file was never generated (T-0051's recovery path). */
export function reportFileMissing(): AnyHandler {
  return http.get(`${API}/reviews/:uuid/runs/:runUuid/`, () =>
    HttpResponse.json(fx.detail({ ...fx.succeededRun, report_file_url: null }, fx.report)),
  );
}

/** A run whose report file failed permanently -- too large to store, the one reason a
 * retry cannot change (T-0051). */
export function reportFileFailed(): AnyHandler {
  return http.get(`${API}/reviews/:uuid/runs/:runUuid/`, () =>
    HttpResponse.json(
      fx.detail(
        {
          ...fx.succeededRun,
          report_file_url: null,
          report_generation_error: "گزارش برای ذخیره‌سازی بیش از حد بزرگ بود.",
        },
        fx.report,
      ),
    ),
  );
}
