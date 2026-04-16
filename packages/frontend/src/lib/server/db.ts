// HoFi Protocol — Helpers de acceso a Cloud SQL (PostgreSQL)
// Solo importar en Route Handlers (nunca en "use client").
//
// Schema real de la tabla tasks (verificado 2026-04-09):
//   id, persona_id, holon_id, descripcion, categoria, recompensa_hoca,
//   aprobada (boolean), created_at, horas, tenzo_score, carbono_kg,
//   gnh_score, gnh_generosidad, gnh_apoyo_social, gnh_calidad_vida, sbt_inscripta
//
// En Cloud Run: conexión por socket Unix (DB_SOCKET_PATH).
// En local:    conexión TCP directa al IP público (DB_HOST=104.198.205.167).

import { Pool, type PoolConfig } from "pg";
import type {
  HolonStats,
  ActivityItem,
  SocialYieldMetric,
  HolonLocation,
  PersonalTransaction,
  ImpactCircle,
  CareCategory,
  UserRole,
} from "@/lib/api/types";

// ─── Pool de conexiones ───────────────────────────────────────────────────────

function buildPoolConfig(): PoolConfig {
  // Cloud Run: socket Unix
  const socketPath = process.env.DB_SOCKET_PATH;
  if (socketPath) {
    return {
      user: process.env.DB_USER ?? "hofi_user",
      password: process.env.DB_PASS,
      database: process.env.DB_NAME ?? "hofi",
      host: socketPath,
    };
  }

  // Local / IP pública: siempre SSL (Cloud SQL requiere SSL en conexiones externas)
  return {
    user: process.env.DB_USER ?? "hofi_user",
    password: process.env.DB_PASS,
    database: process.env.DB_NAME ?? "hofi",
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: parseInt(process.env.DB_PORT ?? "5432"),
    ssl: { rejectUnauthorized: false },
  };
}

/**
 * Normaliza el holonId: "familia-valdez" → "familia-valdes" (como el Tenzo).
 */
function normalizeHolonId(holonId: string): string {
  return holonId.replace("familia-valdez", "familia-valdes");
}

// Singleton del pool
let _pool: Pool | null = null;

