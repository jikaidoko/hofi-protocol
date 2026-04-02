// HoFi Protocol — Helpers de autenticación del lado del servidor
// Firma y verifica JWT usando la misma JWT_SECRET_KEY que usa el Tenzo Agent.
// Solo importar en Server Components o Route Handlers (nunca en "use client").

import { cookies } from "next/headers";
import type { UserRole, UserSession } from "@/lib/api/types";

// ─── Constantes ───────────────────────────────────────────────────────────────

const JWT_SECRET = process.env.JWT_SECRET_KEY ?? "";
const SESSION_COOKIE = "hofi_session";
const TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7; // 7 días

// ─── Tipos internos del payload JWT ──────────────────────────────────────────

interface JwtPayload {
  sub: string;          // userId
  name: string;
  role: UserRole;
  holon: string;        // holonId
  avatar: string;
  iat: number;
  exp: number;
}

// ─── Implementación mínima HMAC-SHA256 sin dependencia externa ───────────────
// Usamos la Web Crypto API disponible en Node 18+ y en el Edge Runtime.

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function base64UrlDecode(str: string): Uint8Array {
  const padded = str + "=".repeat((4 - (str.length % 4)) % 4);
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function hmacSign(payload: string, secret: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return base64UrlEncode(new Uint8Array(sig));
}

async function hmacVerify(
  payload: string,
  signature: string,
  secret: string
): Promise<boolean> {
  const expected = await hmacSign(payload, secret);
  // Comparación de tiempo constante (evita timing attacks)
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return diff === 0;
}

// ─── API pública ──────────────────────────────────────────────────────────────

/**
 * Genera un JWT firmado con la misma clave que usa el Tenzo Agent.
 */
export async function signSessionToken(session: UserSession): Promise<string> {
  if (!JWT_SECRET) throw new Error("JWT_SECRET_KEY no configurado");

  const header = base64UrlEncode(
    new TextEncoder().encode(JSON.stringify({ alg: "HS256", typ: "JWT" }))
  );
  const now = Math.floor(Date.now() / 1000);
  const payload: JwtPayload = {
    sub: session.userId,
    name: session.name,
    role: session.role,
    holon: session.holonId,
    avatar: session.avatar,
    iat: now,
    exp: now + TOKEN_TTL_SECONDS,
  };
  const encodedPayload = base64UrlEncode(
    new TextEncoder().encode(JSON.stringify(payload))
  );
  const data = `${header}.${encodedPayload}`;
  const sig = await hmacSign(data, JWT_SECRET);
  return `${data}.${sig}`;
}

/**
 * Verifica y decodifica un JWT. Devuelve null si es inválido o expirado.
 */
export async function verifySessionToken(
  token: string
): Promise<UserSession | null> {
  if (!JWT_SECRET) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    const [header, encodedPayload, sig] = parts;
    const valid = await hmacVerify(`${header}.${encodedPayload}`, sig, JWT_SECRET);
    if (!valid) return null;

    const payload = JSON.parse(
      new TextDecoder().decode(base64UrlDecode(encodedPayload))
    ) as JwtPayload;

    if (payload.exp < Math.floor(Date.now() / 1000)) return null;

    return {
      userId: payload.sub,
      name: payload.name,
      role: payload.role,
      holonId: payload.holon,
      balance: 0,          // El balance se consulta por separado en Cloud SQL
      avatar: payload.avatar,
    };
  } catch {
    return null;
  }
}

/**
 * Lee la sesión actual desde la cookie httpOnly.
 * Úsalo en Route Handlers y Server Components.
 */
export async function getServerSession(): Promise<UserSession | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return verifySessionToken(token);
}

/**
 * Devuelve los atributos para escribir la cookie de sesión (httpOnly, Secure, SameSite).
 */
export function sessionCookieOptions(token: string) {
  return {
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: TOKEN_TTL_SECONDS,
  };
}

/**
 * Opciones para borrar la cookie de sesión (logout).
 */
export function clearCookieOptions() {
  return {
    name: SESSION_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 0,
  };
}
