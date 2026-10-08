import { describe, expect, it } from "vitest";
import {
  CLIENT_IP_HEADER,
  MAX_BODY_BYTES,
  PROXY_TOKEN_HEADER,
  TOO_LARGE,
  clientAddress,
  clientResponseHeaders,
  hasBody,
  passesThrough,
  readLimitedBody,
  refusal,
  upstreamRequestHeaders,
} from "./proxy";

function browserRequest(init: RequestInit = {}): Request {
  return new Request("http://localhost:3000/api/threads", init);
}

describe("upstreamRequestHeaders", () => {
  it("adds the shared secret when API_PROXY_TOKEN is configured", () => {
    const headers = upstreamRequestHeaders(browserRequest(), "s3cret");
    expect(headers.get(PROXY_TOKEN_HEADER)).toBe("s3cret");
  });

  it.each([undefined, ""])("sends no secret header when the token is %j", (token) => {
    const headers = upstreamRequestHeaders(browserRequest(), token);
    expect(headers.has(PROXY_TOKEN_HEADER)).toBe(false);
  });

  it("never forwards a secret header the browser made up", () => {
    const forged = browserRequest({ headers: { [PROXY_TOKEN_HEADER]: "guess" } });
    expect(upstreamRequestHeaders(forged, undefined).has(PROXY_TOKEN_HEADER)).toBe(false);
    expect(upstreamRequestHeaders(forged, "s3cret").get(PROXY_TOKEN_HEADER)).toBe("s3cret");
  });

  it("passes accept, and content-type only for requests with a body", () => {
    const get = upstreamRequestHeaders(browserRequest({ headers: { accept: "text/event-stream" } }), "t");
    expect(get.get("accept")).toBe("text/event-stream");
    expect(get.has("content-type")).toBe(false);
    const post = upstreamRequestHeaders(
      browserRequest({ method: "POST", body: "{}", headers: { "content-type": "application/json" } }),
      "t",
    );
    expect(post.get("accept")).toBe("application/json");
    expect(post.get("content-type")).toBe("application/json");
    const bare = upstreamRequestHeaders(browserRequest({ method: "DELETE" }), "t");
    expect(bare.get("content-type")).toBe("application/json");
  });
});

describe("clientResponseHeaders", () => {
  it("keeps only the stream-safe headers, so an echoed secret never reaches the browser", () => {
    const upstream = new Headers({
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      [PROXY_TOKEN_HEADER]: "s3cret",
      "set-cookie": "a=b",
    });
    expect([...clientResponseHeaders(upstream).entries()]).toEqual([
      ["cache-control", "private, no-store, no-transform"],
      ["content-type", "text/event-stream"],
      ["x-accel-buffering", "no"],
    ]);
  });

  it("never passes on upstream caching: a thread is one visitor's", () => {
    const upstream = new Headers({ "content-type": "application/json", "cache-control": "public, s-maxage=600" });
    expect(clientResponseHeaders(upstream).get("cache-control")).toBe("private, no-store");
  });

  it("passes on how long a busy API asks the caller to wait", () => {
    const upstream = new Headers({ "content-type": "application/json", "retry-after": "5" });
    expect(clientResponseHeaders(upstream).get("retry-after")).toBe("5");
  });
});

describe("clientAddress", () => {
  it("prefers the platform's x-real-ip, then the first x-forwarded-for hop", () => {
    expect(clientAddress(browserRequest({ headers: { "x-real-ip": "203.0.113.9" } }))).toBe("203.0.113.9");
    expect(
      clientAddress(browserRequest({ headers: { "x-forwarded-for": "198.51.100.4, 10.0.0.1" } })),
    ).toBe("198.51.100.4");
    expect(clientAddress(browserRequest({ headers: { "x-real-ip": "2001:db8::1" } }))).toBe("2001:db8::1");
    expect(clientAddress(browserRequest())).toBeNull();
  });

  it("drops anything that is not an address", () => {
    expect(clientAddress(browserRequest({ headers: { "x-real-ip": "visitor-" + "x".repeat(80) } }))).toBeNull();
    expect(clientAddress(browserRequest({ headers: { "x-forwarded-for": "evil, 10.0.0.1" } }))).toBeNull();
  });

  it("is forwarded to the API as its own header, on the platform only", () => {
    const request = browserRequest({ headers: { "x-real-ip": "203.0.113.9" } });
    expect(upstreamRequestHeaders(request, "t", { onPlatform: true }).get(CLIENT_IP_HEADER)).toBe("203.0.113.9");
    // Off Vercel the visitor wrote that header: trusting it would let them pick their own limit bucket.
    expect(upstreamRequestHeaders(request, "t").has(CLIENT_IP_HEADER)).toBe(false);
  });
});

