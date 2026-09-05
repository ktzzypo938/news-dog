import test from "node:test";
import assert from "node:assert/strict";
import worker from "./src/index.mjs";

const env = { CTS_FETCH_TOKEN: "test-only" };
const request = path => new Request(`https://worker.example${path}`, {
  headers: { Authorization: "Bearer test-only" },
});

test("rejects unauthenticated and arbitrary forwarding requests", async () => {
  assert.equal((await worker.fetch(new Request("https://worker.example/api/news/politics/list"), env)).status, 401);
  for (const path of ["/", "/api/news/sports/list", "/api/news/politics/list?url=https://example.com", "/api/news/politics/list?page=999", "/api/news/politics/list?limit=10000"]) {
    assert.equal((await worker.fetch(request(path), env)).status, 400);
  }
});

test("forwards only the official endpoint and never forwards the caller key", async t => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url: String(url), options });
    return Response.json({ status: true, data: { articles: [] } });
  });
  const result = await worker.fetch(request("/api/news/politics/list?page=2"), env);
  assert.equal(result.status, 200);
  assert.equal(calls[0].url, "https://news.cts.com.tw/api/news/politics/list?page=2&limit=30");
  assert.equal(calls[0].options.headers.Authorization, undefined);
  assert.equal(calls[0].options.redirect, "manual");
  assert.deepEqual(await result.json(), { status: true, data: { articles: [] } });
});

test("preserves rate limits and does not retry the upstream request", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    return new Response("Limited", { status: 429, headers: { "Retry-After": "120" } });
  });
  const result = await worker.fetch(request("/api/news/202609053075329"), env);
  assert.equal(result.status, 429);
  assert.equal(result.headers.get("Retry-After"), "120");
  assert.equal(calls, 1);
});
