// HoFi Protocol - Canonicalizacion de person_id
//
// Port TypeScript de packages/telegram-bot/voice_auth.canonical_person_id().
// Debe devolver EXACTAMENTE el mismo resultado que la implementacion Python
// para que el frontend y el bot de Telegram escriban tasks.persona_id con
// la misma clave canonica, y cada miembro acumule HoCa en un unico bucket.
//
// Ejemplos:
//   "!Doco!"         -> "doco"
//   "Mourino"        -> "mourino"
//   "Doco Luna"      -> "doco"
//   "Andralis M."    -> "andralis"
//   "  LUNA  "       -> "luna"
//   ""               -> ""

/**
 * Deriva el person_id canonico a partir de un nombre display.
 *
 *   1. Normaliza NFD y quita combining marks (tildes, diaeresis, enie -> n).
 *   2. Quita puntuacion (todo lo no alfanumerico ASCII ni whitespace).
 *   3. Minusculas y colapsa espacios.
 *   4. Devuelve solo el primer token - los apellidos no contaminan la clave.
 *
 * Tiene que ser idempotente y 1:1 con `voice_auth.canonical_person_id()`
 * en Python. Si alguna vez cambia uno, ambos deben cambiar juntos.
 *
 * El orden NFD-PRIMERO + regex ASCII (sin flag /u) permite compilar sin
 * requerir target ES2018+, manteniendo compatibilidad con la config base
 * de Next.js.
 */
export function canonicalPersonId(nombre: string | null | undefined): string {
  if (!nombre) return "";

  // 1) NFD + strip de combining marks.
  const sinDiacriticos = nombre
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

  // 2) Quitar puntuacion: todo lo que no sea letra ASCII, digito, _ o whitespace.
  const sinPuntuacion = sinDiacriticos.replace(/[^\w\s]/g, " ");

  // 3) Minusculas + colapsar whitespace + trim.
  const norm = sinPuntuacion.toLowerCase().replace(/\s+/g, " ").trim();

  // 4) Primer token unicamente.
  const tokens = norm.split(" ").filter(Boolean);
  return tokens[0] ?? "";
}
