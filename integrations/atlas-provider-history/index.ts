import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const ATLAS_URL = "https://ldmtlwzqaqmegedktlxr.supabase.co";
const ATLAS_PUBLISHABLE_KEY = "sb_publishable_Nu21dZFBM3NwtIvOwIM8ag_9tyfDJyR";
const allowedOrigins = new Set([
  "https://atlasobservatorio.app",
  "https://www.atlasobservatorio.app",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
]);

function cors(origin: string | null) {
  const allowed = origin && allowedOrigins.has(origin) ? origin : "https://atlasobservatorio.app";
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Headers": "authorization, x-client-info, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

function json(body: unknown, status: number, headers: Record<string,string>) {
  return new Response(JSON.stringify(body), { status, headers: { ...headers, "Content-Type": "application/json; charset=utf-8" } });
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");
  const headers = cors(origin);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (req.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405, headers);

  const authHeader = req.headers.get("authorization") ?? "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!token) return json({ ok: false, error: "NOT_AUTHORIZED" }, 401, headers);

  const atlas = createClient(ATLAS_URL, ATLAS_PUBLISHABLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: `Bearer ${token}` } },
  });

  const { data: userData, error: userError } = await atlas.auth.getUser(token);
  if (userError || !userData.user) return json({ ok: false, error: "NOT_AUTHORIZED" }, 401, headers);

  const { data: allowed, error: gateError } = await atlas.rpc("atlas_require_allowed_user");
  if (gateError || allowed !== true) return json({ ok: false, error: "NOT_ALLOWED" }, 403, headers);

  let body: Record<string, unknown> = {};
  try { body = await req.json(); } catch { /* handled below */ }

  const rut = String(body.rut ?? "").toUpperCase().replace(/[^0-9K]/g, "");
  const currentYear = new Date().getUTCFullYear();
  const fromYear = Math.max(2007, Math.min(Number(body.from_year ?? 2020) || 2020, currentYear));
  const toYear = Math.max(fromYear, Math.min(Number(body.to_year ?? currentYear) || currentYear, currentYear));

  if (!/^[0-9]{6,8}[0-9K]$/.test(rut)) return json({ ok: false, error: "INVALID_RUT" }, 400, headers);

  const provider = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await provider.rpc("provider_entity_history_v1", {
    p_rut: rut,
    p_from_year: fromYear,
    p_to_year: toYear,
  });

  if (error) {
    console.error("provider_entity_history_v1", error.code, error.message);
    return json({ ok: false, error: "QUERY_FAILED" }, 500, headers);
  }

  return new Response(JSON.stringify(data ?? { ok: true, summary: null, years: [], buyers: [] }), {
    status: 200,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "private, max-age=300" },
  });
});
