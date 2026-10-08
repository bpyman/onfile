// Same-origin proxy to the Python API (ADR 0006). The browser never learns
// API_ORIGIN or API_PROXY_TOKEN, so there is no CORS surface, the backend can
// move freely, and the hosted API answers only calls that came through here.

import {
  TOO_LARGE,
  clientResponseHeaders,
  hasBody,
  passesThrough,
  readLimitedBody,
  refusal,
  upstreamRequestHeaders,
} from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API_ORIGIN = (process.env.API_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/$/, "");
// How long the API may take to start answering; a turn's stream then runs on.
// Render's free tier takes about a minute to wake, so this leaves it room.
const UPSTREAM_HEADERS_TIMEOUT_MS = 100_000;
const UNREACHABLE = "The analysis service is unreachable. Please try again shortly.";
const UPSTREAM_FAILED = "The analysis service had a problem. Please try again.";

async function forward(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const refused = refusal(request, path);
  if (refused) return Response.json({ detail: refused.detail }, { status: refused.status });
  const search = new URL(request.url).search;
  const target = `${API_ORIGIN}/api/${path.map(encodeURIComponent).join("/")}${search}`;
  const body = hasBody(request) ? await readLimitedBody(request) : undefined;
  if (body === null) return Response.json({ detail: TOO_LARGE }, { status: 413 });
  // Aborts if the visitor leaves, or if the API has not begun answering in time.
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  request.signal.addEventListener("abort", onAbort);
  const timer = setTimeout(onAbort, UPSTREAM_HEADERS_TIMEOUT_MS);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      // Only Vercel overwrites the visitor's address headers; elsewhere they are the visitor's own.
      headers: upstreamRequestHeaders(request, process.env.API_PROXY_TOKEN, {
        onPlatform: Boolean(process.env.VERCEL),
      }),
      body,
      cache: "no-store",
      // A redirect would carry the proxy token and the body to wherever it points.
      redirect: "manual",
      signal: controller.signal,
    });
  } catch {
    return Response.json({ detail: UNREACHABLE }, { status: 502 });
  } finally {
    clearTimeout(timer);
  }
  if (!passesThrough(upstream, request.method)) {
    await upstream.body?.cancel();
    return Response.json(
      { detail: UPSTREAM_FAILED },
      { status: upstream.status >= 400 ? upstream.status : 502, headers: { "cache-control": "private, no-store" } },
    );
  }
  return new Response(request.method === "HEAD" ? null : upstream.body, {
    status: upstream.status,
    headers: clientResponseHeaders(upstream.headers),
  });
}

export { forward as GET, forward as HEAD, forward as POST, forward as DELETE };
