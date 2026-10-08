// Header rules for the same-origin proxy (app/api/[...path]/route.ts, ADR 0006).
// Server-side only: the token comes from the route's environment and is never
// sent back to the browser.

import { isIP } from "node:net";

/** The shared-secret header the Python API checks when API_PROXY_TOKEN is set. */
export const PROXY_TOKEN_HEADER = "x-proxy-token";
/** The visitor's address, for the API's per-visitor limits (trusted only with the token). */
export const CLIENT_IP_HEADER = "x-client-ip";
/** A request body the API would take: one question of at most 2,000 characters. */
export const MAX_BODY_BYTES = 16 * 1024;
/** The 413 detail, for a declared length over the limit and for a chunked body that passes it. */
export const TOO_LARGE = "That request is too large for the analysis service.";

/** Response headers the browser needs; everything else from upstream is dropped. */
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "x-accel-buffering",
  // How long a busy API (429) asks callers to wait.
  "retry-after",
];

/**
 * Headers for the upstream API call. Built from an allowlist, so nothing the
 * browser sent (a forged proxy token included) reaches the API; the proxy token
 * is added only when one is configured.
 */
export function upstreamRequestHeaders(
  request: Request,
  token: string | undefined,
  { onPlatform = false }: { onPlatform?: boolean } = {},
): Headers {
  const headers = new Headers({ accept: request.headers.get("accept") ?? "application/json" });
  if (hasBody(request)) {
    headers.set("content-type", request.headers.get("content-type") ?? "application/json");
  }
  if (token) headers.set(PROXY_TOKEN_HEADER, token);
  const client = onPlatform ? clientAddress(request) : null;
  if (client) headers.set(CLIENT_IP_HEADER, client);
  return headers;
}

/**
 * The visitor's address as the hosting platform reports it: Vercel sets
 * x-real-ip and puts the client first in x-forwarded-for, overwriting what
 * the browser sent. Elsewhere (a local run, another host) the visitor writes
 * these headers, so the caller asks only on Vercel. Anything but an address
 * is dropped.
 */
export function clientAddress(request: Request): string | null {
  const real = request.headers.get("x-real-ip")?.trim();
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const address = real || forwarded;
  return address && isIP(address) ? address : null;
}

/** Why the proxy refuses a request before forwarding it, or null to forward it. */
export function refusal(request: Request, path: string[]): { status: number; detail: string } | null {
  // An encoded slash would split into two segments upstream; no API path needs one.
  if (path.map(decoded).some((segment) => segment === "." || segment === ".." || /[/\\]/.test(segment))) {
    return { status: 404, detail: "Not found." };
  }
  if (!hasBody(request)) return null;
  // Only this app's own pages may change threads: a cross-site form or fetch
  // would otherwise open threads and spend turns in a visitor's name.
  // Browsers mark every request with where it came from; a script or form on
  // another site cannot remove the mark. (Non-browser callers send none and
  // cannot be made to act for a visitor.)
  const site = request.headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin" && site !== "none") {
    return { status: 403, detail: "Requests must come from this site." };
  }
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > MAX_BODY_BYTES) {
    return { status: 413, detail: TOO_LARGE };
  }
  return null;
}

/** Whether the request carries a body: every method but the two reads. */
export function hasBody(request: Request): boolean {
  return request.method !== "GET" && request.method !== "HEAD";
}

function decoded(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/**
 * Whether an upstream answer may go to the browser as it is. Anything but JSON
 * or an event stream (an HTML error page, a traceback) is replaced, and so is
 * a redirect: the proxy never follows one, nor sends the browser to it.
 */
export function passesThrough(upstream: Response, method = "GET"): boolean {
  if (upstream.status >= 300 && upstream.status < 400) return false;
  // A HEAD answer has no body to check (an uptime probe of /api/health).
  if (method === "HEAD") return upstream.status < 500;
  const kind = (upstream.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  return kind === "application/json" || kind === "text/event-stream" || upstream.status === 204;
}

/**
 * Headers for the browser's response: only the allowlisted, stream-safe ones.
 * Threads are one visitor's, so nothing is cached on the way, whatever upstream
 * said; a stream also asks proxies not to compress it.
 */
export function clientResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.get(name);
    if (value) headers.set(name, value);
  }
  const stream = headers.get("content-type")?.startsWith("text/event-stream");
  headers.set("cache-control", stream ? "private, no-store, no-transform" : "private, no-store");
  return headers;
}

/**
 * The request body as text, or null once it passes ``limit`` bytes. A chunked
 * upload names no length, so it is read piece by piece and dropped as soon as
 * it is too large, rather than buffered whole first.
 */
export async function readLimitedBody(request: Request, limit = MAX_BODY_BYTES): Promise<string | null> {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}
