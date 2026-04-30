// HoFi Protocol — Datos mock para desarrollo y fallback UI
// Los componentes importan desde aquí mientras no hay conexión real al backend.
// Cuando las API routes estén activas, migrar a @/lib/api/client.ts

import type {
  ActivityItem,
  CareCategory,
  HolonLocation,
  ImpactCircle,
  PersonalTransaction,
} from "@/lib/api/types";

// ─── Re-export de tipos desde api/types para compatibilidad ──────────────────
export type {
  UserRole,
  UserSession,
  CareCategory,
  ActivityItem,
  HolonStats,
  SocialYieldMetric,
  HolonLocation,
  PersonalTransaction,
  TransactionType,
  MetricScope,
  ImpactCircle,
} from "@/lib/api/types";

// Alias para compatibilidad con impact-circles.tsx que importa ImpactCircleData
export type { ImpactCircle as ImpactCircleData } from "@/lib/api/types";

export { CARE_CATEGORY_META as ACTIVITY_CATEGORIES } from "@/lib/api/types";

// ─── Mock: Stats del holón ───────────────────────────────────────────────────

export const MOCK_HOLON_STATS = {
  holonId: "familia-mourino",
  totalMembers: 3,
  activeCaregivers: 2,
  health: 87,
  weeklyGrowth: 12,
  totalHocaDistributed: 1240,
};

// ─── Mock: Feed de actividades ────────────────────────────────────────────────

export const MOCK_ACTIVITY_FEED: ActivityItem[] = [
  {
    id: "act-001",
    category: "gardening" as CareCategory,
    amount: 45,
    timestamp: "5 min ago",
    exactTime: new Date(Date.now() - 5 * 60000).toISOString(),
    memberName: "Doco",
    memberAvatar: "DO",
    description: "Siembra y riego de la huerta comunitaria del holón.",
  },
  {
    id: "act-002",
    category: "cooking" as CareCategory,
    amount: 38,
    timestamp: "1 hour ago",
    exactTime: new Date(Date.now() - 60 * 60000).toISOString(),
    memberName: "Luna",
    memberAvatar: "LU",
    description: "Preparación de almuerzo comunitario para 5 personas.",
  },
  {
    id: "act-003",
    category: "caring" as CareCategory,
    amount: 62,
    timestamp: "2 hours ago",
    exactTime: new Date(Date.now() - 120 * 60000).toISOString(),
    memberName: "Gaya",
    memberAvatar: "GA",
    description: "Acompañamiento y cuidado durante la tarde.",
  },
  {
    id: "act-004",
    category: "teaching" as CareCategory,
    amount: 55,
    timestamp: "3 hours ago",
    exactTime: new Date(Date.now() - 180 * 60000).toISOString(),
    memberName: "Doco",
    memberAvatar: "DO",
    description: "Taller de permacultura con los chicos del barrio.",
  },
  {
    id: "act-005",
    category: "building" as CareCategory,
    amount: 70,
    timestamp: "5 hours ago",
    exactTime: new Date(Date.now() - 300 * 60000).toISOString(),
    memberName: "Doco",
    memberAvatar: "DO",
    description: "Mantenimiento de la infraestructura del espacio común.",
  },
];

// ─── Mock: Social Yield ───────────────────────────────────────────────────────

export const MOCK_SOCIAL_YIELD = [
  { label: "HOCA distributed", value: 1240, unit: "HOCA",   change: 18 },
  { label: "Care acts",        value: 47,   unit: "acts",   change: 12 },
  { label: "Active members",   value: 3,    unit: "people", change: 0  },
  { label: "Avg per act",      value: 26.4, unit: "HOCA",   change: 5  },
];

// ─── Mock: Ubicaciones de holones en el mundo ─────────────────────────────────

export const MOCK_HOLON_LOCATIONS: HolonLocation[] = [
  {
    id: "familia-mourino",
    name: "Familia Mouriño",
    city: "Buenos Aires, AR",
    coordinates: [-58.3816, -34.6037],
    activeMembers: 3,
    totalHocaDistributed: 1240,
    topCategory: "gardening",
  },
  {
    id: "archi-brazo",
    name: "archi-brazo",
    city: "Córdoba, AR",
    coordinates: [-64.1888, -31.4201],
    activeMembers: 8,
    totalHocaDistributed: 3850,
    topCategory: "building",
  },
  {
    id: "el-pantano",
    name: "el-pantano",
    city: "Delta del Tigre, AR",
    coordinates: [-58.5796, -34.4246],
    activeMembers: 5,
    totalHocaDistributed: 2100,
    topCategory: "land",
  },
];

// ─── Mock: Impact Circles ─────────────────────────────────────────────────────
// Los IDs "co2", "gnh", "cci" mapean al COLOR_CONFIG en impact-circles.tsx.
// Cada métrica tiene valores por scope (personal / holon / world).

