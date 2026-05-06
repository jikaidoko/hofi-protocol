// POST /api/auth/register
// Crea una cuenta email/password en la tabla `users` (Cloud SQL) y firma
// inmediatamente la cookie de sesión, igual que /api/auth/login.
//
// Body:
//   {
//     email:        string,
//     password:     string,         // mínimo 8 caracteres
//     memberName:   string,         // display name; el person_id canónico
//                                   // se deriva en el Tenzo (lower ASCII)
//     holonId?:     string,         // default: "familia-mourino"
//     role?:        "member" | "guardian"   // default: "member"
//   }
//
// Errores comunes:
//   400 — validación (campos faltantes)
//   409 — email o member_name ya en uso (el Tenzo decide)
//   503 — DB en modo mock (entornos de dev sin DB real)

import { NextRequest, NextResponse } from "next/server";
import { signSessionToken, sessionCookieOptions } from "@/lib/server/auth";
import { emailRegister } from "@/lib/server/tenzo-client";
import type { UserRole, UserSession } from "@/lib/api/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { email, password, memberName, holonId, role } = body as {
      email?: string;
      password?: string;
      memberName?: string;
      holonId?: string;
      role?: string;
    };

    if (!email || !password || !memberName) {
      return NextResponse.json(
        { error: "Se requieren email, password y memberName" },
        { status: 400 }
      );
    }

    if (password.length < 8) {
      return NextResponse.json(
        { error: "La contraseña debe tener al menos 8 caracteres" },
        { status: 400 }
      );
    }

    if (memberName.trim().length < 2) {
      return NextResponse.json(
        { error: "El nombre debe tener al menos 2 caracteres" },
        { status: 400 }
      );
    }

    // ── Llamada al Tenzo ──────────────────────────────────────────────────────
    const result = await emailRegister({
      email,
      password,
      memberName,
      holonId,
      role,
    });

    if (!result.ok) {
      // El Tenzo devuelve 409 con detail explicativo si email/person_id duplicados.
      const status =
        result.status === 409 ? 409 :
        result.status === 503 ? 503 :
        result.status >= 400 && result.status < 500 ? result.status : 500;
      return NextResponse.json({ error: result.error }, { status });
    }

    // ── Cuenta creada → firmar cookie de sesión ──────────────────────────────
    const u = result.user;
    const userRole: UserRole = (u.role as UserRole) ?? "member";
    const session: UserSession = {
      userId: u.personId,
      name: u.memberName,
      role: userRole,
      holonId: u.holonId,
      balance: 0,    // usuario nuevo: balance arranca en 0
      avatar: u.memberName.substring(0, 2).toUpperCase(),
    };

    const token = await signSessionToken(session);
    const cookieOpts = sessionCookieOptions(token);

    const response = NextResponse.json({ session, registered: true });
    response.cookies.set(cookieOpts);
    return response;
  } catch (err) {
    console.error("[/api/auth/register] Error:", err);
    return NextResponse.json(
      { error: "Error interno del servidor" },
      { status: 500 }
    );
  }
}
