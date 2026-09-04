/**
 * Server state, owned by TanStack Query. There is no client-side store mirroring it.
 *
 * The polling rule is the interesting part: a run is polled while it is pending or
 * running, and `useCheckRun` keeps polling a little past that -- a succeeded run's
 * report file is a second, separately-dispatched piece of work (T-0032) that can still
 * be catching up. Polling stops for good once the run's own status *and* its report
 * file's fate (present, or permanently failed, T-0051) are both decided. A fixed
 * interval would keep asking about a result that cannot change, for as long as the tab
 * is open.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  CheckRunDetail,
  CheckRunSummary,
  Media,
  Page,
  Project,
  Review,
  RulePack,
  Tenant,
  User,
} from "@/api/types";
import { isTerminal } from "@/api/types";

export const keys = {
  me: ["me"] as const,
  tenants: ["tenants"] as const,
  rulePacks: (tenant: string | null) => ["rule-packs", tenant] as const,
  projects: (tenant: string | null) => ["projects", tenant] as const,
  project: (tenant: string | null, uuid: string) => ["project", tenant, uuid] as const,
  reviews: (tenant: string | null, projectUuid: string | null) =>
    ["reviews", tenant, projectUuid] as const,
  review: (uuid: string) => ["review", uuid] as const,
  runs: (review: string | null) => ["runs", review] as const,
  run: (review: string, run: string) => ["run", review, run] as const,
};

export function useMe(enabled: boolean): UseQueryResult<User> {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => api.get<User>("/v1/me/"),
    enabled,
    retry: false,
  });
}

export function useTenants(enabled: boolean): UseQueryResult<Page<Tenant>> {
  return useQuery({
    queryKey: keys.tenants,
    queryFn: () => api.get<Page<Tenant>>("/v1/tenants/"),
    enabled,
  });
}

/** A user's first (or next) workspace, via `TenantCreateSerializer`. The caller still has
 * to call `chooseTenant` itself with the response -- this hook only performs the write and
 * keeps the tenant list in step with it, the same division `useCreateReview` and its
 * siblings already use. */
export function useCreateTenant(): UseMutationResult<
  Tenant,
  Error,
  { name: string; slug: string; language: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post<Tenant>("/v1/tenants/", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.tenants }),
  });
}

/** The catalogue (T-0030), read-only and the same for every tenant. Every user needs it
 * the moment a review has no `rule_set` of its own -- fetched once and filtered on the
 * client rather than refetched per review's picker. */
export function useRulePacks(tenant: string | null): UseQueryResult<Page<RulePack>> {
  return useQuery({
    queryKey: keys.rulePacks(tenant),
    queryFn: () => api.get<Page<RulePack>>("/v1/rule-packs/"),
    enabled: Boolean(tenant),
  });
}

/** The changelist (T-0074): every project the tenant owns, with `review_count` -- one
 * query for the whole page (`ProjectViewSet.get_queryset`'s annotation). */
export function useProjects(tenant: string | null): UseQueryResult<Page<Project>> {
  return useQuery({
    queryKey: keys.projects(tenant),
    queryFn: () => api.get<Page<Project>>("/v1/projects/"),
    enabled: Boolean(tenant),
  });
}

/** A single project, for the detail page's own heading -- `GET /v1/projects/{uuid}/`
 * rather than reusing the list's cache, so a detail page opened directly (a reload, a
 * bookmark) does not depend on the changelist having been fetched first. */
export function useProject(
  tenant: string | null,
  uuid: string,
): UseQueryResult<Project> {
  return useQuery({
    queryKey: keys.project(tenant, uuid),
    queryFn: () => api.get<Project>(`/v1/projects/${uuid}/`),
    enabled: Boolean(tenant) && Boolean(uuid),
  });
}

export function useCreateProject(
  tenant: string | null,
): UseMutationResult<Project, Error, { name: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload) => api.post<Project>("/v1/projects/", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.projects(tenant) }),
  });
}

export function useReviews(
  tenant: string | null,
  projectUuid: string | null,
): UseQueryResult<Page<Review>> {
  return useQuery({
    queryKey: keys.reviews(tenant, projectUuid),
    queryFn: () => api.get<Page<Review>>(`/v1/reviews/?project=${projectUuid}`),
    enabled: Boolean(tenant) && Boolean(projectUuid),
    // A review's latest run changes while a check is in flight, so the list refreshes
    // itself only while at least one is unfinished.
    refetchInterval: (query) => {
      const page = query.state.data;
      if (!page) return false;
      const busy = page.results.some(
        (review) => review.latest_run && !isTerminal(review.latest_run.status),
      );
      return busy ? 2000 : false;
    },
  });
}

