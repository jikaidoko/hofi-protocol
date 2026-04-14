// GET /api/user/transactions
// Historial de transacciones personales del usuario autenticado.
// Alimenta el componente PersonalActivity.
// Requiere sesión activa.

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";

export const dynamic = "force-dynamic";
import { queryUserTransactions } from "@/lib/server/db";

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession();

    if (!session) {
      return NextResponse.json({ error: "No autenticado" }, { status: 401 });
    }

    const limitParam = req.nextUrl.searchParams.get("limit");
    const limit = Math.min(parseInt(limitParam ?? "20"), 50);

    const transactions = await queryUserTransactions(
      session.holonId,
      session.name,
      limit
    );

    return NextResponse.json(transactions);
  } catch (err) {
    console.error("[/api/user/transactions] Error:", err);
    return NextResponse.json([], { status: 200 });
  }
}
