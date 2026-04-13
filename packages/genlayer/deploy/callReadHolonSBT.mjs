/**
 * deploy/callReadHolonSBT.mjs
 * Verifica el HolonSBT ISC leyendo owner, holon_name y member_count (post-deploy).
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   $env:HOLON_SBT_ADDRESS    = "0x22ce5caF239AAD7DbEb7Bea3dDBcC69202d8560E"
 *   $env:GENLAYER_NETWORK     = "studionet"
 *   node deploy/callReadHolonSBT.mjs
 */

import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

const PRIVATE_KEY   = process.env.GENLAYER_PRIVATE_KEY;
const SBT_ADDRESS   = process.env.HOLON_SBT_ADDRESS;
const NETWORK       = (process.env.GENLAYER_NETWORK ?? "studionet").toLowerCase();
const RETRIES       = parseInt(process.env.READ_RETRIES    ?? "8",    10);
const INTERVAL_MS   = parseInt(process.env.READ_INTERVAL_MS ?? "5000", 10);

if (!PRIVATE_KEY || !SBT_ADDRESS) {
  console.error(
    "\n❌  Faltan variables de entorno.\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    '    $env:HOLON_SBT_ADDRESS    = "0x22ce5caF239AAD7DbEb7Bea3dDBcC69202d8560E"\n' +
    '    $env:GENLAYER_NETWORK     = "studionet"\n' +
    "    node deploy/callReadHolonSBT.mjs\n"
  );
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

async function readWithRetry(client, address, method, args = []) {
  for (let i = 1; i <= RETRIES; i++) {
    try {
      const result = await client.readContract({
        address,
        functionName: method,
        args,
      });
      return result;
    } catch (err) {
      const msg = err?.message ?? String(err);
      if (i < RETRIES) {
        console.log(`    [${method}] intento ${i}/${RETRIES} falló (${msg.slice(0, 80)}…) — reintentando en ${INTERVAL_MS}ms`);
        await new Promise(r => setTimeout(r, INTERVAL_MS));
      } else {
        throw err;
      }
    }
  }
}

async function main() {
  const networkLabel = NETWORK === "studionet" ? "GenLayer Studionet (Asimov)" : "GenLayer Testnet Bradbury";

  console.log("\n🌱  HoFi Protocol — Verificación HolonSBT ISC v0.2.1");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Contrato    :", SBT_ADDRESS);
  console.log("🌐  Red         :", networkLabel);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  console.log("📖  Leyendo estado del contrato...\n");

  let owner, holonName, memberCount;

  try {
    console.log("  → get_owner()");
    owner = await readWithRetry(client, SBT_ADDRESS, "get_owner");
    console.log("    owner       :", owner);
  } catch (err) {
    console.error("  ❌  get_owner falló:", err?.message ?? err);
  }

  try {
    console.log("  → get_holon_name()");
    holonName = await readWithRetry(client, SBT_ADDRESS, "get_holon_name");
    console.log("    holon_name  :", holonName);
  } catch (err) {
    console.error("  ❌  get_holon_name falló:", err?.message ?? err);
  }

  try {
    console.log("  → get_member_count()");
    memberCount = await readWithRetry(client, SBT_ADDRESS, "get_member_count");
    console.log("    member_count:", memberCount);
  } catch (err) {
    console.error("  ❌  get_member_count falló:", err?.message ?? err);
  }

  const allOk = owner !== undefined && holonName !== undefined && memberCount !== undefined;

  console.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  if (allOk) {
    console.log("✅  HolonSBT ISC v0.2.1 verificado — contrato responde correctamente.");
    console.log("\n🔧  Próximos pasos:");
    console.log(`  1. Emitir SBTs para miembros del holón:`);
    console.log(`     $env:HOLON_SBT_ADDRESS = "${SBT_ADDRESS}"`);
    console.log("     node deploy/callIssueSBT.mjs");
    console.log("  2. Actualizar Cloud Run Tenzo con HOLON_SBT_ADDRESS:");
    console.log(`     gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 \\\n       --update-env-vars="HOLON_SBT_ADDRESS=${SBT_ADDRESS}"`);
  } else {
    console.log("⚠️   Algunas lecturas fallaron. El contrato puede estar aún finalizando.");
    console.log("    Reintentá en ~30 segundos.");
  }
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err?.message ?? err);
  process.exit(1);
});
