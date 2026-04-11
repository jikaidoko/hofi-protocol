/**
 * deploy/callSetHolonRules.mjs
 * Llama a set_holon_rules() en TenzoEquityOracle v0.2.2 (Studionet Asimov).
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   $env:ORACLE_ADDRESS       = "0x<nueva_direccion_v0.2.2>"
 *   node deploy/callSetHolonRules.mjs
 *
 * Variables de entorno:
 *   GENLAYER_PRIVATE_KEY  — clave privada del owner (deployer del ISC)
 *   ORACLE_ADDRESS        — dirección del contrato v0.2.2 (REQUERIDA)
 */

import { createClient, createAccount } from "genlayer-js";
import { localnet } from "genlayer-js/chains";

// Studio Asimov usa chain "localnet" pero apunta a su propio servidor.
const chain = {
  ...localnet,
  rpcUrls: {
    default: { http: ["https://studio.genlayer.com/api"] },
    public:  { http: ["https://studio.genlayer.com/api"] },
  },
};

// ── Config ────────────────────────────────────────────────────────────────────

const PRIVATE_KEY    = process.env.GENLAYER_PRIVATE_KEY;
const ORACLE_ADDRESS = process.env.ORACLE_ADDRESS;  // REQUERIDA — nueva dirección v0.2.2

const HOLON_ID        = "familia-valdes";
const RULES_DESCRIPTION =
  "Holón familiar orientado al cuidado regenerativo. Se valoran tareas de " +
  "cuidado humano (cocinar, cuidar niños, acompañar enfermos), cuidado " +
  "animal, cuidado ecológico (huerta, compostaje, semillas), y mantenimiento " +
  "del espacio compartido. La recompensa debe ser proporcional al tiempo y al " +
  "impacto relacional. Se prioriza la equidad entre miembros adultos y se " +
  "reconoce el trabajo invisible históricamente no remunerado.";

if (!PRIVATE_KEY) {
  console.error(
    "\n❌  Falta GENLAYER_PRIVATE_KEY.\n" +
    "    Copiá tu clave desde GenLayer Studio → Accounts → Export key\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n'
  );
  process.exit(1);
}
if (!ORACLE_ADDRESS) {
  console.error(
    "\n❌  Falta ORACLE_ADDRESS.\n" +
    "    Copiá la dirección del deploy v0.2.2 y corré:\n\n" +
    '    $env:ORACLE_ADDRESS = "0x<nueva_direccion>"\n' +
    "    node deploy/callSetHolonRules.mjs\n"
  );
  process.exit(1);
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  console.log("\n🏡  HoFi — set_holon_rules");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Oracle   :", ORACLE_ADDRESS);
  console.log("🆔  Holón    :", HOLON_ID);
  console.log("📜  Reglas   :\n   ", RULES_DESCRIPTION);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  // initializeConsensusSmartContract() es exclusivo del simulador local.
  // En Studionet/Bradbury no es necesario.

  console.log("📡  Enviando transacción set_holon_rules...");
  const txHash = await client.writeContract({
    address: ORACLE_ADDRESS,
    functionName: "set_holon_rules",
    args: [HOLON_ID, RULES_DESCRIPTION],
  });

  console.log("🔗  TX hash:", txHash);
  console.log("⏳  Esperando finalización (puede tardar ~60 segundos)...\n");

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
    console.error("❌  La transacción falló.");
    console.error("    Receipt:", JSON.stringify(receipt, null, 2));
    process.exit(1);
  }

  console.log("✅  set_holon_rules ejecutado exitosamente!");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("🏡  Holón    :", HOLON_ID);
  console.log("📜  Reglas registradas en el ISC v0.2.2");
  console.log("🔗  TX       :", txHash);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
  console.log("Los validadores GenLayer ahora usarán estas reglas como criterio");
  console.log("de equidad al evaluar tareas del holón familia-valdes.\n");
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err.message ?? err);
  process.exit(1);
});
