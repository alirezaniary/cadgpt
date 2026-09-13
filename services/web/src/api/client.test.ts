/**
 * T-0053. `downloadFile` is the one place the report-download button actually runs --
 * before this task nothing under `services/web/src` exercised it, and two defects sat in
 * it undetected: the saved filename was hardcoded rather than read from the server's
 * `Content-Disposition`, and the object URL was revoked synchronously in the same tick as
 * `link.click()`, which some browsers race (they only start reading a `blob:` URL on a
 * later task, and a URL freed before then fails the download silently).
 *
 * Run via the "unit" Vitest project (`vitest.config.ts`, `environment: "node"`) -- a pure
 * function over `fetch` and the DOM APIs `downloadFile` calls, none of which need a real
 * browser. `document` and `URL.createObjectURL`/`revokeObjectURL` do not exist in Node, so
 * both are stubbed here with exactly the surface `downloadFile` touches -- narrower than
 * pulling in a DOM implementation (jsdom/happy-dom) neither this file nor the rest of the
 * "unit" project otherwise needs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadFile } from "@/api/client";

interface FakeLink {
  href: string;
  download: string;
  click: () => void;
  remove: () => void;
}

function stubDom(events: string[]): { link: FakeLink; body: { appendChild: (n: unknown) => void } } {
  const link: FakeLink = {
    href: "",
    download: "",
    click: vi.fn(() => events.push("click")),
    remove: vi.fn(),
  };
  const body = { appendChild: vi.fn() };
  vi.stubGlobal("document", {
    createElement: vi.fn(() => link),
    body,
  });
  return { link, body };
}

function stubObjectUrl(events: string[]): { revokeObjectURL: ReturnType<typeof vi.fn> } {
  const revokeObjectURL = vi.fn(() => events.push("revoke"));
  vi.stubGlobal("URL", {
    createObjectURL: vi.fn(() => "blob:mock-url"),
    revokeObjectURL,
  });
  return { revokeObjectURL };
}

function fakeResponse(options: {
  headers?: Record<string, string>;
  status?: number;
  ok?: boolean;
}): Response {
  const headerMap = new Map(
    Object.entries(options.headers ?? {}).map(([k, v]) => [k.toLowerCase(), v]),
  );
  return {
    status: options.status ?? 200,
    ok: options.ok ?? true,
    headers: { get: (name: string) => headerMap.get(name.toLowerCase()) ?? null },
    blob: async () => new Blob(["# report"], { type: "text/markdown" }),
  } as unknown as Response;
}

describe("downloadFile", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("saves under the server's Content-Disposition filename, not the caller's fallback", async () => {
    const events: string[] = [];
    const { link } = stubDom(events);
    stubObjectUrl(events);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        fakeResponse({
          headers: { "Content-Disposition": 'attachment; filename="report-6a1e.md"' },
        }),
      ),
    );

    await downloadFile("/api/v1/reviews/r/runs/u/report-file/", "report.md");

    // Before the fix, this call site always saved "report.md" -- the fallback -- because
    // the caller's hardcoded literal, not the server's own name for this run, is what
    // reached `link.download`. Two different runs' reports would collide in the user's
    // downloads folder and neither could be traced back to the run that produced it.
    expect(link.download).toBe("report-6a1e.md");
  });

  it("falls back to the caller's filename when the response carries no Content-Disposition", async () => {
    const events: string[] = [];
    const { link } = stubDom(events);
    stubObjectUrl(events);
    vi.stubGlobal("fetch", vi.fn(async () => fakeResponse({})));

    await downloadFile("/api/v1/reviews/r/runs/u/report-file/", "report.md");

    expect(link.download).toBe("report.md");
  });

  it("decodes an RFC 6266 extended filename* in preference to the plain parameter", async () => {
    const events: string[] = [];
    const { link } = stubDom(events);
    stubObjectUrl(events);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        fakeResponse({
          headers: {
            "Content-Disposition":
              "attachment; filename=\"report.md\"; filename*=UTF-8''report-6a1e.md",
          },
        }),
      ),
    );

    await downloadFile("/api/v1/reviews/r/runs/u/report-file/", "report.md");

    expect(link.download).toBe("report-6a1e.md");
  });

  it("does not revoke the object URL until after the click has had a chance to start the download", async () => {
    // This is a timing-dependent defect (T-0053): a browser that starts reading a
    // `blob:` URL asynchronously can lose the download if the URL is freed in the same
    // tick as `click()`. Real timing in a real browser would make this test flaky either
    // way -- it might pass "by luck" even against the broken code, if the harness
    // happens to schedule the download's read before the synchronous revoke runs. Fake
    // timers make the ordering deterministic and assert it directly instead: with the
    // bug, `revokeObjectURL` runs synchronously inside the same `await downloadFile(...)`
    // call, before any timer has fired, so it would already show as called at the point
    // marked below. With the fix, it is scheduled behind a macrotask and provably has not
    // run yet at that same point -- only after timers are advanced.
    const events: string[] = [];
    const { link } = stubDom(events);
    const { revokeObjectURL } = stubObjectUrl(events);
    vi.stubGlobal("fetch", vi.fn(async () => fakeResponse({})));

    await downloadFile("/api/v1/reviews/r/runs/u/report-file/", "report.md");

    // The click itself has already happened...
    expect(link.click).toHaveBeenCalledTimes(1);
    // ...but the revoke must not have run yet -- this is the assertion the pre-fix code
    // fails: it calls `URL.revokeObjectURL` synchronously in a `finally` right after
    // `click()`, so by this point it would already have been called once.
    expect(revokeObjectURL).not.toHaveBeenCalled();

    // Only once the event loop actually gets a turn does the revoke run.
    await vi.runAllTimersAsync();

    expect(revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(events).toEqual(["click", "revoke"]);
  });
});
