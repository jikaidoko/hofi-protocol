// HoFi Protocol — Cliente API del lado del browser
// Wrapper sobre fetch que inyecta el JWT desde la cookie de sesión y
// normaliza errores. Todos los componentes del nuevo UI deben usar estas
// funciones en vez de llamar directamente a los backends externos.

import type {
  ApiResponse,
  UserSession,
  VoiceAuthResult,
  TenzoEvaluationInput,
  TenzoEvaluationResult,
  HolonStats,
  ActivityItem,
  SocialYieldMetric,
  HolonLocation,
  PersonalTransaction,
} from "./types";

// ─── Base fetch ───────────────────────────────────────────────────────────────

/**
 * Hace un fetch a un endpoint /api/* del propio Next.js.
 * Las cookies de sesión se envían automáticamente (credentials: "include").
 */
async function hoFiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  try {
    const res = await fetch(path, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    const json = await res.json();

    if (!res.ok) {
      return {
        ok: false,
        error: json?.error ?? `HTTP ${res.status}`,
        status: res.status,
      };
    }

    return { ok: true, data: json as T };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Autenticación por voz: envía el blob de audio al servidor.
 * El servidor lo reenvía al servicio de biometría de voz (bot o tenzo)
 * y, si coincide, devuelve una sesión JWT.
 */
export async function authByVoice(
  audioBlob: Blob,
  nameClaim?: string
): Promise<ApiResponse<VoiceAuthResult>> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "voice.webm");
  if (nameClaim) formData.append("name", nameClaim);

  try {
    const res = await fetch("/api/auth/voice", {
      method: "POST",
      credentials: "include",
      body: formData,
      // Sin Content-Type: el browser lo pone automáticamente con boundary
    });
    const json = await res.json();
    if (!res.ok) return { ok: false, error: json?.error ?? `HTTP ${res.status}` };
    return { ok: true, data: json as VoiceAuthResult };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Network error" };
  }
}

/**
 * Login por email + contraseña.
 * El servidor verifica contra Cloud SQL y devuelve JWT en cookie httpOnly.
 */
export async function authByEmail(
  email: string,
  password: string
): Promise<ApiResponse<{ session: UserSession }>> {
  return hoFiFetch<{ session: UserSession }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

/**
 * Inicia el flujo OAuth para un proveedor social.
 * Redirige al servidor que construye la URL del proveedor.
 */
export function startOAuthFlow(provider: "google" | "telegram" | "x"): void {
  window.location.href = `/api/auth/oauth/${provider}`;
}

/**
 * Cierra la sesión limpiando la cookie httpOnly del servidor.
 */
export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
}

// ─── Cuidado / Care ───────────────────────────────────────────────────────────

/**
 * Registra un acto de cuidado por texto (Manual Entry).
 * El servidor lo evalúa con el Tenzo Agent y devuelve el resultado.
 */
export async function registerCareByText(
  input: TenzoEvaluationInput
): Promise<ApiResponse<TenzoEvaluationResult>> {
  return hoFiFetch<TenzoEvaluationResult>("/api/care/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/**
 * Registra un acto de cuidado por voz (Voice Register).
 * Envía el audio; el servidor transcribe, parsea y evalúa con Tenzo.
 */
export async function registerCareByVoice(
  audioBlob: Blob
): Promise<ApiResponse<TenzoEvaluationResult>> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "care.webm");

  try {
    const res = await fetch("/api/care/voice", {
      method: "POST",
      credentials: "include",
      body: formData,
    });
    const json = await res.json();
    if (!res.ok) return { ok: false, error: json?.error ?? `HTTP ${res.status}` };
    return { ok: true, data: json as TenzoEvaluationResult };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Network error" };
  }
}

// ─── Holon ────────────────────────────────────────────────────────────────────

/**
 * Estadísticas generales del holón (miembros, salud, HOCA distribuidas, etc.)
 */
export async function getHolonStats(
  holonId: string
): Promise<ApiResponse<HolonStats>> {
  return hoFiFetch<HolonStats>(`/api/holon/${holonId}`);
}

/**
 * Feed de actividad del holón, filtrado por el rol del usuario que consulta.
 * El servidor aplica la máscara de privacidad apropiada.
 */
export async function getHolonFeed(
  holonId: string
): Promise<ApiResponse<ActivityItem[]>> {
  return hoFiFetch<ActivityItem[]>(`/api/holon/${holonId}/feed`);
}

/**
 * Métricas de rendimiento social del holón (Social Yield).
 */
export async function getHolonYield(
  holonId: string
): Promise<ApiResponse<SocialYieldMetric[]>> {
  return hoFiFetch<SocialYieldMetric[]>(`/api/holon/${holonId}/yield`);
}

// ─── Usuario ──────────────────────────────────────────────────────────────────

/**
 * Perfil del usuario autenticado (requiere sesión activa).
 */
export async function getMyProfile(): Promise<ApiResponse<UserSession>> {
  return hoFiFetch<UserSession>("/api/user/me");
}

/**
 * Historial de transacciones personales del usuario autenticado.
 */
export async function getMyTransactions(): Promise<
  ApiResponse<PersonalTransaction[]>
> {
  return hoFiFetch<PersonalTransaction[]>("/api/user/transactions");
}

// ─── Mundo / World map ────────────────────────────────────────────────────────

/**
 * Lista de todos los holones con coordenadas para el mapa mundial.
 */
export async function getWorldHolons(): Promise<ApiResponse<HolonLocation[]>> {
  return hoFiFetch<HolonLocation[]>("/api/world/holons");
}