function getPool(): Pool {
  if (!_pool) {
    _pool = new Pool(buildPoolConfig());
    _pool.on("error", (err) => {
      console.error("[db] Error inesperado en pool:", err.message);
      _pool = null; // Reset para que el siguiente request reintente
    });
  }
  return _pool;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function query<T extends Record<string, any>>(sql: string, params: unknown[] = []): Promise<T[]> {
  const pool = getPool();
  const { rows } = await pool.query<T>(sql, params);
  return rows;
}

// ─── Holón stats ──────────────────────────────────────────────────────────────

export async function queryHolonStats(holonId: string): Promise<HolonStats> {
  holonId = normalizeHolonId(holonId);
  const rows = await query<{
    total_members: string;
    active_caregivers: string;
    health_score: string;
    weekly_growth: string;
    total_hoca: string;
  }>(
    `SELECT
       COUNT(DISTINCT t.persona_id)                                        AS total_members,
       COUNT(DISTINCT CASE WHEN t.created_at > NOW() - INTERVAL '24h'
                           THEN t.persona_id END)                          AS active_caregivers,
       COALESCE(ROUND(AVG(t.tenzo_score) * 100)::int, 75)                  AS health_score,
       COALESCE(ROUND(
         (COUNT(CASE WHEN t.created_at > NOW() - INTERVAL '7d' THEN 1 END)::numeric /
          NULLIF(COUNT(CASE WHEN t.created_at BETWEEN NOW() - INTERVAL '14d'
                            AND NOW() - INTERVAL '7d' THEN 1 END), 0) - 1) * 100
       ), 0)                                                                AS weekly_growth,
       COALESCE(SUM(t.recompensa_hoca), 0)                                 AS total_hoca
     FROM tasks t
     WHERE t.holon_id = $1 AND t.aprobada = true`,
    [holonId]
  );

  const r = rows[0];
  return {
    holonId,
    totalMembers: parseInt(r?.total_members ?? "0"),
    activeCaregivers: parseInt(r?.active_caregivers ?? "0"),
    health: parseInt(r?.health_score ?? "75"),
    weeklyGrowth: parseFloat(r?.weekly_growth ?? "0"),
    totalHocaDistributed: parseFloat(r?.total_hoca ?? "0"),
  };
}

// ─── Feed de actividad ────────────────────────────────────────────────────────

export async function queryActivityFeed(
  holonId: string,
  role: UserRole,
  limit = 50
): Promise<ActivityItem[]> {
  holonId = normalizeHolonId(holonId);
  const rows = await query<{
    id: string;
    categoria: string;
    recompensa_hoca: number;
    created_at: Date;
    persona_id: string | null;
    descripcion: string | null;
  }>(
    `SELECT id, categoria, recompensa_hoca, created_at, persona_id, descripcion
     FROM tasks
     WHERE holon_id = $1 AND aprobada = true
       AND created_at > NOW() - INTERVAL '30d'
     ORDER BY created_at DESC
     LIMIT $2`,
    [holonId, limit]
  );

  return rows.map((row) => {
    const diffMs = Date.now() - new Date(row.created_at).getTime();
    const diffMin = Math.round(diffMs / 60000);
    const timestamp =
      diffMin < 60
        ? `${diffMin} min ago`
        : `${Math.floor(diffMin / 60)} hour${Math.floor(diffMin / 60) > 1 ? "s" : ""} ago`;

    const base: ActivityItem = {
      id: String(row.id),
      category: mapCategory(row.categoria),
      amount: row.recompensa_hoca ?? 0,
      timestamp,
      exactTime: new Date(row.created_at).toISOString(),
    };

    if (role === "member" || role === "guardian") {
      base.memberAvatar = row.persona_id
        ? row.persona_id.substring(0, 2).toUpperCase()
        : "?";
    }

    if (role === "guardian") {
      base.memberName = row.persona_id ?? "Anónimo";
      base.description = row.descripcion ?? "";
    }

    return base;
  });
}

// ─── Social Yield ─────────────────────────────────────────────────────────────

export async function querySocialYield(holonId: string): Promise<SocialYieldMetric[]> {
  holonId = normalizeHolonId(holonId);
  const rows = await query<{
    total_hoca_week: number;
    total_hoca_prev: number;
    care_acts_week: number;
    care_acts_prev: number;
    active_members_week: number;
    active_members_prev: number;
  }>(
    `SELECT
       COALESCE(SUM(CASE WHEN created_at > NOW() - INTERVAL '7d'
         THEN recompensa_hoca ELSE 0 END), 0)                             AS total_hoca_week,
       COALESCE(SUM(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
         AND NOW() - INTERVAL '7d' THEN recompensa_hoca ELSE 0 END), 0)  AS total_hoca_prev,
       COUNT(CASE WHEN created_at > NOW() - INTERVAL '7d' THEN 1 END)    AS care_acts_week,
       COUNT(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
         AND NOW() - INTERVAL '7d' THEN 1 END)                           AS care_acts_prev,
       COUNT(DISTINCT CASE WHEN created_at > NOW() - INTERVAL '7d'
         THEN persona_id END)                                             AS active_members_week,
       COUNT(DISTINCT CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
         AND NOW() - INTERVAL '7d' THEN persona_id END)                  AS active_members_prev
     FROM tasks
     WHERE holon_id = $1 AND aprobada = true`,
    [holonId]
  );

  const r = rows[0];
  const pct = (curr: number, prev: number) =>
    prev > 0 ? Math.round(((curr - prev) / prev) * 100) : 0;

  return [
    { label: "HOCA distributed", value: Math.round(r?.total_hoca_week ?? 0), unit: "HOCA", change: pct(r?.total_hoca_week ?? 0, r?.total_hoca_prev ?? 0) },
    { label: "Care acts",        value: r?.care_acts_week ?? 0,               unit: "acts",  change: pct(r?.care_acts_week ?? 0, r?.care_acts_prev ?? 0) },
    { label: "Active members",   value: r?.active_members_week ?? 0,          unit: "people", change: pct(r?.active_members_week ?? 0, r?.active_members_prev ?? 0) },
    { label: "Avg per act",      value: r?.care_acts_week > 0 ? Math.round((r.total_hoca_week / r.care_acts_week) * 10) / 10 : 0, unit: "HOCA", change: 0 },
  ];
}

// ─── World holons ─────────────────────────────────────────────────────────────

export async function queryWorldHolons(): Promise<HolonLocation[]> {
  try {
    const rows = await query<{
      holon_id: string;
      total_hoca: number;
      top_category: string;
      members: number;
    }>(
      `SELECT holon_id,
              COALESCE(SUM(recompensa_hoca), 0)                     AS total_hoca,
              MODE() WITHIN GROUP (ORDER BY categoria)              AS top_category,
              COUNT(DISTINCT persona_id)::int                       AS members
       FROM tasks WHERE aprobada = true
       GROUP BY holon_id`,
      []
    );
    if (!rows.length) throw new Error("no data");
    return rows.map((r) => ({
      id: r.holon_id,
      name: r.holon_id,
      city: r.holon_id === "familia-valdes" ? "Buenos Aires, AR" : "Argentina",
      coordinates: [-58.3816, -34.6037] as [number, number],
      activeMembers: r.members,
      totalHocaDistributed: Math.round(r.total_hoca),
      topCategory: mapCategory(r.top_category),
    }));
  } catch {
    return [
      {
        id: "familia-valdes",
        name: "familia-valdes",
        city: "Buenos Aires, AR",
        coordinates: [-58.3816, -34.6037],
        activeMembers: 3,
        totalHocaDistributed: 0,
        topCategory: "caring",
      },
    ];
  }
}

// ─── Transacciones personales ─────────────────────────────────────────────────

export async function queryUserTransactions(
  holonId: string,
  memberName: string,
  limit = 20
): Promise<PersonalTransaction[]> {
  holonId = normalizeHolonId(holonId);
  const rows = await query<{
    id: string;
    categoria: string;
    recompensa_hoca: number;
    descripcion: string;
    created_at: Date;
  }>(
    `SELECT id, categoria, recompensa_hoca, descripcion, created_at
     FROM tasks
     WHERE holon_id = $1 AND persona_id = $2
     ORDER BY created_at DESC
     LIMIT $3`,
    [holonId, memberName, limit]
  );

  return rows.map((row) => {
    const diffMs = Date.now() - new Date(row.created_at).getTime();
    const diffMin = Math.round(diffMs / 60000);
    const timestamp =
      diffMin < 60 ? `${diffMin} min ago`
      : diffMin < 1440 ? `${Math.floor(diffMin / 60)}h ago`
      : `${Math.floor(diffMin / 1440)}d ago`;

    return {
      id: String(row.id),
      type: "earned" as const,
      amount: row.recompensa_hoca ?? 0,
      description: row.descripcion ?? "Care act",
      timestamp,
      exactTime: new Date(row.created_at).toISOString(),
      category: mapCategory(row.categoria),
    };
  });
}

// ─── Balance HOCA ─────────────────────────────────────────────────────────────

export async function queryMemberBalance(holonId: string, memberName: string): Promise<number> {
  holonId = normalizeHolonId(holonId);
  const rows = await query<{ total: number }>(
    `SELECT COALESCE(SUM(recompensa_hoca), 0) AS total
     FROM tasks
     WHERE holon_id = $1 AND persona_id = $2 AND aprobada = true`,
    [holonId, memberName]
  );
  return Math.round(rows[0]?.total ?? 0);
}

// ─── Guardar tarea aprobada ───────────────────────────────────────────────────

export interface SaveTaskInput {
  holonId: string;
  memberName: string;         // Guardado en persona_id (nombre del login)
  descripcion: string;
  categoria: string;
  recompensaHoca: number;
  confianza: number;          // Se guarda en tenzo_score
  horasValidadas?: number;    // → horas
  carbonoKg?: number;
  gnhGenerosidad?: number;
  gnhApoyoSocial?: number;
  gnhCalidadVida?: number;
  tenzoScore?: number;
}

export async function saveApprovedTask(input: SaveTaskInput): Promise<void> {
  const holonId = normalizeHolonId(input.holonId);
  const gnhScore = input.gnhGenerosidad != null
    ? ((input.gnhGenerosidad ?? 0) + (input.gnhApoyoSocial ?? 0) + (input.gnhCalidadVida ?? 0)) / 3
    : null;

  await query(
    `INSERT INTO tasks
       (persona_id, holon_id, descripcion, categoria, recompensa_hoca,
        aprobada, horas, carbono_kg,
        gnh_generosidad, gnh_apoyo_social, gnh_calidad_vida, gnh_score,
        tenzo_score, created_at)
     VALUES ($1, $2, $3, $4, $5, true, $6, $7, $8, $9, $10, $11, $12, NOW())`,
    [
      input.memberName,
      holonId,
      input.descripcion,
      input.categoria,
      input.recompensaHoca,
      input.horasValidadas ?? null,
      input.carbonoKg ?? null,
      input.gnhGenerosidad ?? null,
      input.gnhApoyoSocial ?? null,
      input.gnhCalidadVida ?? null,
      gnhScore,
      input.tenzoScore ?? input.confianza ?? null,
    ]
  );
}

// ─── Impact Circles ───────────────────────────────────────────────────────────

export async function queryImpactCircles(
  holonId: string,
  memberName?: string
): Promise<ImpactCircle[]> {
  holonId = normalizeHolonId(holonId);

  const memberFilter = memberName ? "AND persona_id = $2" : "";
  const params: unknown[] = memberName ? [holonId, memberName] : [holonId];

  const rows = await query<{
    co2_this_week:  number;
    co2_last_week:  number;
    co2_all_time:   number;
    gnh_this_week:  number;
    gnh_last_week:  number;
    gnh_all_time:   number;
    cci_this_week:  number;
    cci_last_week:  number;
    cci_all_time:   number;
  }>(
    `SELECT
       COALESCE(SUM(CASE WHEN created_at > NOW() - INTERVAL '7d'  THEN carbono_kg ELSE 0 END), 0) AS co2_this_week,
       COALESCE(SUM(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d' AND NOW() - INTERVAL '7d' THEN carbono_kg ELSE 0 END), 0) AS co2_last_week,
       COALESCE(SUM(carbono_kg), 0)                                                                AS co2_all_time,
       COALESCE(AVG(CASE WHEN created_at > NOW() - INTERVAL '7d'  THEN gnh_score END), 0)         AS gnh_this_week,
       COALESCE(AVG(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d' AND NOW() - INTERVAL '7d' THEN gnh_score END), 0) AS gnh_last_week,
       COALESCE(AVG(gnh_score), 0)                                                                 AS gnh_all_time,
       COALESCE(SUM(CASE WHEN created_at > NOW() - INTERVAL '7d'  THEN horas ELSE 0 END), 0)      AS cci_this_week,
       COALESCE(SUM(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d' AND NOW() - INTERVAL '7d' THEN horas ELSE 0 END), 0) AS cci_last_week,
       COALESCE(SUM(horas), 0)                                                                     AS cci_all_time
     FROM tasks
     WHERE holon_id = $1 AND aprobada = true ${memberFilter}`,
    params
  );

  const r = rows[0];
  const scope = memberName ? "personal" : "holon";

  return [
    {
      id: "co2",
      unit: "kg CO₂",
      thisWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.co2_this_week ?? 0) * 10) / 10 },
      lastWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.co2_last_week ?? 0) * 10) / 10 },
      allTime:  { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.co2_all_time  ?? 0) * 10) / 10 },
    },
    {
      id: "gnh",
      unit: "GNH pts",
      thisWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.gnh_this_week ?? 0) * 100) / 100 },
      lastWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.gnh_last_week ?? 0) * 100) / 100 },
      allTime:  { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.gnh_all_time  ?? 0) * 100) / 100 },
    },
    {
      id: "cci",
      unit: "hrs",
      thisWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.cci_this_week ?? 0) * 10) / 10 },
      lastWeek: { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.cci_last_week ?? 0) * 10) / 10 },
      allTime:  { personal: 0, holon: 0, world: 0, [scope]: Math.round((r?.cci_all_time  ?? 0) * 10) / 10 },
    },
  ];
}

// ─── Helpers internos ─────────────────────────────────────────────────────────

function mapCategory(cat: string | null | undefined): CareCategory {
  const map: Record<string, CareCategory> = {
    gardening:    "gardening",
    cooking:      "cooking",
    teaching:     "teaching",
    healing:      "healing",
    building:     "building",
    caring:       "caring",
    animals:      "animals",
    land:         "land",
    resources:    "resources",
    // Aliases del Tenzo Agent (español → CareCategory)
    nutricion:    "cooking",
    alimentacion: "cooking",
    acompanamiento: "caring",
    compania:     "caring",
    salud:        "healing",
    medicina:     "healing",
    educacion:    "teaching",
    formacion:    "teaching",
    limpieza:     "building",
    hogar:        "building",
    transporte:   "resources",
    movilidad:    "resources",
    cuidado:      "caring",
  };
  return map[(cat ?? "").toLowerCase()] ?? "caring";
}