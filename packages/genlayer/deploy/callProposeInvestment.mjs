/**
 * deploy/callProposeInvestment.mjs
 * Propone y evalúa una inversión ReFi de prueba en el ISC.
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   $env:REFI_ISC_ADDRESS     = "0x<dirección_del_contrato>"
 *   node deploy/callProposeInvestment.mjs
 *
 * Opcionales:
 *   $env:PROPOSAL_ID   — override del ID (default: genera uno con timestamp)
 *   $env:SKIP_EVALUATE — "true" para solo proponer sin evaluar
 */

import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

const PRIVATE_KEY    = process.env.GENLAYER_PRIVATE_KEY;
const ISC_ADDRESS    = process.env.REFI_ISC_ADDRESS;
const NETWORK        = (process.env.GENLAYER_NETWORK ?? "bradbury").toLowerCase();
const SKIP_EVALUATE  = process.env.SKIP_EVALUATE === "true";
const PROPOSAL_ID    = process.env.PROPOSAL_ID
                       ?? `test-solar-fv-${Date.now()}`;

if (!PRIVATE_KEY || !ISC_ADDRESS) {
  console.error(
    "\n❌  Faltan variables de entorno.\n\n" +
    '    $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"\n' +
    '    $env:REFI_ISC_ADDRESS     = "0x<dirección>"\n' +
    "    node deploy/callProposeInvestment.mjs\n"
  );
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

// ── Propuesta de prueba ───────────────────────────────────────────────────────
const PROPOSAL = {
  proposal_id:     PROPOSAL_ID,
  holon_id:        "familia-valdes",
  project_name:    "Panel solar comunitario",
  description:     "Instalación de 10 paneles solares en el espacio comunitario del holón familia-valdes. Reduce la factura energética colectiva y genera excedente para venta a la red.",
  amount_usdc:     "2000",
  expected_yield:  "0.06",
  impact_evidence: "Reduce 4.8 toneladas de CO2 equivalente por año. Beneficia directamente a 12 familias. Tecnología probada con proveedor local certificado. Retorno de inversión estimado en 4 años.",
  ods_goals:       "ODS7,ODS13",
  sector:          "renewable_energy",
  is_local:        true,
};

async function main() {
  console.log("\n🌱  HoFi — ReFiGovernanceISC — Propuesta de inversión");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Contrato  :", ISC_ADDRESS);
  console.log("🌐  Red       :", NETWORK);
  console.log("📋  Propuesta :", PROPOSAL_ID);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  // ── 1. propose_investment ─────────────────────────────────────────────────
  console.log("📝  Enviando propuesta...");
  console.log("    Proyecto:", PROPOSAL.project_name);
  console.log("    Monto:   ", PROPOSAL.amount_usdc, "USDC");
  console.log("    Yield:   ", `${parseFloat(PROPOSAL.expected_yield) * 100}%`, "anual");
  console.log("    Local:   ", PROPOSAL.is_local ? "Sí (bonus +15%)" : "No");

  const proposeTx = await client.writeContract({
    address:      ISC_ADDRESS,
    functionName: "propose_investment",
    args: [
      PROPOSAL.proposal_id,
      PROPOSAL.holon_id,
      PROPOSAL.project_name,
      PROPOSAL.description,
      PROPOSAL.amount_usdc,
      PROPOSAL.expected_yield,
      PROPOSAL.impact_evidence,
      PROPOSAL.ods_goals,
      PROPOSAL.sector,
      PROPOSAL.is_local,
    ],
  });

  console.log("🔗  TX hash:", proposeTx);
  console.log("⏳  Esperando confirmación...");

  const proposeReceipt = await client.waitForTransactionReceipt({
    hash:     proposeTx,
    status:   "ACCEPTED",
    retries:  100,
    interval: 2000,
  });

  if (!["AGREE", "MAJORITY_AGREE"].includes(proposeReceipt?.resultName)) {
    console.error("❌  propose_investment falló:", proposeReceipt?.resultName);
    console.error(safeStringify(proposeReceipt));
    process.exit(1);
  }
  console.log("✅  Propuesta registrada.\n");

  if (SKIP_EVALUATE) {
    console.log("⏭️   SKIP_EVALUATE=true — omitiendo evaluación.");
    console.log(`\n    Para evaluar más tarde:\n`);
    console.log(`    $env:PROPOSAL_ID = "${PROPOSAL_ID}"`);
    console.log("    (agregar llamada a evaluate_investment en un script separado)\n");
    return;
  }

  // ── 2. evaluate_investment ────────────────────────────────────────────────
  console.log("🤖  Iniciando evaluación LLM (5 validadores — puede tardar 1–2 min)...");

  const evalTx = await client.writeContract({
    address:      ISC_ADDRESS,
    functionName: "evaluate_investment",
    args: [PROPOSAL.proposal_id],
  });

  console.log("🔗  TX hash:", evalTx);
  console.log("⏳  Esperando consenso de validadores...\n");

  const evalReceipt = await client.waitForTransactionReceipt({
    hash:     evalTx,
    status:   "ACCEPTED",
    retries:  300,
    interval: 3000,
  });

  if (!["AGREE", "MAJORITY_AGREE"].includes(evalReceipt?.resultName)) {
    console.error("❌  evaluate_investment falló:", evalReceipt?.resultName);
    console.error(safeStringify(evalReceipt));
    process.exit(1);
  }

  // ── 3. Leer resultado ─────────────────────────────────────────────────────
  // get_evaluation() retorna JSON string en v1.1.0
  const rawEval = await client.readContract({
    address:      ISC_ADDRESS,
    functionName: "get_evaluation",
    args: [PROPOSAL.proposal_id],
  });
  const evaluation = (typeof rawEval === "string") ? JSON.parse(rawEval) : rawEval;

  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(evaluation?.approved ? "✅  APROBADA" : "❌  RECHAZADA");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("   impact_score    :", evaluation?.impact_score);
  console.log("   yield_score     :", evaluation?.yield_score);
  console.log("   risk_score      :", evaluation?.risk_score);
  console.log("   composite_score :", evaluation?.composite_score);
  console.log("\n📝  Razonamiento:");
  console.log("   ", evaluation?.reasoning);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  if (evaluation?.approved) {
    console.log("🚀  Próximo paso: el relayer ejecuta executeReFiInvestment() en Sepolia:");
    console.log("    CommonStakePool: 0xd3BB4A84e022D9b26FdAF85AaC486be1d847A7f5");
    console.log("    Función: executeReFiInvestment(recipient, amount, projectId, evidence)");
  } else {
    console.log("ℹ️   La propuesta fue rechazada. Podés revisar los scores y ajustar");
    console.log("    la evidencia de impacto o el rendimiento esperado antes de re-proponer.");
  }
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
