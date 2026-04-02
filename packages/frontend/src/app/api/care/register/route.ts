// POST /api/care/register
// Registra un acto de cuidado ingresado por texto (Manual Entry en el UI).
//
// Flujo:
//   1. Validar campos del formulario
//   2. Obtener sesión del usuario (opcional — guests pueden proponer)
//   3. Enviar al Tenzo Agent para evaluación con Gemini 2.5 Flash
//   4. Devolver resultado al cliente (razonamiento, HOCA a otorgar, etc.)
//
// Este endpoint reemplaza la llamada directa que tenía care-modal.tsx
// al Cloud Run del Tenzo, centralizando la autenticación y el logging.

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { evaluateCareTask } from "@/lib/server/tenzo-client";
import type { TenzoEvaluationInput } from "@/lib/api/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      descripcion,
      categoria,
      duracion_horas,
      holon_id,
      ubicacion,
    } = body as Partial<TenzoEvaluationInput>;

    // ── Validación básica ──────────────────────────────────────────────────
    if (!descripcion || typeof descripcion !== "string" || descripcion.trim().length < 5) {
      return NextResponse.json(
        { error: "Se requiere una descripción de al menos 5 caracteres" },
        { status: 400 }
      );
    }
    if (!categoria) {
      return NextResponse.json(
        { error: "Se requiere una categoría" },
        { status: 400 }
      );
    }
    const horas = parseFloat(String(duracion_horas));
    if (isNaN(horas) || horas <= 0 || horas > 24) {
      return NextResponse.json(
        { error: "duracion_horas debe ser un número entre 0.5 y 24" },
        { status: 400 }
      );
    }

    // ── Sesión (opcional) ─────────────────────────────────────────────────
    // Guests pueden registrar cuidados; el Tenzo los evalúa igual.
    // La sesión se usa para asociar el task al miembro en Cloud SQL.
    const session = await getServerSession();
    const effectiveHolonId = holon_id ?? session?.holonId ?? "familia-valdez";

    // ── Evaluación Tenzo ──────────────────────────────────────────────────
    const input: TenzoEvaluationInput = {
      descripcion: descripcion.trim(),
      categoria,
      duracion_horas: horas,
      holon_id: effectiveHolonId,
      ...(ubicacion ? { ubicacion } : {}),
    };

    const result = await evaluateCareTask(input);

    // ── Logging (no bloquea la respuesta) ─────────────────────────────────
    if (session) {
      console.info(
        `[/api/care/register] ${session.name} → ${categoria} ${horas}h ` +
          `→ ${result.aprobada ? `✅ ${result.recompensa_hoca} HOCA` : "⏳ apelación"}`
      );
    }

    return NextResponse.json(result);
  } catch (err) {
    console.error("[/api/care/register] Error:", err);

    // Distinguir errores del Tenzo vs errores internos
    const message = err instanceof Error ? err.message : "Error desconocido";
    if (message.includes("Tenzo")) {
      return NextResponse.json(
        { error: `El Tenzo Agent no está disponible: ${message}` },
        { status: 503 }
      );
    }
    return NextResponse.json({ error: "Error interno del servidor" }, { status: 500 });
  }
}
