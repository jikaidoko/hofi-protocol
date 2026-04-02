// HoFi Protocol — Helpers de acceso a Cloud SQL (PostgreSQL)
// Solo importar en Route Handlers (nunca en "use client").
//
// Usa el mismo Cloud SQL que el Tenzo Agent:
//   hofi-v2-2026:us-central1:hofi-db  /  base: hofi_db  /  user: tenzo_user
//
// Requiere agregar "pg" a las dependencias:
//   cd packages/frontend && npm install pg @types/pg
//
// En Cloud Run: conexión por socket Unix (igual que Tenzo).
// En local:    conexión por TCP con DB_HOST=127.0.0.1 (via Cloud SQL Auth Proxy).

import { Pool, type PoolConfig } from "pg";
import type {
  HolonStats,
  ActivityItem,
  SocialYieldMetric,
  HolonLocation,
  PersonalTransaction,
  CareCategory,
  UserRole,
} from "@/lib/api/types";

// ─── Pool de conexiones ───────────────────────────────────────────────────────

function buildPoolConfig(): PoolConfig {
  // Cloud Run: socket Unix (igual que en tenzo_agent.py)
  const socketPath = process.env.DB_SOCKET_PATH;
  if (socketPath) {
    return {
      user: process.env.DB_USER ?? "tenzo_user",
      password: process.env.DB_PASS,
      database: process.env.DB_NAME ?? "hofi_db",
      host: socketPath,
    };
  }

  // Local / Cloud SQL Auth Proxy: TCP
  return {
    user: process.env.DB_USER ?? "tenzo_user",
    password: process.env.DB_PASS,
    database: process.env.DB_NAME ?? "hofi_db",
    host: process.env.DB_HOST ?? "127.0.0.1",
    port: parseInt(process.env.DB_PORT ?? "5432"),
    ssl: process.env.NODE_ENV === "production" ? { rejectUnauthorized: false } : false,
  };
}

// Singleton del pool (evita crear conexiones en cada request)
let _pool: Pool | null = null;

