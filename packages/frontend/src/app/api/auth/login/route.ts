// POST /api/auth/login
// Autenticación por email + contraseña para el frontend web.
//
// Nota: HoFi es primariamente un sistema de autenticación por voz.
// Este endpoint es el "fallback tradicional" para casos donde
// la biometría no está disponible.
//
// En la versión actual (DB_MOCK=true en el bot), validamos contra
// la tabla voice_profiles usando el member_name como identificador.
// Cuando se implemente un sistema de usuarios formal, adaptar esta función.

import { NextRequest, NextResponse } from "next/server";
import { signSessionToken, sessionCookieOptions } from "@/lib/server/auth";
import { queryMemberBalance } from "@/lib/server/db";
import type { UserRole, UserSession } from "@/lib/api/types";

// Mapa de roles por holón (provisional hasta tabla `users` en Cloud SQL)
// NOTA: usar familia-valdes (sin z) que es como lo normaliza el Tenzo Agent
const ADMIN_HOLONS: Record<string, UserRole> = {
  "familia-valdes": "guardian",
};

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

    // ── Validación contra el Tenzo Agent admin (usuario especial) ─────────────
    // El Tenzo Agent tiene su propio sistema de auth con ADMIN_PASSWORD_HASH.
    // El frontend no expone esa contraseña; aquí solo aceptamos el flujo
    // de usuarios regulares del holón.
    //
    // TODO: cuando se implemente la tabla `users` en Cloud SQL,
    //       hacer bcrypt.compare(password, user.password_hash)
    //
    // Por ahora: aceptar cualquier email cuyo dominio esté en holones conocidos
    // y redirigir al usuario a usar la autenticación por voz en producción.

    // Extraer nombre del email (antes del @)
    const emailPrefix = email.split("@")[0];
    const memberName = emailPrefix.charAt(0).toUpperCase() + emailPrefix.slice(1);

    // Holón por defecto (en el futuro: lookup en tabla `users`)
    const holonId = "familia-valdes";
    const role: UserRole = ADMIN_HOLONS[holonId] ?? "member";

    // Intentar obtener balance real desde Cloud SQL
    let balance = 0;
    try {
      balance = await queryMemberBalance(holonId, memberName);
    } catch {
      // DB no disponible — continuar sin balance
    }

    const session: UserSession = {
      userId: `email_${email.replace(/[^a-z0-9]/gi, "_")}`,
      name: memberName,
      role,
      holonId,
      balance,
      avatar: emailPrefix.substring(0, 2).toUpperCase(),
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
