// GET /api/debug/tenzo — diagnoses Tenzo Agent auth from the Vercel server side
// REMOVE THIS FILE AFTER DEBUGGING
import { NextResponse } from "next/server";

const TENZO_BASE =
  process.env.TENZO_AGENT_URL ??
  "https://hofi-tenzo-1080243330445.us-central1.run.app";

const DEMO_API_KEY =
  process.env.DEMO_API_KEY ??
  "644834adec7c5ad08122f1e1cdf13d19f004bf7f6e6af119e38ca53698b1f1ad";

export async function GET() {
  const results: Record<string, unknown> = {
    tenzo_base: TENZO_BASE,
    demo_key_prefix: DEMO_API_KEY.slice(0, 8) + "…",
    demo_key_length: DEMO_API_KEY.length,
  };

  // 1. Health check
  try {
    const health = await fetch(`${TENZO_BASE}/health`);
    results.health = { status: health.status, ok: health.ok };
  } catch (e) {
    results.health = { error: String(e) };
  }

  // 2. Auth — get a fresh token
  let token: string | null = null;
  try {
    const authRes = await fetch(`${TENZO_BASE}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "tenzo-admin", password: DEMO_API_KEY }),
    });
    const authBody = await authRes.text();
    results.auth = { status: authRes.status, bodyPreview: authBody.slice(0, 200) };
    if (authRes.ok) {
      const parsed = JSON.parse(authBody);
      token = parsed.access_token as string;
      results.token_preview = token ? token.slice(0, 30) + "…" : null;
      results.token_length = token?.length ?? 0;
    }
  } catch (e) {
    results.auth = { error: String(e) };
  }

  // 3. Evaluar with fresh token
  if (token) {
    try {
      const evalRes = await fetch(`${TENZO_BASE}/evaluar`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          descripcion_libre: "Test de diagnóstico — cuidado de adulto mayor durante 1 hora",
          titulo: "Test de diagnóstico",
          descripcion: "Test de diagnóstico — cuidado de adulto mayor durante 1 hora",
          categoria: "acompanamiento",
          duracion_horas: 1,
          holon_id: "familia-mourino",
        }),
      });
      const evalBody = await evalRes.text();
      results.evaluar = { status: evalRes.status, body: evalBody.slice(0, 500) };
    } catch (e) {
      results.evaluar = { error: String(e) };
    }
  }

  return NextResponse.json(results);
}
