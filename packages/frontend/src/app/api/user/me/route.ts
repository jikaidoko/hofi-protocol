export const dynamic = 'force-dynamic'

// GET /api/user/me
// Perfil del usuario autenticado: nombre, rol, holón, balance HOCA.
// Requiere sesión activa (cookie httpOnly).
//
// El balance HOCA se consulta desde Cloud SQL (suma histórica de tasks aprobadas).
// Cuando ON_CHAIN=true, se debería leer del contrato HoCaToken en HolonChain/Sepolia.

import { NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { queryMemberBalance } from "@/lib/server/db";

export async function GET() {
  try {
    const session = await getServerSession();

    if (!session) {
      return NextResponse.json(
        { error: "No autenticado" },
        { status: 401 }
      );
    }

    // Enriquecer con balance real de Cloud SQL
    let balance = session.balance;
    try {
      balance = await queryMemberBalance(session.holonId, session.name);
    } catch {
      // DB no disponible — usar balance del token (puede estar en 0)
    }

    return NextResponse.json({ ...session, balance });
  } catch (err) {
    console.error("[/api/user/me] Error:", err);
    return NextResponse.json({ error: "Error interno del servidor" }, { status: 500 });
  }
}

