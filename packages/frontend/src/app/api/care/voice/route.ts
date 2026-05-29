// POST /api/care/voice
// Registra un acto de cuidado por voz (Voice Register en el UI).
//
// Flujo:
//   1. Recibe audio webm del browser (grabado con MediaRecorder)
//   2. Lo reenvía al Tenzo Agent que:
//      a. Transcribe con Whisper
//      b. Parsea la actividad con task_parser.py
//      c. Evalúa con Gemini 2.5 Flash
//   3. Devuelve resultado al cliente
//
// Requiere que el Tenzo Agent tenga un endpoint /evaluar-voz o similar.
// Por ahora proxea al endpoint estándar si no existe el de voz.

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "@/lib/server/auth";
import { getTenzoToken } from "@/lib/server/tenzo-client";
import { saveApprovedTask } from "@/lib/server/db";
import { canonicalPersonId } from "@/lib/server/canonical";

const TENZO_BASE =
  process.env.TENZO_AGENT_URL ??
  "https://hofi-tenzo-277171732954.us-central1.run.app";

export async function POST(req: NextRequest) {
  try {
    // ── Validar que hay audio ──────────────────────────────────────────────
    const formData = await req.formData();
    const audioFile = formData.get("audio");

    if (!audioFile || !(audioFile instanceof Blob)) {
      return NextResponse.json(
        { error: "Se requiere campo 'audio' como Blob" },
        { status: 400 }
      );
    }

    // ── Sesión del usuario ────────────────────────────────────────────────
    const session = await getServerSession();
    const holonId = session?.holonId ?? "familia-mourino";

    // Persona canónica: derivada igual que en /api/care/register para que
    // el bucket en tasks.persona_id coincida con el del bot de Telegram y
    // del manual entry. Si no hay sesión, queda vacío y la tarea no persiste.
    const personaId =
      canonicalPersonId(session?.userId) ||
      canonicalPersonId(session?.name) ||
      "";

    // ── Proxy al Tenzo Agent ──────────────────────────────────────────────
    const token = await getTenzoToken();

    // Construir FormData para el Tenzo
    const tenzoForm = new FormData();
    tenzoForm.append("audio", audioFile, "care.webm");
    tenzoForm.append("holon_id", holonId);
    if (session?.name) tenzoForm.append("member_name", session.name);
    if (personaId) tenzoForm.append("persona_id", personaId);

    // Intentar endpoint de voz primero; fallback al endpoint de texto si no existe
    const tenzoRes = await fetch(`${TENZO_BASE}/evaluar-voz`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: tenzoForm,
    });

    // Si el endpoint de voz no existe (404), informar al cliente
    if (tenzoRes.status === 404) {
      return NextResponse.json(
        {
          error:
            "El endpoint /evaluar-voz no está implementado en el Tenzo Agent. " +
            "Por favor agrega este endpoint en packages/tenzo-agent/tenzo_agent.py",
        },
        { status: 501 }
      );
    }

    if (!tenzoRes.ok) {
      const text = await tenzoRes.text();
      return NextResponse.json(
        { error: `Tenzo error ${tenzoRes.status}: ${text}` },
        { status: 502 }
      );
    }

    const result = await tenzoRes.json();

    // ── Clasificación del veredicto del Tenzo ─────────────────────────────
    // Tres casos posibles, semántica unificada con /api/care/register:
    //   - aprobada=true   → aprobada por Tenzo (confianza alta o consenso ISC)
    //   - aprobada=null   → escalada a community approval (HOCA pendientes)
    //   - aprobada=false  → rechazada
    // El Tenzo Cloud Run sólo persiste el caso aprobada=true (en su pipeline).
    // Las escaladas y rechazadas las maneja el frontend.
    const aprobadaRaw = result.aprobada;
    const hocaPropuesta = typeof result.recompensa_hoca === "number"
      ? result.recompensa_hoca
      : 0;
    const isApproved = aprobadaRaw === true && hocaPropuesta > 0;
    const isPendingReview =
      !isApproved &&
      aprobadaRaw !== false &&
      hocaPropuesta > 0; // escalada con HOCA propuesta

    console.info(
      `[/api/care/voice] Tenzo verdict → aprobada=${aprobadaRaw} hoca=${hocaPropuesta} ` +
        `→ ${isApproved ? "approved" : isPendingReview ? "pending_review" : "declined"} ` +
        `| user=${session?.name ?? "guest"} persona=${personaId || "n/a"}`
    );
    // Diagnóstico extendido: por qué Tenzo decidió esto.
    // Útil para entender si la descripción transcrita por Whisper matchea
    // con el catálogo del holón y con qué confianza Gemini la evaluó.
    console.info(
      "[/api/care/voice] Tenzo detail → " +
        JSON.stringify({
          transcripcion: result.transcripcion?.slice(0, 120),
          language_probability: result.language_probability,
          categoria: result.categoria,
          confianza: result.confianza,
          match_catalogo: result.match_catalogo,
          escalada_humana: result.escalada_humana,
          horas_validadas: result.horas_validadas,
          razonamiento: result.razonamiento?.slice(0, 200),
          pipeline: Array.isArray(result.pipeline)
            ? result.pipeline.map((p: { capa?: string; aprobada?: unknown; confianza?: number; match?: string }) => ({
                capa: p.capa,
                aprobada: p.aprobada,
                confianza: p.confianza,
                match: p.match,
              }))
            : result.pipeline,
        })
    );

    // ── Persistencia en Cloud SQL ─────────────────────────────────────────
    // Single source de verdad por caso:
    //   - Approved → SOLO el Tenzo persiste (en su pipeline interno).
    //     El frontend NO duplica.
    //   - Pending  → SOLO el frontend persiste con aprobada=NULL.
    //     El Tenzo no persiste estas (oracle.aprobada is None).
    //   - Declined → nadie persiste.
    //
    // Hacemos await (no fire-and-forget) para que el GET de transactions
    // que viene del cliente post-response vea la row recién insertada.
    if (isPendingReview && session) {
      try {
        await saveApprovedTask({
          holonId,
          personaId: personaId || session.name,
          memberName: session.name,
          descripcion:
            (result.transcripcion as string) ||
            (result.descripcion as string) ||
            "Acto de cuidado por voz",
          categoria: result.categoria ?? "cuidado",
          recompensaHoca: hocaPropuesta,
          confianza: result.confianza ?? 0.8,
          horasValidadas: result.horas_validadas,
          carbonoKg: result.carbono_kg,
          gnhGenerosidad: result.gnh?.generosidad,
          gnhApoyoSocial: result.gnh?.apoyo_social,
          gnhCalidadVida: result.gnh?.calidad_de_vida,
          tenzoScore: result.tenzo_score ?? result.confianza,
          aprobada: null, // pending review
        });
        console.info(
          `[/api/care/voice] ⏳ pending persisted ${hocaPropuesta} HOCA → ` +
            `${personaId || session.name} (${holonId})`
        );
      } catch (dbErr) {
        console.error("[/api/care/voice] DB save error (pending):", dbErr);
      }
    } else if (isApproved) {
      console.info(`[/api/care/voice] approved → Tenzo persiste (no dup)`);
    } else if (!session) {
      console.warn(`[/api/care/voice] NO persiste — sin sesión`);
    }

    return NextResponse.json(result);
  } catch (err) {
    console.error("[/api/care/voice] Error:", err);
    return NextResponse.json({ error: "Error interno del servidor" }, { status: 500 });
  }
}
