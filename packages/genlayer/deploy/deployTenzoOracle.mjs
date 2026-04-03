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
import { localnet } from "genlayer-js/chains";

// Studio Hosted usa el chain "localnet" internamente pero apunta a su propio servidor.
// Confirmado en runtime-config.js: VITE_GENLAYER_NETWORK="localnet",
//   VITE_JSON_RPC_SERVER_URL="https://studio.genlayer.com/api"
// Sobreescribimos solo la URL manteniendo el resto del objeto localnet intacto.
const chain = {
  ...localnet,
  rpcUrls: {
    default: { http: ["https://studio.genlayer.com/api"] },
    public:  { http: ["https://studio.genlayer.com/api"] },
  },
};

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

  console.log("⚙️   Inicializando consensus smart contract...");
  await client.initializeConsensusSmartContract();

  const contractCode = new Uint8Array(readFileSync(CONTRACT_PATH));

  console.log("🚀  Deployando TenzoEquityOracle v0.2.2...");
  const txHash = await client.deployContract({
    code: contractCode,
    args: [],
  });

  console.log("⏳  Esperando confirmación (puede tardar 30–60 segundos)...");
  // status puede ser string "ACCEPTED" o el enum TransactionStatus.ACCEPTED según versión
  let receipt;
  try {
    const { TransactionStatus } = await import("genlayer-js/types").catch(() => ({}));
    receipt = await client.waitForTransactionReceipt({
      hash: txHash,
      status: TransactionStatus?.ACCEPTED ?? "ACCEPTED",
      retries: 200,
      interval: 2000,
    });
  } catch {
    receipt = await client.waitForTransactionReceipt({
      hash: txHash,
      status: "FINALIZED",
      retries: 200,
      interval: 2000,
    });
  }

  const execResult =
    receipt?.consensus_data?.leader_receipt?.[0]?.execution_result;

  if (execResult !== "SUCCESS") {
    console.error("❌  Deploy falló.");
    console.error("    Receipt:", JSON.stringify(receipt, null, 2));
    process.exit(1);
  }

  const contractAddress = receipt?.data?.contract_address;

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
