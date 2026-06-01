// GET /api/holon/[holonId]/tasks/pending
// Proxy al Tenzo Agent: lista las tareas con approval_state='pending_community'
// y las reglas del holón (quorum, espíritu).
// Requiere autenticación — solo miembros del holón pueden ver y votar.

import { NextResponse } from "next/server";
import { getTenzoToken } from "@/lib/server/tenzo-client";
import { getServerSession } from "@/lib/server/auth";
import { canonicalPersonId } from "@/lib/server/canonical";
import type { PendingTask, HolonApprovalRules } from "@/components/hofi/community-approval-modal";

const TENZO_BASE =
  process.env.TENZO_AGENT_URL ??
  "https://hofi-tenzo-277171732954.us-central1.run.app";

function relativeTime(dateStr: string): string {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} hour${diffH > 1 ? "s" : ""} ago`;
  return `${Math.floor(diffH / 24)} day${Math.floor(diffH / 24) > 1 ? "s" : ""} ago`;
}

function mapCategory(raw: string): string {
  const map: Record<string, string> = {
    jardineria: "gardening", jardinería: "gardening", cuidado_ecologico: "gardening",
    cocina_comunitaria: "cooking", cocina_comunal: "cooking", cocina: "cooking",
    taller_educativo: "teaching", educacion: "teaching",
    salud_comunitaria: "healing", salud: "healing",
    mantenimiento: "building", construccion: "building",
    cuidado_humano: "caring", cuidado_ninos: "caring", cuidado: "caring",
    animales: "animals", tierra: "land", recursos: "resources",
  };
  return map[raw?.toLowerCase()] ?? raw ?? "caring";
}

const DEFAULT_RULES: HolonApprovalRules = {
  holonName: "Familia Mouriño",
  requiredApprovals: 2,
  totalMembers: 5,
  spirit: "In our holon, caring is the yield. Each member's voice recognizes the invisible work that sustains our community.",
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ holonId: string }> }
) {
  try {
    const { holonId } = await params;
    const session = await getServerSession();

    if (!session) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const token = await getTenzoToken();
    const currentPersonaId = canonicalPersonId(session.name);

    const [tasksRes, rulesRes] = await Promise.all([
      fetch(`${TENZO_BASE}/holons/${holonId}/tasks/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${TENZO_BASE}/holons/${holonId}/rules`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ]);

    // ── Pending tasks ──────────────────────────────────────────────────────────
    let pendingTasks: PendingTask[] = [];
    if (tasksRes.ok) {
      const data = await tasksRes.json();
      const tasks = Array.isArray(data) ? data : (data.tasks ?? []);

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      pendingTasks = tasks.map((t: any) => {
        const taskApprovals: Array<{ voter_persona_id: string; voted_at?: string }> =
          Array.isArray(t.approvals) ? t.approvals : [];

        const myVote: "approved" | "none" = taskApprovals.some(
          (a) => a.voter_persona_id === currentPersonaId
        ) ? "approved" : "none";

        return {
          id: String(t.id),
          description: String(t.descripcion ?? ""),
          memberName: String(t.persona_id ?? "Member"),
          memberAvatar: String(t.persona_id ?? "ME").substring(0, 2).toUpperCase(),
          category: mapCategory(String(t.categoria ?? "")),
          duration: Number(t.horas ?? 1),
          tenzoConfidence: Number(t.tenzo_score ?? 0.6),
          tenzoReasoning: String(t.tenzo_reasoning ?? "Task submitted for community review."),
          suggestedReward: Number(t.recompensa_hoca ?? 0),
          submittedAt: t.created_at ? relativeTime(String(t.created_at)) : "recently",
          approvalsRequired: Number(t.approvals_required ?? DEFAULT_RULES.requiredApprovals),
          approvals: taskApprovals.map((a) => ({
            memberName: String(a.voter_persona_id ?? "Member"),
            memberAvatar: String(a.voter_persona_id ?? "ME").substring(0, 2).toUpperCase(),
            approvedAt: a.voted_at ? relativeTime(String(a.voted_at)) : "recently",
          })),
          myVote,
        } satisfies PendingTask;
      });
    }

    // ── Holon rules ────────────────────────────────────────────────────────────
    let holonRules = DEFAULT_RULES;
    if (rulesRes.ok) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rules = await rulesRes.json() as any;
      holonRules = {
        holonName: rules.holon_name ?? DEFAULT_RULES.holonName,
        requiredApprovals: rules.quorum ?? DEFAULT_RULES.requiredApprovals,
        totalMembers: rules.total_members ?? DEFAULT_RULES.totalMembers,
        spirit: rules.spirit ?? DEFAULT_RULES.spirit,
      };
    }

    return NextResponse.json({ pendingTasks, holonRules });
  } catch (err) {
    console.error("[tasks/pending] Error:", err);
    return NextResponse.json({ pendingTasks: [], holonRules: DEFAULT_RULES });
  }
}
