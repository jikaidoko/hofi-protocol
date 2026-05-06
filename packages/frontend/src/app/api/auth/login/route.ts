// POST /api/auth/login
// Autenticación por email + contraseña contra la tabla `users` en Cloud SQL.
//
// Flujo:
//   1. Browser envía {email, password} como JSON
//   2. Este handler llama a POST /auth/email/login del Tenzo Agent (que
//      valida bcrypt contra la tabla users)
//   3. Si las credenciales son válidas, firmamos la cookie httpOnly
//      `hofi_session` con el mismo helper que usa el voice login
//   4. Devolvemos la sesión al cliente (sin el token; vive en la cookie)
//
// Patrón idéntico a /api/auth/voice — el Tenzo es la fuente de verdad para
// credenciales, este endpoint solo monta la sesión Next.js encima.

import { NextRequest, NextResponse } from "next/server";
import { signSessionToken, sessionCookieOptions } from "@/lib/server/auth";
import { emailLogin } from "@/lib/server/tenzo-client";
import { queryMemberBalance } from "@/lib/server/db";
import type { UserRole, UserSession } from "@/lib/api/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { email, password } = body as { email?: string; password?: string };

    if (!email || !password) {
      return NextResponse.json(
        { error: "Se requieren email y password" },
        { status: 400 }
      );
    }

    // ── Validación contra el Tenzo Agent ──────────────────────────────────────
    const result = await emailLogin({ email, password });
    if (!result.ok) {
      // El Tenzo devuelve 401 con detail "Credenciales inválidas" si falla
      // y 503 si DB está en modo mock. Reenviamos el mismo status para que
      // el modal pueda mostrarlo bien.
      return NextResponse.json(
        { error: result.error ?? "Credenciales inválidas" },
        { status: result.status === 503 ? 503 : 401 }
      );
    }

    const u = result.user;

    // Cargar balance HoCa desde Cloud SQL (la cookie no lo persiste — se
    // refresca en cada login). Best-effort: si la DB no responde, queda en 0
    // y la UI lo recargará desde /api/user/me.
    let balance = 0;
    try {
      balance = await queryMemberBalance(u.holonId, u.personId);
    } catch {
      // ignorar — el balance es secundario al login
    }

    const role: UserRole = (u.role as UserRole) ?? "member";
    const session: UserSession = {
      userId: u.personId,
      name: u.memberName,
      role,
      holonId: u.holonId,
      balance,
      avatar: u.memberName.substring(0, 2).toUpperCase(),
    };

    const token = await signSessionToken(session);
    const cookieOpts = sessionCookieOptions(token);

    const response = NextResponse.json({ session });
    response.cookies.set(cookieOpts);
    return response;
  } catch (err) {
    console.error("[/api/auth/login] Error:", err);
    return NextResponse.json(
      { error: "Error interno del servidor" },
      { status: 500 }
    );
  }
}