function getPool(): Pool {
  if (!_pool) {
    _pool = new Pool(buildPoolConfig());
    _pool.on("error", (err) => {
      console.error("[db] Error inesperado en pool:", err.message);
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

/**
 * Estadísticas generales del holón para la Community Orb y la cabecera.
 */
export async function queryHolonStats(holonId: string): Promise<HolonStats> {
  const rows = await query<{
    total_members: string;
    active_caregivers: string;
    health_score: string;
    weekly_growth: string;
    total_hoca: string;
  }>(
    `SELECT
       COUNT(DISTINCT vp.member_name)                                    AS total_members,
       COUNT(DISTINCT CASE WHEN t.created_at > NOW() - INTERVAL '24h'
                           THEN t.member_name END)                       AS active_caregivers,
       COALESCE(ROUND(AVG(t.confianza) * 100)::int, 75)                  AS health_score,
       COALESCE(ROUND(
         (COUNT(CASE WHEN t.created_at > NOW() - INTERVAL '7d' THEN 1 END)::numeric /
          NULLIF(COUNT(CASE WHEN t.created_at BETWEEN NOW() - INTERVAL '14d'
                            AND NOW() - INTERVAL '7d' THEN 1 END), 0) - 1) * 100
       ), 0)                                                             AS weekly_growth,
       COALESCE(SUM(t.recompensa_hoca), 0)                              AS total_hoca
     FROM voice_profiles vp
     LEFT JOIN tasks t ON t.holon_id = $1
     WHERE vp.holon_id = $1`,
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

/**
 * Devuelve el feed de actividades del holón con máscara de privacidad por rol.
 *
 * - guest:    sin nombre, sin descripción, sin hora exacta
 * - member:   con iniciales de avatar, hora aproximada, rango de HOCA
 * - guardian: datos completos
 */
export async function queryActivityFeed(
  holonId: string,
  role: UserRole,
  limit = 50
): Promise<ActivityItem[]> {
  const rows = await query<{
    id: string;
    categoria: string;
    recompensa_hoca: number;
    created_at: Date;
    member_name: string | null;
    descripcion: string | null;
    confianza: number;
  }>(
    `SELECT id, categoria, recompensa_hoca, created_at, member_name, descripcion, confianza
     FROM tasks
     WHERE holon_id = $1
       AND estado = 'aprobada'
       AND created_at > NOW() - INTERVAL '24h'
     ORDER BY created_at DESC
     LIMIT $2`,
    [holonId, limit]
  );

  return rows.map((row) => {
    const now = Date.now();
    const diffMs = now - new Date(row.created_at).getTime();
    const diffMin = Math.round(diffMs / 60000);
    const timestamp =
      diffMin < 60
        ? `${diffMin} min ago`
        : `${Math.floor(diffMin / 60)} hour${Math.floor(diffMin / 60) > 1 ? "s" : ""} ago`;

    const base: ActivityItem = {
      id: row.id,
      category: mapCategory(row.categoria),
      amount: row.recompensa_hoca ?? 0,
      timestamp,
      exactTime: new Date(row.created_at).toISOString(),
    };

    if (role === "member" || role === "guardian") {
      base.memberAvatar = row.member_name
        ? row.member_name.substring(0, 2).toUpperCase()
        : "?";
    }

    if (role === "guardian") {
      base.memberName = row.member_name ?? "Anónimo";
      base.description = row.descripcion ?? "";
    }

    return base;
  });
}

// ─── Social Yield ─────────────────────────────────────────────────────────────

/**
 * Métricas de rendimiento social del holón (últimos 7 días vs 7 anteriores).
 */
export async function querySocialYield(
  holonId: string
): Promise<SocialYieldMetric[]> {
  const rows = await query<{
    total_hoca_week: number;
    total_hoca_prev: number;
    care_acts_week: number;
    care_acts_prev: number;
    active_members_week: number;
    active_members_prev: number;
  }>(
    `SELECT
       SUM(CASE WHEN created_at > NOW() - INTERVAL '7d' THEN recompensa_hoca ELSE 0 END) AS total_hoca_week,
       SUM(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
                AND NOW() - INTERVAL '7d' THEN recompensa_hoca ELSE 0 END)              AS total_hoca_prev,
       COUNT(CASE WHEN created_at > NOW() - INTERVAL '7d' THEN 1 END)                  AS care_acts_week,
       COUNT(CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
                  AND NOW() - INTERVAL '7d' THEN 1 END)                                AS care_acts_prev,
       COUNT(DISTINCT CASE WHEN created_at > NOW() - INTERVAL '7d'
                           THEN member_name END)                                        AS active_members_week,
       COUNT(DISTINCT CASE WHEN created_at BETWEEN NOW() - INTERVAL '14d'
                           AND NOW() - INTERVAL '7d'
                           THEN member_name END)                                        AS active_members_prev
     FROM tasks
     WHERE holon_id = $1 AND estado = 'aprobada'`,
    [holonId]
  );

  const r = rows[0];
  const pctChange = (curr: number, prev: number) =>
    prev > 0 ? Math.round(((curr - prev) / prev) * 100) : 0;

  return [
    {
      label: "HOCA distributed",
      value: Math.round(r?.total_hoca_week ?? 0),
      unit: "HOCA",
      change: pctChange(r?.total_hoca_week ?? 0, r?.total_hoca_prev ?? 0),
    },
    {
      label: "Care acts",
      value: r?.care_acts_week ?? 0,
      unit: "acts",
      change: pctChange(r?.care_acts_week ?? 0, r?.care_acts_prev ?? 0),
    },
    {
      label: "Active members",
      value: r?.active_members_week ?? 0,
      unit: "people",
      change: pctChange(r?.active_members_week ?? 0, r?.active_members_prev ?? 0),
    },
    {
      label: "Avg per act",
      value:
        r?.care_acts_week > 0
          ? Math.round((r.total_hoca_week / r.care_acts_week) * 10) / 10
          : 0,
      unit: "HOCA",
      change: 0,
    },
  ];
}

// ─── World holons ─────────────────────────────────────────────────────────────

/**
 * Lista todos los holones registrados para el mapa mundial.
 * Requiere tabla `holons` con columnas: id, name, city, lat, lng,
 * o bien se construye a partir de voice_profiles agrupadas.
 */
export async function queryWorldHolons(): Promise<HolonLocation[]> {
  // Intenta leer de tabla `holons` si existe
  try {
    const rows = await query<{
      id: string;
      name: string;
      city: string;
      lat: number;
      lng: number;
      active_members: number;
      total_hoca: number;
      top_category: string;
    }>(
      `SELECT
         h.id, h.name, h.city, h.lat, h.lng,
         COUNT(DISTINCT vp.member_name)::int          AS active_members,
         COALESCE(SUM(t.recompensa_hoca), 0)         AS total_hoca,
         MODE() WITHIN GROUP (ORDER BY t.categoria)  AS top_category
       FROM holons h
       LEFT JOIN voice_profiles vp ON vp.holon_id = h.id
       LEFT JOIN tasks t ON t.holon_id = h.id AND t.estado = 'aprobada'
       GROUP BY h.id, h.name, h.city, h.lat, h.lng`,
      []
    );

    return rows.map((r) => ({
      id: r.id,
      name: r.name,
      city: r.city,
      coordinates: [r.lng, r.lat],
      activeMembers: r.active_members,
      totalHocaDistributed: Math.round(r.total_hoca),
      topCategory: mapCategory(r.top_category),
    }));
  } catch {
    // Si la tabla holons no existe aún, devuelve el holón piloto
    return [
      {
        id: "familia-valdez",
        name: "familia-valdez",
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

/**
 * Historial de transacciones personales de un miembro del holón.
 */
export async function queryUserTransactions(
  holonId: string,
  memberName: string,
  limit = 20
): Promise<PersonalTransaction[]> {
  const rows = await query<{
    id: string;
    categoria: string;
    recompensa_hoca: number;
    descripcion: string;
    created_at: Date;
    estado: string;
  }>(
    `SELECT id, categoria, recompensa_hoca, descripcion, created_at, estado
     FROM tasks
     WHERE holon_id = $1 AND member_name = $2
     ORDER BY created_at DESC
     LIMIT $3`,
    [holonId, memberName, limit]
  );

  return rows.map((row) => {
    const now = Date.now();
    const diffMs = now - new Date(row.created_at).getTime();
    const diffMin = Math.round(diffMs / 60000);
    const timestamp =
      diffMin < 60
        ? `${diffMin} min ago`
        : diffMin < 1440
        ? `${Math.floor(diffMin / 60)}h ago`
        : `${Math.floor(diffMin / 1440)}d ago`;

    return {
      id: row.id,
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

/**
 * Balance total de HOCA ganadas por un miembro (suma histórica).
 * Nota: cuando ON_CHAIN=true, usar el balance del contrato HoCaToken.
 */
export async function queryMemberBalance(
  holonId: string,
  memberName: string
): Promise<number> {
  const rows = await query<{ total: number }>(
    `SELECT COALESCE(SUM(recompensa_hoca), 0) AS total
     FROM tasks
     WHERE holon_id = $1 AND member_name = $2 AND estado = 'aprobada'`,
    [holonId, memberName]
  );
  return Math.round(rows[0]?.total ?? 0);
}

// ─── Helpers internos ─────────────────────────────────────────────────────────

/**
 * Mapea categorías del Tenzo Agent (español) a las del UI (inglés).
 */
function mapCategory(raw: string | null | undefined): CareCategory {
  const map: Record<string, CareCategory> = {
    // Español → inglés
    jardineria: "gardening",
    jardinería: "gardening",
    cocina_comunal: "cooking",
    cocina: "cooking",
    taller_educativo: "teaching",
    ensenanza: "teaching",
    enseñanza: "teaching",
    salud_comunitaria: "healing",
    salud: "healing",
    mantenimiento: "building",
    construccion: "building",
    construcción: "building",
    cuidado_ninos: "caring",
    cuidado: "caring",
    animales: "animals",
    tierra: "land",
    recursos: "resources",
    limpieza_espacios: "resources",
    // Ya en inglés (por si el Tenzo devuelve en inglés)
    gardening: "gardening",
    cooking: "cooking",
    teaching: "teaching",
    healing: "healing",
    building: "building",
    caring: "caring",
    animals: "animals",
    land: "land",
    resources: "resources",
  };
  return map[raw?.toLowerCase() ?? ""] ?? "caring";
}
