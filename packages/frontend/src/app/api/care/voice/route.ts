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
  "https://hofi-tenzo-1080243330445.us-central1.run.app";

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

    // ── Persistir en Cloud SQL si aprobada ──────────────────────────────
    // CRÍTICO: el Tenzo intenta persistir desde su propio pipeline pero
    // su conexión a Cloud SQL viene fallando (OperationalError persistente).
    // Replicamos el patrón de /api/care/register: el frontend escribe
    // directo desde su pool, que sí está sano.
    if (result.aprobada === true && session) {
      saveApprovedTask({
        holonId,
        personaId: personaId || session.name,
        memberName: session.name,
        descripcion:
          (result.transcripcion as string) ||
          (result.descripcion as string) ||
          "Acto de cuidado por voz",
        categoria: result.categoria ?? "cuidado",
        recompensaHoca: result.recompensa_hoca ?? 0,
        confianza: result.confianza ?? 0.8,
        horasValidadas: result.horas_validadas,
        carbonoKg: result.carbono_kg,
        gnhGenerosidad: result.gnh?.generosidad,
        gnhApoyoSocial: result.gnh?.apoyo_social,
        gnhCalidadVida: result.gnh?.calidad_de_vida,
        tenzoScore: result.tenzo_score ?? result.confianza,
      }).catch((dbErr) => {
        // No bloquear la respuesta si falla la persistencia.
        console.error("[/api/care/voice] DB save error:", dbErr);
      });
    }

    console.info(
      `[/api/care/voice] ${session?.name ?? "guest"} → voz ` +
        `→ ${result.aprobada ? `✅ ${result.recompensa_hoca} HOCA` : "⏳ procesando"}`
    );

    return NextResponse.json(result);
  } catch (err) {
    console.error("[/api/care/voice] Error:", err);
    return NextResponse.json({ error: "Error interno del servidor" }, { status: 500 });
  }
}
