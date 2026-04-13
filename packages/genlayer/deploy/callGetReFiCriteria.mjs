/**
 * deploy/callGetReFiCriteria.mjs
 * Lee los criterios actuales del ReFiGovernanceISC (verificación post-deploy).
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   $env:REFI_ISC_ADDRESS     = "0x<dirección_del_contrato>"
 *   node deploy/callGetReFiCriteria.mjs
 *
 * Opcionales:
 *   $env:GENLAYER_NETWORK   — "bradbury" (default) o "studionet"
 *   $env:DEPLOY_TX_HASH     — TX del deploy para diagnosticar status
 *   $env:READ_RETRIES       — cantidad de reintentos (default: 8)
 *   $env:READ_INTERVAL_MS   — ms entre reintentos (default: 5000)
 */

import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

const PRIVATE_KEY    = process.env.GENLAYER_PRIVATE_KEY;
const ISC_ADDRESS    = process.env.REFI_ISC_ADDRESS;
const NETWORK        = (process.env.GENLAYER_NETWORK ?? "bradbury").toLowerCase();
const DEPLOY_TX_HASH = process.env.DEPLOY_TX_HASH;
const RETRIES        = parseInt(process.env.READ_RETRIES   ?? "8",    10);
const INTERVAL_MS    = parseInt(process.env.READ_INTERVAL_MS ?? "5000", 10);

if (!PRIVATE_KEY || !ISC_ADDRESS) {
  console.error(
    "\n❌  Faltan variables de entorno.\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    '    $env:REFI_ISC_ADDRESS     = "0x<dirección>"\n' +
    "    node deploy/callGetReFiCriteria.mjs\n"
  );
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function tryRead(client, address) {
  // Intentamos primero con latest-nonfinal (más reciente, default).
  // Si falla, probamos con latest-final (más conservador).
  const variants = ["latest-nonfinal", "latest-final"];
  let lastErr;
  for (const variant of variants) {
    try {
      return await client.readContract({
        address,
        functionName: "get_criteria",
        args: [],
        transactionHashVariant: variant,
      });
    } catch (e) {
      lastErr = e;
      // Si el error es "contract not found", probamos otra variante.
      // Si es otro error, lo propagamos directo.
      if (!String(e?.message ?? e).toLowerCase().includes("not found")) {
        throw e;
      }
    }
  }
  throw lastErr;
}

async function diagnoseDeployTx(client, txHash) {
  try {
    const tx = await client.getTransaction({ hash: txHash });
    console.log("\n🔍  Diagnóstico TX deploy:");
    console.log("    hash       :", txHash);
    console.log("    status     :", tx?.statusName ?? `(num: ${tx?.status})`);
    console.log("    result     :", tx?.resultName ?? "(none)");
    console.log("    txExecRes  :", tx?.txExecutionResultName ?? "(none)");
    console.log("    recipient  :", tx?.recipient);
    console.log("    queuePos   :", tx?.queuePosition);
    if (tx?.txDataDecoded?.contractAddress) {
      console.log("    contractAddr:", tx.txDataDecoded.contractAddress);
    }
  } catch (e) {
    console.warn("⚠️   No se pudo diagnosticar la TX:", e.message ?? e);
  }
}

async function main() {
  console.log("\n🌱  HoFi — ReFiGovernanceISC — Verificar criterios");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Contrato : ", ISC_ADDRESS);
  console.log("🌐  Red      : ", NETWORK);
  console.log("🔁  Reintentos:", RETRIES, `(cada ${INTERVAL_MS}ms)`);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  if (DEPLOY_TX_HASH) {
    await diagnoseDeployTx(client, DEPLOY_TX_HASH);
  }

  let raw, lastErr;
  for (let attempt = 1; attempt <= RETRIES; attempt++) {
    try {
      console.log(`📖  Intento ${attempt}/${RETRIES} — leyendo get_criteria()...`);
      raw = await tryRead(client, ISC_ADDRESS);
      console.log(`    ✅  Lectura exitosa en intento ${attempt}\n`);
      break;
    } catch (e) {
      lastErr = e;
      const msg = e?.message ?? String(e);
      console.warn(`    ⚠️   Intento ${attempt} falló: ${msg.split("\n")[0]}`);
      if (attempt < RETRIES) {
        console.warn(`    ⏳  Esperando ${INTERVAL_MS}ms antes de reintentar...\n`);
        await sleep(INTERVAL_MS);
      }
    }
  }

  if (raw === undefined) {
    console.error("\n❌  No se pudo leer el contrato después de", RETRIES, "intentos.");
    console.error("    Último error:", lastErr?.message ?? lastErr);
    console.error("\n💡  Diagnóstico sugerido:");
    console.error("   1. Verificar la TX en el explorer:");
    console.error("      https://explorer-bradbury.genlayer.com/tx/<TX_HASH>");
    console.error("   2. Si el contrato aún no está FINALIZED, esperar más tiempo.");
    console.error("   3. Si la TX fue rechazada, redeployar con scripts/contracts corregidos.\n");
    process.exit(1);
  }

  // get_criteria() retorna JSON string en v1.1.0+
  const result = (typeof raw === "string") ? JSON.parse(raw) : raw;

  console.log("✅  Criterios actuales:");
  console.log(JSON.stringify(result, null, 2));

  // Verificar valores esperados
  const expected = {
    min_impact_score:       "0.60",
    max_risk_score:         "0.40",
    yield_vs_impact_weight: "0.30",
    local_priority_bonus:   "0.15",
  };
  let ok = true;
  for (const [key, val] of Object.entries(expected)) {
    if (result?.[key] !== val) {
      console.warn(`⚠️   ${key}: esperado "${val}", recibido "${result?.[key]}"`);
      ok = false;
    }
  }
  if (ok) console.log("\n✅  Todos los criterios coinciden con los valores default.");
}

main().catch((err) => {
  console.error("❌  Error:", err.message ?? err);
  process.exit(1);
});
