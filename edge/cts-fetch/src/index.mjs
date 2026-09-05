// CTS news API only. The key is stored as a Worker secret, never in this file.
export default {
  async fetch(request, env) {
    if (!env.CTS_FETCH_TOKEN) {
      return Response.json({ error: "Service not configured" }, { status: 503 });
    }
    if (request.headers.get("Authorization") !== `Bearer ${env.CTS_FETCH_TOKEN}`) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (request.method !== "GET") {
      return Response.json({ error: "GET required" }, { status: 405 });
    }

    const url = new URL(request.url);
    const list = /^\/api\/news\/(politics|society|life|international)\/list$/.test(url.pathname);
    const article = /^\/api\/news\/\d{15}$/.test(url.pathname);
    if (!list && !article) {
      return Response.json({ error: "Unsupported CTS path" }, { status: 400 });
    }
    if ([...url.searchParams.keys()].some(key => !list || !["page", "limit"].includes(key))) {
      return Response.json({ error: "Unsupported query" }, { status: 400 });
    }
    const page = url.searchParams.get("page") ?? "1";
    const limit = url.searchParams.get("limit") ?? "30";
    if (list && (!/^\d+$/.test(page) || +page < 1 || +page > 15 || limit !== "30")) {
      return Response.json({ error: "Invalid pagination" }, { status: 400 });
    }

    const upstreamUrl = new URL(url.pathname, "https://news.cts.com.tw");
    if (list) {
      upstreamUrl.searchParams.set("page", page);
      upstreamUrl.searchParams.set("limit", "30");
    }
    try {
      const upstream = await fetch(upstreamUrl, {
        headers: {
          "Accept": "application/json",
          "User-Agent": "SquareNewsCrawler/1.0 (+https://square.news)",
        },
        redirect: "manual",
        signal: AbortSignal.timeout(20000),
      });
      if (!upstream.ok) {
        return Response.json({ error: "CTS upstream error", upstreamStatus: upstream.status }, {
          status: upstream.status >= 400 ? upstream.status : 502,
          headers: upstream.headers.has("Retry-After")
            ? { "Retry-After": upstream.headers.get("Retry-After") } : {},
        });
      }
      if (!upstream.headers.get("Content-Type")?.includes("application/json")) {
        return Response.json({ error: "Unexpected CTS response" }, { status: 502 });
      }
      return new Response(upstream.body, {
        headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
      });
    } catch {
      return Response.json({ error: "CTS request failed" }, { status: 502 });
    }
  },
};
