// Public assets and a same-origin bridge to an operator-selected evaluator.
// No Python execution, credentials, or evaluation artifacts live in this Worker.
export function evaluatorOrigin(value) {
  if (!value) return null;
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("EVALUATOR_ORIGIN must be an HTTPS origin");
  }
  return url.origin;
}
export function evaluatorPath(path) {
  return (
    /^\/(api|runs|cards|entries|tracks|templates)(\/|$)/.test(path) ||
    /^\/me(\/|$)/.test(path) ||
    [
      "/login/github",
      "/auth/github/callback",
      "/logout",
      "/methodology",
      "/cli/authorize",
    ].includes(path)
  );
}
const json = (body, status = 200) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.cuaspeedrun.com") {
      url.hostname = "cuaspeedrun.com";
      return Response.redirect(url.toString(), 308);
    }
    const origin = evaluatorOrigin(env.EVALUATOR_ORIGIN);
    if (url.pathname === "/site-api/status")
      return json({ configured: Boolean(origin) });
    if (["/", "/submit", "/submit/"].includes(url.pathname)) {
      const asset = new URL(request.url);
      asset.pathname =
        url.pathname === "/" ? "/index.html" : "/submit/index.html";
      return env.ASSETS.fetch(new Request(asset, request));
    }
    if (!evaluatorPath(url.pathname)) return env.ASSETS.fetch(request);
    if (!origin)
      return json(
        {
          detail:
            "Hosted evaluations are not open yet. Run independently using the developer guide.",
        },
        503,
      );
    if (origin === url.origin)
      return json({ detail: "Evaluator configuration is invalid." }, 503);
    // Cookie-authenticated writes must originate on this public site. CLI
    // bearer clients have no Origin header and use the existing API contract.
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      const suppliedOrigin = request.headers.get("Origin");
      if (
        (suppliedOrigin && suppliedOrigin !== url.origin) ||
        request.headers.get("Sec-Fetch-Site") === "cross-site"
      )
        return json({ detail: "Cross-origin writes are not allowed." }, 403);
    }
    const upstream = new URL(url.pathname + url.search, origin);
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.set("X-Forwarded-Host", url.host);
    headers.set("X-Forwarded-Proto", "https");
    try {
      const response = await fetch(
        new Request(upstream, {
          method: request.method,
          headers,
          body: ["GET", "HEAD"].includes(request.method)
            ? undefined
            : request.body,
          redirect: "manual",
        }),
      );
      const outgoing = new Headers(response.headers);
      outgoing.set("Cache-Control", "private, no-store");
      outgoing.set("X-Content-Type-Options", "nosniff");
      const location = outgoing.get("Location");
      if (location) {
        const redirect = new URL(location, origin);
        if (redirect.origin === origin)
          outgoing.set(
            "Location",
            url.origin + redirect.pathname + redirect.search + redirect.hash,
          );
      }
      const cookies = outgoing.getSetCookie();
      if (cookies.length) {
        outgoing.delete("Set-Cookie");
        for (const cookie of cookies)
          outgoing.append(
            "Set-Cookie",
            /;\s*secure\b/i.test(cookie) ? cookie : cookie + "; Secure",
          );
      }
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: outgoing,
      });
    } catch {
      return json(
        {
          detail:
            "The evaluation service is temporarily unavailable. Please try again later.",
        },
        502,
      );
    }
  },
};
