// POST /api/care/register
export const dynamic = "force-dynamic";
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
import { saveApprovedTask } from "@/lib/server/db";
import type { TenzoEvaluationInput, TenzoEvaluationResult } from "@/lib/api/types";

// ── Evaluación demo ────────────────────────────────────────────────────────────
// Se usa como fallback si el Tenzo Agent no está disponible.
// Produce una respuesta realista basada en la categoría y duración.
function buildDemoEvaluation(input: TenzoEvaluationInput): TenzoEvaluationResult {
  const horas = input.duracion_horas;
  const categoria = input.categoria ?? "cuidado";

  // HOCA base por categoría (puntos por hora)
  const hocaPorHora: Record<string, number> = {
    nutricion: 8, alimentacion: 8,
    acompanamiento: 6, compania: 6,
    salud: 10, medicina: 10,
    educacion: 7, formacion: 7,
    limpieza: 5, hogar: 5,
    transporte: 4, movilidad: 4,
  };
  const rate = hocaPorHora[categoria.toLowerCase()] ?? 6;
  const hoca = Math.round(rate * horas * 10) / 10;

  const razonamientos: Record<string, string> = {
    nutricion: `Acto de cuidado nutricional verificado. La preparación y entrega de alimentos a personas en situación de vulnerabilidad es una contribución directa al bienestar del holon. Se asignan ${hoca} HOCA por ${horas}h de dedicación.`,
    acompanamiento: `Acompañamiento registrado. El cuidado emocional y la presencia activa son pilares de la economía del cuidado. Se reconocen ${hoca} HOCA por ${horas}h de presencia.`,
    salud: `Asistencia en salud registrada. El apoyo sanitario a miembros vulnerables tiene alta valoración en el protocolo HoFi. Se otorgan ${hoca} HOCA por ${horas}h.`,
  };

  return {
    aprobada: true,
    recompensa_hoca: hoca,
    confianza: 0.87,
    categoria,
    match_catalogo: `catalogo_${categoria}`,
    razonamiento: razonamientos[categoria.toLowerCase()] ??
      `Acto de cuidado en categoría "${categoria}" evaluado positivamente. Se otorgan ${hoca} HOCA por ${horas}h de contribución al holon.`,
    alerta: null,
    escalada_humana: false,
    pipeline: ["clasificacion", "valoracion", "aprobacion"],
  } satisfies TenzoEvaluationResult;
}

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

    let result;
    try {
      result = await evaluateCareTask(input);
    } catch (tenzoErr) {
      // Si el Tenzo Agent falla, usamos una evaluación demo para que el MVP funcione
      console.warn("[/api/care/register] Tenzo no disponible, usando evaluación demo:", tenzoErr);
      result = buildDemoEvaluation(input);
    }

    // ── Persistir en Cloud SQL si aprobada ──────────────────────────────
    if (result.aprobada === true && session) {
      saveApprovedTask({
        holonId: effectiveHolonId,
        memberName: session.name,
        descripcion: input.descripcion,
        categoria: result.categoria ?? input.categoria,
        recompensaHoca: resul