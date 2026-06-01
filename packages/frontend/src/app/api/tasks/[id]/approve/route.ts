// POST /api/tasks/[id]/approve
// Proxy al Tenzo Agent: registra el voto del usuario autenticado en una tarea
// con approval_state='pending_community'.
// Requiere autenticación.

import { NextResponse } from "next/server";
import { getTenzoToken } from "@/lib/server/tenzo-client";
import { getServerSession } from "@/lib/server/auth";
import { canonicalPersonId } from "@/lib/server/canonical";

const TENZO_BASE =
  process.env.TENZO_AGENT_URL ??
  "https://hofi-tenzo-277171732954.us-central1.run.app";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const session = await getServerSession();

    if (!session) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const token = await getTenzoToken();
    const voterPersonaId = canonicalPersonId(session.name);

    const res = await fetch(`${TENZO_BASE}/tasks/${id}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ voter_persona_id: voterPersonaId }),
    });

    const body = await res.text();
    if (!res.ok) {
      console.error(`[tasks/approve] Tenzo ${res.status}:`, body);
      return NextResponse.json({ error: body }, { status: res.status });
    }

    try {
      return NextResponse.json(JSON.parse(body));
    } catch {
      return NextResponse.json({ ok: true });
    }
  } catch (err) {
    console.error("[tasks/approve] Error:", err);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
