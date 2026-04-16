// GET /api/holon/[holonId]/yield
// Métricas de rendimiento social del holón (Social Yield).
// Alimenta las tarjetas de métricas en HolonView.
//
// Compara últimos 7 días vs los 7 anteriores para calcular tendencia.

import { NextRequest, NextResponse } from "next/server";
import { querySocialYield } from "@/lib/server/db";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ holonId: string }> }
) {
  try {
    const { holonId } = await params;
    const metrics = await querySocialYield(holonId);
    return NextResponse.json(metrics);
  } catch (err) {
    console.error("[/api/holon/[holonId]/yield] Error:", err);
    // Fallback con valores neutros
    return NextResponse.json([
      { label: "HOCA distributed", value: 0, unit: "HOCA", change: 0 },
      { label: "Care acts",        value: 0, unit: "acts",  change: 0 },
      { label: "Active members",   value: 0, unit: "people", change: 0 },
      { label: "Avg per act",      value: 0, unit: "HOCA",  change: 0 },
    ]);
  }
}