/** A review's past runs (T-0074's `ReviewDetailPage`, "a list of this review's past
 * runs") -- `CheckRunViewSet.list`, unchanged since before this task, just never called
 * from the frontend until now. Refetches itself while any run in the page is still
 * in flight, the same rule `useReviews` applies to a review's `latest_run`. */
export function useCheckRuns(reviewUuid: string | null): UseQueryResult<Page<CheckRunSummary>> {
  return useQuery({
    queryKey: keys.runs(reviewUuid),
    queryFn: () => api.get<Page<CheckRunSummary>>(`/v1/reviews/${reviewUuid}/runs/`),
    enabled: Boolean(reviewUuid),
    refetchInterval: (query) => {
      const page = query.state.data;
      if (!page) return false;
      const busy = page.results.some((run) => !isTerminal(run.status));
      return busy ? 2000 : false;
    },
  });
}

/** A single review, for `ReviewDetailPage`'s own heading (name, model filename) --
 * `GET /v1/reviews/{uuid}/`, the same `ReviewViewSet.retrieve` `useReviews`'s list
 * already reads through, just addressed one at a time so the detail page does not
 * depend on the project's review list having been fetched first. */
export function useReview(tenant: string | null, uuid: string): UseQueryResult<Review> {
  return useQuery({
    queryKey: keys.review(uuid),
    queryFn: () => api.get<Review>(`/v1/reviews/${uuid}/`),
    enabled: Boolean(tenant) && Boolean(uuid),
  });
}

export function useCheckRun(
  reviewUuid: string,
  runUuid: string | null,
): UseQueryResult<CheckRunDetail> {
  return useQuery({
    queryKey: keys.run(reviewUuid, runUuid ?? ""),
    queryFn: () => api.get<CheckRunDetail>(`/v1/reviews/${reviewUuid}/runs/${runUuid}/`),
    enabled: Boolean(runUuid),
    refetchInterval: (query) => {
      const run = query.state.data;
      if (!run || !isTerminal(run.status)) return 1500;
      // The check itself is done, but its report file is generated by a second,
      // separately-dispatched task (T-0032) that can still be catching up -- or, if its
      // dispatch was lost, never arrive without `useGenerateReportFile` being called
      // (T-0051). Keep polling while that is still undecided; stop the moment it is
      // either downloadable or has permanently failed, same as any other final answer.
      const reportPending =
        run.status === "succeeded" && !run.report_file_url && !run.report_generation_error;
      return reportPending ? 2000 : false;
    },
  });
}

/** Ask the server to (re)generate a succeeded run's report file (T-0051) -- reachable
 * when the automatic generation dispatched from the check's own success was lost, or
 * for a run that succeeded before that generator existed. Idempotent on the server: a
 * run that already has a file is untouched. */
export function useGenerateReportFile(
  tenant: string | null,
): UseMutationResult<CheckRunSummary, Error, { reviewUuid: string; runUuid: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewUuid, runUuid }) =>
      api.post<CheckRunSummary>(`/v1/reviews/${reviewUuid}/runs/${runUuid}/report-file/`),
    onSuccess: (_data, { reviewUuid, runUuid }) => {
      void client.invalidateQueries({ queryKey: keys.run(reviewUuid, runUuid) });
      // Prefix match: the caller does not know which project's list is showing this
      // review, so every `["reviews", tenant, *]` list is invalidated rather than one.
      void client.invalidateQueries({ queryKey: ["reviews", tenant] });
    },
  });
}

async function uploadMedia(file: File, kind: Media["kind"]): Promise<Media> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  return api.post<Media>("/v1/media/", form);
}

export function useCreateReview(
  tenant: string | null,
): UseMutationResult<Review, Error, { file: File; name: string; project: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, name, project }) => {
      const media = await uploadMedia(file, "ifc_model");
      return api.post<Review>("/v1/reviews/", {
        name,
        model_file: media.uuid,
        project,
        // No `rule_set` from here on (`docs/decisions.md`, 2026-09-04): every review
        // created through this form takes the catalogue path, selected per check
        // request instead (T-0031).
      });
    },
    onSuccess: (_data, { project }) =>
      client.invalidateQueries({ queryKey: keys.reviews(tenant, project) }),
  });
}

export function useStartCheck(
  tenant: string | null,
): UseMutationResult<
  CheckRunSummary,
  Error,
  { reviewUuid: string; rulePacks: string[] | undefined }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewUuid, rulePacks }) =>
      api.post<CheckRunSummary>(`/v1/reviews/${reviewUuid}/check/`, {
        rule_packs: rulePacks ?? [],
      }),
    onSuccess: (_data, { reviewUuid }) => {
      void client.invalidateQueries({ queryKey: ["reviews", tenant] });
      void client.invalidateQueries({ queryKey: keys.runs(reviewUuid) });
    },
  });
}
