// POST /api/auth/voice
// Autenticación biométrica de voz para el frontend web.
//
// Flujo:
//   1. Browser envía audio (webm/ogg) como multipart/form-data
//   2. Este handler lo reenvía al servicio de biometría (VOICE_AUTH_URL)
//      — que es el mismo motor de voz que usa el bot de Telegram —
//   3. Si el servicio valida la huella vocal, generamos un JWT de sesión
//      y lo ponemos en una cookie httpOnly
//   4. Devolvemos la sesión al cliente (sin el token, que es httpOnly)

import { NextRequest, NextResponse } from "next/server";
import { verifyVoicePrint } from "@/lib/server/tenzo-client";
import {
  signSessionToken,
  sessionCookieOptions,
} from "@/lib/server/auth";
import type { UserRole, UserSession } from "@/lib/api/types";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const audioFile = formData.get("audio");
    const nameClaim = formData.get("name")?.toString();

    if (!audioFile || !(audioFile instanceof Blob)) {
      return NextResponse.json(
        { error: "Se requiere campo 'audio' como Blob" },
        { status: 400 }
      );
    }

    // Convertir Blob → Buffer para enviarlo al servicio de biometría
    const arrayBuffer = await audioFile.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // Llamar al servicio de voice biometrics
    const voiceResult = await verifyVoicePrint(buffer, nameClaim);

    if (!voiceResult || !voiceResult.authenticated) {
      return NextResponse.json(
        {
          authenticated: false,
          error: voiceResult
            ? "Voz no reconocida — umbral de similitud no alcanzado"
            : "Servicio de biometría de voz no configurado (VOICE_AUTH_URL)",
        },
        { status: 401 }
      );
    }

    // Construir sesión de usuario. `personId` es la clave canónica — la misma
    // con la que el bot escribe tasks.persona_id, así el balance y el feed
    // personal quedan consistentes en ambos canales.
    const session: UserSession = {
      userId: voiceResult.personId ?? `voice_${Date.now()}`,
      name: voiceResult.name ?? nameClaim ?? "Miembro",
      role: (voiceResult.role as UserRole) ?? "member",
      holonId: voiceResult.holonId ?? "familia-valdes",
      balance: 0, // Se carga por separado desde Cloud SQL / on-chain
      avatar: (voiceResult.name ?? nameClaim ?? "??")
        .substring(0, 2)
        .toUpperCase(),
    };

    // Firmar JWT y ponerlo en cookie httpOnly
    const token = await signSessionToken(session);
    const cookieOpts = sessionCookieOptions(token);

    const response = NextResponse.json({
      authenticated: true,
      session,
      confidence: voiceResult.confidence,
    });

    response.cookies.set(cookieOpts);
    return response;
  } catch (err) {
    console.error("[/api/auth/voice] Error:", err);
    return NextResponse.json(
      { error: "Error interno del servidor" },
      { status: 500 }
    );
  }
}
