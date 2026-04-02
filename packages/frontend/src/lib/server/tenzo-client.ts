// HoFi Protocol — Cliente server-side para el Tenzo Agent
// Solo importar en Route Handlers (nunca en "use client").
// Mantiene las credenciales del Tenzo Agent fuera del browser.

import type { TenzoEvaluationInput, TenzoEvaluationResult } from "@/lib/api/types";

// ─── Configuración ────────────────────────────────────────────────────────────

const TENZO_BASE =
  process.env.TENZO_AGENT_URL ??
  "https://hofi-tenzo-1080243330445.us-central1.run.app";

const DEMO_API_KEY =
  process.env.DEMO_API_KEY ??
  "644834adec7c5ad08122f1e1cdf13d19f004bf7f6e6af119e38ca53698b1f1ad";

// Cache en memoria del token de admin (evita un round-trip por request)
let _adminToken: string | null = null;
let _tokenExpiresAt = 0;

// ─── Autenticación con Tenzo ─────────────────────────────────────────────────

/**
 * Obtiene un JWT de admin del Tenzo Agent.
 * Usa DEMO_API_KEY como contraseña en /auth/token para obtener un JWT real.
 * Cachea el JWT en memoria hasta 2min antes de que expire (~30min).
 */
export async function getTenzoToken(): Promise<string> {
  const now = Date.now();
  if (_adminToken && now < _tokenExpiresAt) return _adminToken;

  // DEMO_API_KEY es la contraseña del admin en el Tenzo Agent
  const password = DEMO_API_KEY || process.env.TENZO_ADMIN_PASSWORD || "";
  if (!password) throw new Error("No hay credenciales para autenticarse con el Tenzo Agent");

  const res = await fetch(`${TENZO_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "tenzo-admin", password }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Tenzo auth failed ${res.status}: ${text}`);
  }

  const data = await res.json();
  _adminToken = data.access_token as string;
  // Los JWT de Tenzo duran ~30min; refrescamos 2min antes
  _tokenExpiresAt = now + 28 * 60 * 1000;
  return _adminToken;
}

// ─── Evaluación de tareas ─────────────────────────────────────────────────────

/**
 * Envía una tarea de cuidado al Tenzo Agent para su evaluación.
 * El resultado incluye si fue aprobada, HOCA a otorgar y razonamiento.
 */
export async function evaluateCareTask(
  input: TenzoEvaluationInput
): Promise<TenzoEvaluationResult> {
  const body = JSON.stringify({
    descripcion: input.descripcion,
    categoria: input.categoria,
    duracion_horas: input.duracion_horas,
    holon_id: input.holon_id,
    ...(input.ubicacion ? { ubicacion: input.ubicacion } : {}),
  });

  const doRequest = async (token: string) =>
    fetch(`${TENZO_BASE}/evaluar`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body,
    });

  let token = await getTenzoToken();
  let res = await doRequest(token);

  // Si el token en caché está caducado, lo forzamos a refrescar y reintentamos una vez
  if (res.status === 401) {
    _adminToken = null;
    _tokenExpiresAt = 0;
    token = await getTenzoToken();
    res = await doRequest(token);
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Tenzo /evaluar error ${res.status}: ${text}`);
  }

  return res.json() as Promise<TenzoEvaluationResult>;
}

// ─── Auth biométrica de voz ───────────────────────────────────────────────────

/**
 * Envía un audio al servicio de biometría de voz del Bot/Tenzo para autenticar.
 *
 * El VOICE_AUTH_URL apunta al endpoint de voice-auth que será implementado
 * en el Bot de Cloud Run (packages/telegram-bot) o en un endpoint nuevo del
 * Tenzo Agent. Por ahora retorna null si no está configurado.
 *
 * Flujo esperado del endpoint remoto:
 *   POST multipart/form-data { audio: Blob, name?: string }
 *   → 200 { authenticated: true, user_id, name, role, holon_id, confidence }
 *   → 401 { authenticated: false, error }
 */
export async function verifyVoicePrint(
  audioBuffer: Buffer,
  nameClaim?: string
): Promise<{
  authenticated: boolean;
  userId?: string;
  name?: string;
  role?: string;
  holonId?: string;
  confidence?: number;
} | null> {
  const voiceAuthUrl = process.env.VOICE_AUTH_URL;
  if (!voiceAuthUrl) {
    // Voice auth no configurado aún — fallback: no autenticado
    // TODO: implementar endpoint /voice-auth en packages/telegram-bot
    console.warn("[tenzo-client] VOICE_AUTH_URL no configurado");
    return null;
  }

  const form = new FormData();
  const blob = new Blob([audioBuffer.buffer as ArrayBuffer], { type: "audio/webm" });
  form.append("audio", blob, "voice.webm");
  if (nameClaim) form.append("name", nameClaim);

  const token = await getTenzoToken();

  const res = await fetch(voiceAuthUrl, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) return { authenticated: false };
  return res.json();
}

// ─── Stats del protocolo ──────────────────────────────────────────────────────

/**
 * Obtiene estadísticas globales del protocolo desde el Tenzo Agent.
 * Útil para el World View y métricas globales.
 */
export async function getProtocolStats(): Promise<Record<string, unknown>> {
  const token = await getTenzoToken();

  const res = await fetch(`${TENZO_BASE}/protocol/stats`, {
    headers: { Authorization: `Bearer ${token}` },
    next: { revalidate: 60 }, // Cache 60s en Next.js
  });

  if (!res.ok) throw new Error(`Tenzo /protocol/stats error: ${res.status}`);
  return res.json();
}

/**
 * Health check del Tenzo Agent.
 */
export async function checkTenzoHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${TENZO_BASE}/health`, {
      next: { revalidate: 30 },
    });
    return res.ok;
  } catch {
    return false;
  }
}
