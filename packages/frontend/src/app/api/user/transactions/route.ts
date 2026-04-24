export const dynamic = 'force-dynamic'

// GET /api/user/transactions
// Historial de transacciones personales del usuario autenticado.
// Alimenta el componente PersonalActivity.
// Requiere sesión activa.

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { queryUserTransactions } from "@/lib/server/db";
import { canonicalPersonId } from "@/lib/server/canonical";

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession();

    if (!session) {
      return NextResponse.json({ error: "No autenticado" }, { status: 401 });
    }

    const limitParam = req.nextUrl.searchParams.get("limit");
    const limit = Math.min(parseInt(limitParam ?? "20"), 50);

    // tasks.persona_id guarda la clave canónica (bot + frontend usan la misma
    // derivación). Nunca consultamos por el display name.
    const personaId =
      canonicalPersonId(session.userId) ||
      canonicalPersonId(session.name);

    const transactions = await queryUserTransactions(
      session.holonId,
      personaId,
      limit
    );

    return NextResponse.json(transactions);
  } catch (err) {
    console.error("[/api/user/transactions] Error:", err);
    return NextResponse.json([], { status: 200 });
  }
}

