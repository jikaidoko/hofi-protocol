/**
 * deploy/deployHolonSBT.mjs
 * Deploya HolonSBT ISC v0.2.0 en GenLayer Testnet Bradbury.
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   node deploy/deployHolonSBT.mjs
 *
 * Variables de entorno:
 *   GENLAYER_PRIVATE_KEY  — clave privada de tu cuenta en GenLayer Studio
 *                           (copiala desde Studio → Accounts → Export key)
 *   HOLON_NAME            — nombre del holón (default: "familia-valdes")
 *   GENLAYER_NETWORK      — "bradbury" (default) o "studionet"
 *
 * Red Bradbury:
 *   RPC:       https://rpc-bradbury.genlayer.com
 *   Chain ID:  4221
 *   Explorer:  https://explorer-bradbury.genlayer.com
 *   Faucet:    https://testnet-faucet.genlayer.foundation
 */

import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Chains ────────────────────────────────────────────────────────────────────
// genlayer-js@0.28+ incluye testnetBradbury y studionet con consensusMainContract
// ya configurado. No es necesario construirlos manualmente.

// ── Config ────────────────────────────────────────────────────────────────────

const PRIVATE_KEY = process.env.GENLAYER_PRIVATE_KEY;
const HOLON_NAME  = process.env.HOLON_NAME ?? "familia-valdes";
const NETWORK     = (process.env.GENLAYER_NETWORK ?? "bradbury").toLowerCase();

if (!PRIVATE_KEY) {
  console.error(
    "\n❌  Falta la variable GENLAYER_PRIVATE_KEY.\n" +
    "    Copiá tu clave privada desde GenLayer Studio → Accounts\n" +
    "    y corré:\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    "    node deploy/deployHolonSBT.mjs\n"
  );
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

const CONTRACT_PATH = path.resolve(
  __dirname,
  "../contracts/holon_sbt_isc.py"
);

// ── Deploy ────────────────────────────────────────────────────────────────────

async function main() {
  const networkLabel = NETWORK === "studionet"
    ? "GenLayer Studionet (Asimov)"
    : "GenLayer Testnet Bradbury";

  console.log("\n🏡  HoFi Protocol — Deploy HolonSBT ISC v0.2.0");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📄  Contrato  :", CONTRACT_PATH);
  console.log("🌐  Red       :", networkLabel);
  console.log("🏡  Holón     :", HOLON_NAME);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  // initializeConsensusSmartContract() solo funciona con el simulador local
  // (chain ID 61999). En Bradbury/Studionet el contrato de consenso ya está
  // desplegado on-chain — no necesita inicialización manual.
  if (NETWORK === "localnet") {
    console.log("⚙️   Inicializando consensus smart contract (localnet)...");
    await client.initializeConsensusSmartContract();
  }

  const contractCode = new Uint8Array(readFileSync(CONTRACT_PATH));

  console.log("🚀  Deployando HolonSBT ISC v0.2.0...");
  console.log("    Constructor arg: holon_name =", HOLON_NAME);

  const txHash = await client.deployContract({
    code: contractCode,
    args: [HOLON_NAME],   // __init__(self, holon_name: str)
  });

  console.log("🔗  TX hash   :", txHash);
  console.log("⏳  Esperando confirmación (puede tardar 30–90 segundos)...\n");

  // genlayer-js@0.28+: waitForTransactionReceipt acepta solo hash + status string.
  // Status "ACCEPTED" es el punto de finalización normal en Bradbury.
  const receipt = await client.waitForTransactionReceipt({
    hash:     txHash,
    status:   "ACCEPTED",
    retries:  200,
    interval: 2000,
  });

  // v0.28+ en Bradbury: el éxito se detecta por resultName === "AGREE" (consenso alcanzado)
  // y status_name === "ACCEPTED". txExecutionResultName puede ser "FINISHED_WITH_ERROR"
  // para constructores que retornan None (comportamiento normal en GenLayer ISCs).
  const resultName     = receipt?.resultName;
  const execResultName = receipt?.txExecutionResultName;
  const statusName     = receipt?.status_name ?? receipt?.statusName;

  const AGREE_RESULTS = new Set(["AGREE", "MAJORITY_AGREE"]);

  if (!AGREE_RESULTS.has(resultName)) {
    console.error("❌  Deploy falló — consenso no alcanzado.");
    console.error("    resultName           :", resultName);
    console.error("    txExecutionResultName:", execResultName);
    console.error("    statusName           :", statusName);
    console.error("    Receipt (resumido)   :", safeStringify(receipt));
    process.exit(1);
  }

  if (execResultName === "FINISHED_WITH_ERROR") {
    // Para constructores Python que retornan None, GenLayer reporta FINISHED_WITH_ERROR
    // pero el deploy es exitoso si resultName es AGREE. No interrumpir, solo advertir.
    console.warn("⚠️   txExecutionResultName: FINISHED_WITH_ERROR (normal para constructores)");
  }

  const contractAddress = receipt?.txDataDecoded?.contractAddress;

  console.log("✅  HolonSBT ISC v0.2.0 deployado exitosamente!");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Dirección del contrato:");
  console.log("   ", contractAddress);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
  console.log("🔧  Próximos pasos:");
  console.log("");
  console.log("  1. Emitir primer SBT (owner del holón):");
  console.log(`     $env:HOLON_SBT_ADDRESS = "${contractAddress ?? "<address>"}"`);
  console.log("     node deploy/callIssueSBT.mjs");
  console.log("");
  console.log("  2. Actualizar HOFI_COWORK_MEMORY.md con la nueva dirección:");
  console.log(`     HolonSBT ISC v0.2.0: ${contractAddress ?? "<address>"}`);
  console.log("");
  console.log("  3. Actualizar env var en Cloud Run si el Tenzo usa el SBT:");
  console.log(
    `     gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 \\\n` +
    `       --update-env-vars="HOLON_SBT_ADDRESS=${contractAddress ?? "<address>"}"\n`
  );
}

// BigInt-safe JSON serializer (JSON.stringify lanza en BigInt por defecto)
function safeStringify(obj) {
  return JSON.stringify(obj, (_key, value) =>
    typeof value === "bigint" ? value.toString() + "n" : value
  , 2);
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err.message ?? err);
  process.exit(1);
});
