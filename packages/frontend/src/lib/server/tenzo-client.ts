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
 * Lo cachea en memoria hasta que expire para no pedir uno nuevo en cada request.
 * Si DEMO_API_KEY está disponible lo usa como Bearer directamente (más simple).
 */
export async function getTenzoToken(): Promise<string> {
  // Opción 1: usar la DEMO_API_KEY directamente como Bearer
  // El Tenzo Agent acepta tanto JWT de admin como esta clave fija.
  //if (DEMO_API_KEY) return DEMO_API_KEY;

  // Opción 2: autenticarse con usuario/contraseña de admin
  const now = Date.now();
  if (_adminToken && now < _tokenExpiresAt) return _adminToken;

  const adminPassword = process.env.TENZO_ADMIN_PASSWORD ?? "";
  const res = await fetch(`${TENZO_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "tenzo-admin", password: adminPassword }),
  });

  if (!res.ok) {
    throw new Error(`Tenzo auth failed: ${res.status}`);
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
  const token = await getTenzoToken();

  const res = await fetch(`${TENZO_BASE}/evaluar`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      descripcion_libre: input.descripcion,
      titulo: input.descripcion.slice(0, 80),
      descripcion: input.descripcion,
      categoria: input.categoria,
      duracion_horas: input.duracion_horas,
      holon_id: input.holon_id,
      // persona_id: clave canónica bajo la que Tenzo atribuye la tarea al SBT.
      // Si viene undefined o vacío, Tenzo devolvería la tarea sin persona y no
      // acreditaría HoCa al miembro. El route handler debe asegurarse de pasarlo.
      ...(input.persona_id ? { persona_id: input.persona_id } : {}),
      ...(input.ubicacion ? { ubicacion: input.ubicacion } : {}),
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Tenzo /evaluar error ${res.status}: ${text}`);
  }

  return res.json() as Promise<TenzoEvaluationResult>;
}

// ─── Auth biométrica de voz ───────────────────────────────────────────────────

/**
 * Envía un audio al Voice Auth Service (packages/voice-auth-service) para
 * autenticación biométrica. Ese servicio comparte `voice_auth.py` y
 * `member_identities` con el bot de Telegram, así que la misma voz autentica
 * al mismo miembro en ambos canales.
 *
 * VOICE_AUTH_URL debe apuntar al endpoint completo
 * (p.ej. https://hofi-voice-api-xxxx.run.app/voice/authenticate).
 *
 * El endpoint NO requiere Authorization (es público para el flujo de login
 * por voz). La protección contra abuso vive en el servicio: rate-limit por
 * IP y umbral de similitud coseno.
 *
 * Respuesta esperada (200 OK, con body `{ authenticated: false, ... }` si la
 * voz no coincide — el servicio NO responde 401 para ese caso; reserva 401
 * para errores de autorización del endpoint /voice/register):
 *
 *   {
 *     authenticated: boolean,
 *     person_id?: string,        // clave canónica (igual que bot)
 *     name?: string,             // display name del perfil matcheado
 *     role?: string,
 *     holon_id?: string,
 *     confidence?: number,       // similitud coseno 0..1
 *     session_token?: string,    // JWT firmado con JWT_SECRET_KEY compartido
 *     error?: string,
 *   }
 */
export async function verifyVoicePrint(
  audioBuffer: Buffer,
  nameClaim?: string
): Promise<{
  authenticated: boolean;
  personId?: string;
  name?: string;
  role?: string;
  holonId?: string;
  confidence?: number;
  sessionToken?: string;
  error?: string;
} | null> {
  const voiceAuthUrl = process.env.VOICE_AUTH_URL;
  if (!voiceAuthUrl) {
    console.warn("[tenzo-client] VOICE_AUTH_URL no configurado");
    return null;
  }

  const form = new FormData();
  // Aceptamos el MIME del MediaRecorder del navegador (webm/ogg). El backend
  // usa librosa.load() que resuelve el formato por magic bytes, no por header.
  const blob = new Blob([audioBuffer.buffer as ArrayBuffer], { type: "audio/webm" });
  form.append("audio", blob, "voice.webm");
  if (nameClaim) form.append("name", nameClaim);

  let res: Response;
  try {
    res = await fetch(voiceAuthUrl, { method: "POST", body: form });
  } catch (err) {
    console.error("[tenzo-client] verifyVoicePrint network error:", err);
    return { authenticated: false, error: "network" };
  }

  if (!res.ok) {
    return { authenticated: false, error: `voice_api_${res.status}` };
  }

  // Normalizar snake_case del servicio a camelCase del frontend.
  const data = (await res.json()) as {
    authenticated: boolean;
    person_id?: string;
    name?: string;
    role?: string;
    holon_id?: string;
    confidence?: number;
    session_token?: string;
    error?: string;
  };
  return {
    authenticated: data.authenticated,
    personId:     data.person_id,
    name:         data.name,
    role:         data.role,
    holonId:      data.holon_id,
    confidence:   data.confidence,
    sessionToken: data.session_token,
    error:        data.error,
  };
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
