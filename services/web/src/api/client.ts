/**
 * The one place the browser talks to the server.
 *
 * Two properties this file exists to hold.
 *
 * The access token lives in memory and never in `localStorage`. A refresh token sits in
 * an httpOnly cookie the browser sends only to the refresh endpoint, so a cross-site
 * scripting flaw here cannot lift a credential that outlives the page.
 *
 * A 401 triggers exactly one refresh, shared by every request that raced into it. Without
 * the shared promise, ten queries failing at once would fire ten refreshes and rotate the
 * token out from under nine of them.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fieldErrors?: Record<string, string[]>,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ProblemDetail {
  status?: number;
  code?: string;
  detail?: string;
  errors?: Record<string, string[]>;
  request_id?: string;
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

let accessToken: string | null = null;
let tenantSlug: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setTenant(slug: string | null): void {
  tenantSlug = slug;
}

export function getTenant(): string | null {
  return tenantSlug;
}

function headers(body: unknown): Headers {
  const result = new Headers();
  if (accessToken) result.set("Authorization", `Bearer ${accessToken}`);
  // Omitted rather than sent empty: an empty header would name a tenant that is not
  // there, and the server refuses an unresolvable name.
  if (tenantSlug) result.set("X-Tenant", tenantSlug);
  if (body !== undefined && !(body instanceof FormData)) {
    result.set("Content-Type", "application/json");
  }
  return result;
}

async function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${BASE_URL}/v1/auth/refresh/`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        accessToken = null;
        return false;
      }
      const data = (await response.json()) as { access: string };
      accessToken = data.access;
      return true;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function toError(response: Response): Promise<ApiError> {
  let problem: ProblemDetail = {};
  try {
    problem = (await response.json()) as ProblemDetail;
  } catch {
    // A proxy timeout or a 502 is not JSON. The status still carries the meaning.
  }
  return new ApiError(
    response.status,
    problem.code ?? "error",
    problem.detail ?? response.statusText,
    problem.errors,
    problem.request_id,
  );
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  retryOnUnauthorized?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, retryOnUnauthorized = true } = options;

  const init: RequestInit = {
    method,
    credentials: "include",
    headers: headers(body),
  };
  if (signal) init.signal = signal;
  if (body !== undefined) {
    init.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  const response = await fetch(`${BASE_URL}${path}`, init);

  if (response.status === 401 && retryOnUnauthorized) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...options, retryOnUnauthorized: false });
    }
  }

  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Save an authenticated file to disk -- a generated report, not a JSON body.
 *
 * `path` is the *full* server-rooted path a run's `report_file_url` already carries
 * (`/api/v1/reviews/…`), not a `BASE_URL`-relative one like `request()` takes: the server
 * builds that URL from its own route, and re-deriving `BASE_URL + path` here would double
 * the "/api" prefix if the two ever disagree. A plain `<a href>` cannot carry the bearer
 * token this API takes instead of a cookie, so this fetches the bytes itself and hands the
 * browser a local blob to save.
 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(path, { credentials: "include", headers: headers(undefined) });

  if (response.status === 401 && (await refreshAccessToken())) {
    return downloadFile(path, filename);
  }
  if (!response.ok) throw await toError(response);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, signal ? { signal } : {}),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  download: downloadFile,
};