describe("refusal", () => {
  const post = (headers: Record<string, string>) =>
    browserRequest({ method: "POST", body: "{}", headers: { "content-type": "application/json", ...headers } });

  it("refuses dot segments", () => {
    expect(refusal(browserRequest(), ["threads", ".."])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "."])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "%2e%2e"])?.status).toBe(404);
  });

  it("refuses a segment holding a slash once decoded", () => {
    expect(refusal(browserRequest(), ["threads", "a/b"])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "a%2Fb"])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "a%5Cb"])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "3f2a-9c"])).toBeNull();
  });

  it("refuses changes sent from another site", () => {
    expect(refusal(post({ "sec-fetch-site": "cross-site" }), ["threads"])?.status).toBe(403);
    expect(refusal(post({ "sec-fetch-site": "same-site" }), ["threads"])?.status).toBe(403);
    expect(refusal(post({ "sec-fetch-site": "same-origin" }), ["threads"])).toBeNull();
    expect(refusal(post({}), ["threads"])).toBeNull();
  });

  it("lets reads through from anywhere", () => {
    const read = browserRequest({ headers: { "sec-fetch-site": "cross-site" } });
    expect(refusal(read, ["health"])).toBeNull();
  });

  it("refuses a declared body over the limit, with the words the route uses for an undeclared one", () => {
    expect(refusal(post({ "content-length": String(MAX_BODY_BYTES + 1) }), ["threads"])).toEqual({
      status: 413,
      detail: TOO_LARGE,
    });
    expect(TOO_LARGE).toBe("That request is too large for the analysis service.");
  });
});

describe("hasBody", () => {
  it("is false for the two methods that carry none, whatever the browser attached", () => {
    expect(hasBody(browserRequest())).toBe(false);
    expect(hasBody(browserRequest({ method: "HEAD" }))).toBe(false);
    expect(hasBody(browserRequest({ method: "POST", body: "{}" }))).toBe(true);
    expect(hasBody(browserRequest({ method: "DELETE" }))).toBe(true);
  });
});

describe("passesThrough", () => {
  it("passes JSON, event streams and empty answers, and nothing else", () => {
    const answer = (status: number, type?: string) =>
      new Response(status === 204 ? null : "x", { status, headers: type ? { "content-type": type } : {} });
    expect(passesThrough(answer(200, "application/json; charset=utf-8"))).toBe(true);
    expect(passesThrough(answer(200, "text/event-stream"))).toBe(true);
    expect(passesThrough(answer(204))).toBe(true);
    expect(passesThrough(answer(500, "text/html"))).toBe(false);
    expect(passesThrough(answer(502, "text/plain"))).toBe(false);
  });

  it("never passes a redirect on", () => {
    const moved = new Response(null, { status: 307, headers: { location: "https://elsewhere.example/" } });
    expect(passesThrough(moved)).toBe(false);
    expect(passesThrough(moved, "HEAD")).toBe(false);
  });

  it("passes a HEAD answer, which has no body or type", () => {
    expect(passesThrough(new Response(null, { status: 200 }), "HEAD")).toBe(true);
    expect(passesThrough(new Response(null, { status: 503 }), "HEAD")).toBe(false);
  });
});

describe("readLimitedBody", () => {
  function chunked(parts: string[]): Request {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const part of parts) controller.enqueue(encoder.encode(part));
        controller.close();
      },
    });
    return new Request("https://onfile.example/api/threads", {
      method: "POST",
      body: stream,
      // @ts-expect-error Node's fetch needs this for a streamed body.
      duplex: "half",
    });
  }

  it("reads a body under the limit, however it is chunked", async () => {
    expect(await readLimitedBody(chunked(['{"message":', '"hi"}']), 64)).toBe('{"message":"hi"}');
  });

  it("stops at the limit when no length was declared", async () => {
    expect(await readLimitedBody(chunked(["x".repeat(40), "x".repeat(40)]), 64)).toBeNull();
  });
});
