// HoFi Protocol — Tipos compartidos entre cliente y servidor
// Estos tipos reemplazan los de lib/mock-data y son los que usa la API real.

// ─── Roles y sesión ──────────────────────────────────────────────────────────

export type UserRole = "guest" | "member" | "guardian";

export interface UserSession {
  userId: string;
  name: string;
  role: UserRole;
  holonId: string;
  balance: number;      // Balance HOCA del usuario
  avatar: string;       // Iniciales para el avatar UI
  telegramId?: number;  // ID de Telegram si aplica
}

// ─── Cuidado y categorías ────────────────────────────────────────────────────

export type CareCategory =
  | "gardening"
  | "cooking"
  | "teaching"
  | "healing"
  | "building"
  | "caring"
  | "animals"
  | "land"
  | "resources";

// Mapa con label y colores para el UI (equivalente al ACTIVITY_CATEGORIES del mock)
export const CARE_CATEGORY_META: Record<
  CareCategory,
  { label: string; bgColor: string; color: string }
> = {
  gardening: { label: "Gardening",  bgColor: "bg-green-500",   color: "text-green-600"  },
  cooking:   { label: "Cooking",    bgColor: "bg-orange-500",  color: "text-orange-600" },
  teaching:  { label: "Teaching",   bgColor: "bg-blue-500",    color: "text-blue-600"   },
  healing:   { label: "Healing",    bgColor: "bg-rose-500",    color: "text-rose-600"   },
  building:  { label: "Building",   bgColor: "bg-amber-600",   color: "text-amber-700"  },
  caring:    { label: "Caring",     bgColor: "bg-pink-500",    color: "text-pink-600"   },
  animals:   { label: "Animals",    bgColor: "bg-teal-500",    color: "text-teal-600"   },
  land:      { label: "Land",       bgColor: "bg-lime-600",    color: "text-lime-700"   },
  resources: { label: "Resources",  bgColor: "bg-violet-500",  color: "text-violet-600" },
};

// ─── Actividades / feed ───────────────────────────────────────────────────────

export interface ActivityItem {
  id: string;
  category: CareCategory;
  amount: number;          // HOCA otorgadas
  timestamp: string;       // Texto legible: "5 min ago", "2 hours ago"
  exactTime: string;       // ISO-8601
  // Campos opcionales según el rol que consulta:
  memberName?: string;     // Solo visible para guardian
  memberAvatar?: string;   // Iniciales (visible para member+)
  description?: string;    // Solo visible para guardian
}

// ─── Holon ────────────────────────────────────────────────────────────────────

export interface HolonStats {
  holonId: string;
  totalMembers: number;
  activeCaregivers: number;
  health: number;           // 0–100
  weeklyGrowth: number;     // porcentaje
  totalHocaDistributed: number;
}

export interface SocialYieldMetric {
  label: string;
  value: string | number;
  unit: string;
  change: number;           // % cambio respecto al período anterior
}

// ─── Mundo / mapa ─────────────────────────────────────────────────────────────

export interface HolonLocation {
  id: string;
  name: string;
  city: string;
  coordinates: [number, number];   // [lng, lat]
  activeMembers: number;
  totalHocaDistributed: number;
  topCategory: CareCategory;
}

// ─── Transacciones personales ─────────────────────────────────────────────────

export type TransactionType = "earned" | "received" | "spent" | "sent";

export interface PersonalTransaction {
  id: string;
  type: TransactionType;
  amount: number;
  description: string;
  timestamp: string;        // Texto legible
  exactTime: string;        // ISO-8601
  category?: CareCategory;
  counterparty?: string;    // Nombre del otro participante
}

// ─── Impact circles ───────────────────────────────────────────────────────────

export type MetricScope = "personal" | "holon" | "world";

export interface ImpactCircle {
  id: string;               // "co2" | "gnh" | "cci"
  unit: string;
  // Valores desagregados por scope para el componente ImpactCircles
  thisWeek: Record<MetricScope, number>;
  lastWeek: Record<MetricScope, number>;
  allTime: Record<MetricScope, number>;
}

// ─── Respuestas API ───────────────────────────────────────────────────────────

export interface ApiSuccess<T> {
  ok: true;
  data: T;
}

export interface ApiError {
  ok: false;
  error: string;
  status?: number;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;

// ─── Evaluación Tenzo ─────────────────────────────────────────────────────────

export interface TenzoEvaluationInput {
  descripcion: string;
  categoria: string;
  duracion_horas: number;
  holon_id: string;
  ubicacion?: string;
}

export interface TenzoEvaluationResult {
  modo: string;
  aprobada: boolean;
  recompensa_hoca: number;
  clasificacion: string[];
  razonamiento: string;
  alerta: string | null;
  on_chain: { tx_hash: string; explorer: string } | null;
  // Campos del nuevo UI:
  task_id?: string;
}

// ─── Voice auth ───────────────────────────────────────────────────────────────

export interface VoiceAuthResult {
  authenticated: boolean;
  session?: UserSession;
  confidence?: number;
  error?: string;
}
