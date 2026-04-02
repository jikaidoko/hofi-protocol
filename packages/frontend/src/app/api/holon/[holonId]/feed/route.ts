// GET /api/holon/[holonId]/feed
// Feed de actividades del holón con máscara de privacidad por rol.
//
// Visibilidad según rol:
//   - guest:    cantidad + categoría + timestamp vago (sin identidad)
//   - member:   + iniciales de avatar + rango de HOCA
//   - guardian: + nombre completo + descripción + HOCA exactas + hora exacta
//
// Este sistema de privacidad diferencial es central en la filosofía HoFi:
// "el acto de cuidar es el rendimiento" — visible, pero con dignidad.

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { queryActivityFeed } from "@/lib/server/db";
import type { UserRole } from "@/lib/api/types";

export const revalidate = 30; // Refrescar cada 30s

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ holonId: string }> }
) {
  try {
    const { holonId } = await params;

    // Determinar rol del usuario que consulta
    const session = await getServerSession();
    const role: UserRole = session?.role ?? "guest";

    // Limit configurable por query param (máx 100)
    const limitParam = req.nextUrl.searchParams.get("limit");
    const limit = Math.min(parseInt(limitParam ?? "50"), 100);

    const feed = await queryActivityFeed(holonId, role, limit);
    return NextResponse.json(feed);
  } catch (err) {
    console.error("[/api/holon/[holonId]/feed] Error:", err);
    return NextResponse.json([], { status: 200 }); // Array vacío, no rompe el UI
  }
}
