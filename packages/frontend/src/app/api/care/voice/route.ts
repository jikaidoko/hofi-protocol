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

    // ── Proxy al Tenzo Agent ──────────────────────────────────────────────
    const token = await getTenzoToken();

    // Construir FormData para el Tenzo
    const tenzoForm = new FormData();
    tenzoForm.append("audio", audioFile, "care.webm");
    tenzoForm.append("holon_id", holonId);
    if (session?.name) tenzoForm.append("member_name", session.name);

    // Intentar endpoint de voz primero; fallback al endpoint de texto si no existe
    let tenzoRes = await fetch(`${TENZO_BASE}/evaluar-voz`, {
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
