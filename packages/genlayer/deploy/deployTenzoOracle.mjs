/**
 * deploy/deployTenzoOracle.mjs
 * Deploya TenzoEquityOracle v0.2.0 en GenLayer Testnet Asimov (Studionet).
 *
 * Uso:
 *   node deploy/deployTenzoOracle.mjs
 *
 * Variables de entorno requeridas:
 *   GENLAYER_PRIVATE_KEY  — clave privada de tu cuenta en GenLayer Studio
 *                           (copiala desde Studio → Accounts → Export key)
 */

import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

// genlayer-js@0.28+ incluye studionet con consensusMainContract ya configurado.
const chain = studionet;

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const PRIVATE_KEY = process.env.GENLAYER_PRIVATE_KEY;

if (!PRIVATE_KEY) {
  console.error(
    "\n❌  Falta la variable GENLAYER_PRIVATE_KEY.\n" +
    "    Copiá tu clave privada desde GenLayer Studio → Accounts\n" +
    "    y corré:\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    "    node deploy/deployTenzoOracle.mjs\n"
  );
  process.exit(1);
}

const CONTRACT_PATH = path.resolve(
  __dirname,
  "../contracts/tenzo_equity_oracle.py"
);

// ── Deploy ────────────────────────────────────────────────────────────────────

async function main() {
  console.log("🔑  Cuenta:", accountAddress(PRIVATE_KEY));
  console.log("📄  Contrato:", CONTRACT_PATH);
  console.log("🌐  Red: GenLayer Testnet Asimov (Studionet)\n");

  const account = createAccount(PRIVATE_KEY);
  const client = createClient({
    chain,
    account,
  });

  // initializeConsensusSmartContract() es exclusivo del simulador local (chain ID 61999).
  // En Studionet/Bradbury el contrato de consenso ya está on-chain — no inicializar.

  const contractCode = new Uint8Array(readFileSync(CONTRACT_PATH));

  console.log("🚀  Deployando TenzoEquityOracle v0.2.2...");
  const txHash = await client.deployContract({
    code: contractCode,
    args: [],
  });

  console.log("⏳  Esperando confirmación (puede tardar 30–60 segundos)...");
  const receipt = await client.waitForTransactionReceipt({
    hash:     txHash,
    status:   "ACCEPTED",
    retries:  200,
    interval: 2000,
  });

  const execResultName = receipt?.txExecutionResultName;
  if (execResultName !== "FINISHED_WITH_RETURN") {
    console.error("❌  Deploy falló.");
    console.error("    txExecutionResultName:", execResultName);
    console.error("    resultName           :", receipt?.resultName);
    console.error("    statusName           :", receipt?.statusName);
    process.exit(1);
  }

  const contractAddress = receipt?.txDataDecoded?.contractAddress;

  console.log("\n✅  TenzoEquityOracle v0.2.2 deployado exitosamente!");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Dirección del contrato:");
  console.log("   ", contractAddress);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("\n🔗  Próximo paso — activar en Cloud Run:");
  console.log(
    `    gcloud run services update hofi-tenzo --project=hofi-v2-2026 --region=us-central1 \`\n` +
    `      --update-env-vars="TENZO_ORACLE_ADDRESS=${contractAddress}"\n`
  );
}

// Deriva address desde private key sin dependencias extra
function accountAddress(pk) {
  try {
    // Solo muestra primeros/últimos chars por seguridad
    return pk.slice(0, 6) + "..." + pk.slice(-4);
  } catch {
    return "(clave configurada)";
  }
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err);
  process.exit(1);
});