export const MOCK_IMPACT_CIRCLES: ImpactCircle[] = [
  {
    id: "co2",
    unit: "kg",
    thisWeek: { personal: 12, holon: 48, world: 320 },
    lastWeek: { personal: 9,  holon: 40, world: 280 },
    allTime:  { personal: 85, holon: 340, world: 2800 },
  },
  {
    id: "gnh",
    unit: "pts",
    thisWeek: { personal: 6.8, holon: 5.9, world: 6.2 },
    lastWeek: { personal: 6.5, holon: 5.7, world: 6.0 },
    allTime:  { personal: 6.8, holon: 5.9, world: 6.2 },
  },
  {
    id: "cci",
    unit: "hrs",
    thisWeek: { personal: 7.5, holon: 28, world: 190 },
    lastWeek: { personal: 6,   holon: 22, world: 150 },
    allTime:  { personal: 52,  holon: 205, world: 1400 },
  },
];

// ─── Mock: Transacciones personales ───────────────────────────────────────────

export const MOCK_PERSONAL_TRANSACTIONS: PersonalTransaction[] = [
  {
    id: "tx-001",
    type: "earned",
    amount: 45,
    description: "Huerta comunitaria — siembra y riego",
    timestamp: "5 min ago",
    exactTime: new Date(Date.now() - 5 * 60000).toISOString(),
    category: "gardening",
  },
  {
    id: "tx-002",
    type: "earned",
    amount: 55,
    description: "Taller de permacultura",
    timestamp: "3 hours ago",
    exactTime: new Date(Date.now() - 180 * 60000).toISOString(),
    category: "teaching",
  },
  {
    id: "tx-003",
    type: "received",
    amount: 20,
    description: "Transferencia de reconocimiento",
    timestamp: "Yesterday",
    exactTime: new Date(Date.now() - 24 * 60 * 60000).toISOString(),
    counterparty: "Luna",
  },
  {
    id: "tx-004",
    type: "earned",
    amount: 70,
    description: "Mantenimiento espacio común",
    timestamp: "2 days ago",
    exactTime: new Date(Date.now() - 2 * 24 * 60 * 60000).toISOString(),
    category: "building",
  },
  {
    id: "tx-005",
    type: "spent",
    amount: 15,
    description: "Materiales para la huerta",
    timestamp: "3 days ago",
    exactTime: new Date(Date.now() - 3 * 24 * 60 * 60000).toISOString(),
    category: "resources",
  },
];

// ─── Mock: Tareas pendientes de aprobación comunitaria ──────────────────────

import type { PendingTask, HolonApprovalRules } from "@/components/hofi/community-approval-modal";

export const MOCK_HOLON_APPROVAL_RULES: HolonApprovalRules = {
  holonName: "Familia Mouriño",
  requiredApprovals: 3,
  totalMembers: 5,
  spirit:
    "In our holon, caring is the yield. Each member's voice recognizes the invisible work that sustains our community.",
};

export const MOCK_PENDING_TASKS: PendingTask[] = [
  {
    id: "pending-001",
    description:
      "Cuidé a los niños toda la mañana mientras los padres estaban en el taller de construcción. Preparé el desayuno, jugamos y leímos cuentos.",
    memberName: "Luna",
    memberAvatar: "LM",
    category: "caring",
    duration: 4,
    tenzoConfidence: 0.62,
    tenzoReasoning:
      "Childcare is essential community work. Duration is reasonable for a morning of care. The description includes multiple activities (cooking, playing, reading) which suggests genuine engagement.",
    suggestedReward: 240,
    submittedAt: "2 hours ago",
    approvalsRequired: 3,
    approvals: [
      {
        memberName: "Doco",
        memberAvatar: "DV",
        approvedAt: "1 hour ago",
      },
    ],
    myVote: "none",
  },
  {
    id: "pending-002",
    description:
      "Reparé la cerca del gallinero que estaba rota y reorganicé el espacio para que las gallinas tengan más área de pastoreo.",
    memberName: "Amaru",
    memberAvatar: "AM",
    category: "building",
    duration: 2.5,
    tenzoConfidence: 0.58,
    tenzoReasoning:
      "Fence repair and animal habitat improvement aligns with both maintenance and ecological care. The 2.5 hours is proportional to the described scope of work.",
    suggestedReward: 150,
    submittedAt: "5 hours ago",
    approvalsRequired: 3,
    approvals: [
      {
        memberName: "Doco",
        memberAvatar: "DV",
        approvedAt: "4 hours ago",
      },
      {
        memberName: "Luna",
        memberAvatar: "LM",
        approvedAt: "3 hours ago",
      },
    ],
    myVote: "none",
  },
  {
    id: "pending-003",
    description:
      "Preparé conservas de tomate con la cosecha del fin de semana. 12 frascos para la comunidad.",
    memberName: "Uma",
    memberAvatar: "UM",
    category: "cooking",
    duration: 3,
    tenzoConfidence: 0.55,
    tenzoReasoning:
      "Food preservation from community harvest is valuable long-term care. 12 jars for 3 hours is a realistic production rate. This extends the yield of garden work into sustained nourishment.",
    suggestedReward: 180,
    submittedAt: "1 day ago",
    approvalsRequired: 3,
    approvals: [],
    myVote: "none",
  },
];
