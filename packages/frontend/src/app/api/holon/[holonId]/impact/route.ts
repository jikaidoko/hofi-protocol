// GET /api/holon/[holonId]/impact
// Datos para las tres órbitas de impacto: CO₂ evitado, GNH, CCI (horas).
// Acepta ?member=<nombre> para filtrar por persona (tab Presence).
// Sin ?member → estadísticas del holón completo (tab Holon).

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { queryImpactCircles } from "@/lib/server/db";
import { MOCK_IMPACT_CIRCLES } from "@/lib/mock-data";

export const revalidate = 60;

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ holonId: string }> }
) {
  try {
    const { holonId } = await params;
    const session = await getServerSession();

    // Si se pide scope personal, filtrar por el miembro autenticado
    const memberParam = req.nextUrl.searchParams.get("member");
    const memberName = memberParam ?? (session?.name);

    const scope = req.nextUrl.searchParams.get("scope") ?? "holon";
    const nameFilter = scope === "personal" ? memberName : undefined;

    const circles = await queryImpactCircles(holonId, nameFilter);
    return NextResponse.json(circles);
  } catch (err) {
    console.error("[/api/holon/[holonId]/impact] Error:", err);
    // Fallback con mock para no romper el UI
    return NextResponse.json(MOCK_IMPACT_CIRCLES, { status: 200 });
  }
}
