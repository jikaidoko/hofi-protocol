/**
 * deploy/deployReFiGovernanceISC.mjs
 * Deploya ReFiGovernanceISC v1.0.0 en GenLayer Testnet Bradbury / Studionet.
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   node deploy/deployReFiGovernanceISC.mjs
 *
 * Variables de entorno:
 *   GENLAYER_PRIVATE_KEY   — clave privada de tu cuenta en GenLayer Studio
 *                            (copiala desde Studio → Accounts → Export key)
 *   GOVERNANCE_ADDRESS     — dirección governance del CommonStakePool
 *                            (default: deployer address)
 *   GENLAYER_NETWORK       — "bradbury" (default) o "studionet"
 *
 * Redes disponibles:
 *   Bradbury:   RPC https://rpc-bradbury.genlayer.com  | Chain ID 4221
 *   Studionet:  RPC https://rpc-studionet.genlayer.com | Chain ID 61999
 *   Explorer:   https://explorer-bradbury.genlayer.com
 *   Faucet:     https://testnet-faucet.genlayer.foundation
 *
 * Contratos relacionados (Sepolia):
 *   CommonStakePool : 0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5
 *   Deployer wallet : 0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8
 */

import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Config ────────────────────────────────────────────────────────────────────

const PRIVATE_KEY          = process.env.GENLAYER_PRIVATE_KEY;
const GOVERNANCE_ADDRESS   = process.env.GOVERNANCE_ADDRESS
                             ?? "0xb755bEb8777459d8c2b4E3fEA6676aa481a03ED8";
const NETWORK              = (process.env.GENLAYER_NETWORK ?? "bradbury").toLowerCase();

if (!PRIVATE_KEY) {
  console.error(
    "\n❌  Falta la variable GENLAYER_PRIVATE_KEY.\n" +
    "    Copiá tu clave privada desde GenLayer Studio → Accounts\n" +
    "    y corré:\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    "    node deploy/deployReFiGovernanceISC.mjs\n"
  );
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

const CONTRACT_PATH = path.resolve(
  __dirname,
  "../contracts/refi_governance_isc.py"
);

// ── Deploy ────────────────────────────────────────────────────────────────────

async function main() {
  const networkLabel = NETWORK === "studionet"
    ? "GenLayer Studionet (Asimov)"
    : "GenLayer Testnet Bradbury";

  console.log("\n🌱  HoFi Protocol — Deploy ReFiGovernanceISC v1.1.0");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📄  Contrato    :", CONTRACT_PATH);
  console.log("🌐  Red         :", networkLabel);
  console.log("🏛️   Governance  :", GOVERNANCE_ADDRESS);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  const contractCode = new Uint8Array(readFileSync(CONTRACT_PATH));

  console.log("🚀  Deployando ReFiGovernanceISC v1.0.0...");
  console.log("    Constructor arg: governance_address =", GOVERNANCE_ADDRESS);

  const txHash = await client.deployContract({
    code: contractCode,
    args: [GOVERNANCE_ADDRESS],  // __init__(self, governance_address: CalldataAddress)
  });

  console.log("🔗  TX hash   :", txHash);
  console.log("⏳  Esperando confirmación (puede tardar 30–90 segundos)...\n");

  const receipt = await client.waitForTransactionReceipt({
    hash:     txHash,
    status:   "ACCEPTED",
    retries:  200,
    interval: 2000,
  });

  // Studionet devuelve snake_case; Bradbury puede devolver camelCase según versión del SDK.
  const resultName     = receipt?.result_name     ?? receipt?.resultName;
  const execResultName = receipt?.txExecutionResultName ?? receipt?.tx_execution_result_name;
  const statusName     = receipt?.status_name     ?? receipt?.statusName;

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
    console.warn("⚠️   txExecutionResultName: FINISHED_WITH_ERROR (normal para constructores)");
  }

  // Studionet: data.contract_address | Bradbury: txDataDecoded.contractAddress
  const contractAddress =
    receipt?.data?.contract_address ??
    receipt?.txDataDecoded?.contractAddress;

  console.log("✅  ReFiGovernanceISC v1.1.0 deployado exitosamente!");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Dirección del contrato:");
  console.log("   ", contractAddress);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
  console.log("🔧  Próximos pasos:\n");
  console.log("  1. Verificar el deploy (read call):");
  console.log(`     $env:REFI_ISC_ADDRESS = "${contractAddress ?? "<address>"}"`);
  console.log("     node deploy/callGetReFiCriteria.mjs\n");
  console.log("  2. Proponer inversión de prueba:");
  console.log("     node deploy/callProposeInvestment.mjs\n");
  console.log("  3. Asignar REFI_EXECUTOR_ROLE al relayer en CommonStakePool (Sepolia):");
  console.log("     Ver instrucciones en contracts/DEPLOY_REFI_ISC.md → Paso 7b\n");
  console.log("  4. Actualizar HOFI_COWORK_MEMORY.md:");
  console.log(`     ReFiGovernanceISC v1.1.0  ✅ ACTIVO  — ${contractAddress ?? "<address>"}\n`);
}

function safeStringify(obj) {
  return JSON.stringify(obj, (_key, value) =>
    typeof value === "bigint" ? value.toString() + "n" : value
  , 2);
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err.message ?? err);
  process.exit(1);
});
