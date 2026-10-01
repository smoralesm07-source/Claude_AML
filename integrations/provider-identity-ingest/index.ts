import { createClient } from "npm:@supabase/supabase-js@2.111.0";
import { createRemoteJWKSet, jwtVerify } from "npm:jose@6.2.5";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "provider-identity-ingest";
const REPOSITORY = "smoralesm07-source/Claude_AML";
const JWKS = createRemoteJWKSet(new URL(`${ISSUER}/.well-known/jwks`));

function respond(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

async function principal(req: Request) {
  const auth = req.headers.get("authorization") || "";
  if (!auth.startsWith("Bearer ")) throw new Error("MISSING_OIDC");
  const { payload } = await jwtVerify(auth.slice(7), JWKS, { issuer: ISSUER, audience: AUDIENCE });
  if (payload.repository !== REPOSITORY) throw new Error("WRONG_REPOSITORY");
  if (String(payload.ref || "") !== "refs/heads/main") throw new Error("WRONG_REF");
  if (!["push", "workflow_dispatch", "schedule"].includes(String(payload.event_name || ""))) throw new Error("WRONG_EVENT");
  return payload;
}

function admin() {
  const url = Deno.env.get("SUPABASE_URL");
  let key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!key) {
    const parsed = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    key = parsed.default || (Object.values(parsed)[0] as string | undefined);
  }
  if (!url || !key) throw new Error("SERVER_CREDENTIALS_UNAVAILABLE");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return respond({ error: "METHOD_NOT_ALLOWED" }, 405);
  try {
    await principal(req);
    const body = await req.json();
    const rows = Array.isArray(body?.rows) ? body.rows : [];
    if (rows.length < 1 || rows.length > 1000) return respond({ error: "INVALID_BATCH" }, 400);
    const sb = admin();
    const { data, error } = await sb.rpc("provider_identity_ingest_v1", { p_rows: rows });
    if (error) throw new Error(`${error.code || "RPC"}:${error.message}`);
    return respond(data ?? { ok: true, received: rows.length });
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    console.error("provider-identity-ingest", detail);
    return respond({ error: "INGEST_REJECTED", detail: detail.slice(0, 220) }, 403);
  }
});
