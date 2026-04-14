// GET /api/world/holons
// Lista de todos los holones con sus coordenadas geográficas y métricas.
// Alimenta el WorldView (mapa Mapbox con clusters).
//
// Cache agresivo (5 min): la distribución geográfica de holones
// no cambia frecuentemente.

import { NextResponse } from "next/server";
import { queryWorldHolons } from "@/lib/server/db";

// force-dynamic: evita que Next.js intente conectar a Cloud SQL durante el build.
// El cache de 5 min se maneja a nivel de CDN (Vercel Edge) o se reactiva
// cuando Cloud SQL esté disponible en el entorno de ejecución.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const holons = await queryWorldHolons();
    return NextResponse.json(holons);
  } catch (err) {
    console.error("[/api/world/holons] Error:", err);
    // Fallback: holón piloto familia-valdez
    return NextResponse.json([
      {
        id: "familia-valdez",
        name: "familia-valdez",
        city: "Buenos Aires, AR",
        coordinates: [-58.3816, -34.6037],
        activeMembers: 3,
        totalHocaDistributed: 0,
        topCategory: "caring",
      },
    ]);
  }
}
