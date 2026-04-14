// GET /api/holon/[holonId]
// Estadísticas generales de un holón: miembros, caregivers activos,
// health score, crecimiento semanal y HOCA distribuidas.
// Alimenta la CommunityOrb y las métricas del header.

import { NextRequest, NextResponse } from "next/server";
import { queryHolonStats } from "@/lib/server/db";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ holonId: string }> }
) {
  try {
    const { holonId } = await params;

    if (!holonId || holonId.length > 100) {
      return NextResponse.json({ error: "holonId inválido" }, { status: 400 });
    }

    const stats = await queryHolonStats(holonId);
    return NextResponse.json(stats);
  } catch (err) {
    console.error("[/api/holon/[holonId]] Error:", err);
    // Devolver stats mínimos en lugar de 500 para no romper el UI
    return NextResponse.json({
      holonId: "familia-valdes",
      totalMembers: 0,
      activeCaregivers: 0,
      health: 75,
      weeklyGrowth: 0,
      totalH