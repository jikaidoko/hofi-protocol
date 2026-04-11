/**
 * deploy/callIssueSBT.mjs
 * Llama a issue_sbt() en HolonSBT ISC v0.2.0 (Bradbury / Studionet).
 * Úsalo para agregar miembros del holón después del deploy inicial.
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY  = "0x<clave_del_owner>"
 *   $env:HOLON_SBT_ADDRESS     = "0x<address_del_contrato>"
 *   $env:MEMBER_ADDRESS        = "0x<address_del_miembro>"
 *   $env:MEMBER_ROLE           = "member"    # opcional, default: "member"
 *   node deploy/callIssueSBT.mjs
 *
 * Roles válidos: member | coordinator | tenzo | ambassador | guardian
 */

import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury, studionet } from "genlayer-js/chains";

// ── Config ────────────────────────────────────────────────────────────────────

const PRIVATE_KEY     = process.env.GENLAYER_PRIVATE_KEY;
const SBT_ADDRESS     = process.env.HOLON_SBT_ADDRESS;
const MEMBER_ADDRESS  = process.env.MEMBER_ADDRESS;
const MEMBER_ROLE     = process.env.MEMBER_ROLE ?? "member";
const NETWORK         = (process.env.GENLAYER_NETWORK ?? "bradbury").toLowerCase();

const VALID_ROLES = ["member", "coordinator", "tenzo", "ambassador", "guardian"];

for (const [name, val] of [
  ["GENLAYER_PRIVATE_KEY", PRIVATE_KEY],
  ["HOLON_SBT_ADDRESS",    SBT_ADDRESS],
  ["MEMBER_ADDRESS",       MEMBER_ADDRESS],
]) {
  if (!val) {
    console.error(`\n❌  Falta la variable ${name}.\n`);
    process.exit(1);
  }
}

if (!VALID_ROLES.includes(MEMBER_ROLE)) {
  console.error(`\n❌  Rol inválido: "${MEMBER_ROLE}". Válidos: ${VALID_ROLES.join(", ")}\n`);
  process.exit(1);
}

const chain = NETWORK === "studionet" ? studionet : testnetBradbury;

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const networkLabel = NETWORK === "studionet"
    ? "Studionet (Asimov)"
    : "Testnet Bradbury";

  console.log("\n🏡  HoFi — issue_sbt (HolonSBT ISC v0.2.0)");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Contrato  :", SBT_ADDRESS);
  console.log("🌐  Red       :", networkLabel);
  console.log("👤  Miembro   :", MEMBER_ADDRESS);
  console.log("🎭  Rol       :", MEMBER_ROLE);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  // initializeConsensusSmartContract() es exclusivo del simulador local.
  // En Bradbury/Studionet el contrato de consenso ya está on-chain.

  console.log("📡  Enviando issue_sbt...");
  const txHash = await client.writeContract({
    address:      SBT_ADDRESS,
    functionName: "issue_sbt",
    args: [MEMBER_ADDRESS, MEMBER_ROLE],
  });

  console.log("🔗  TX hash   :", txHash);
  console.log("⏳  Esperando finalización...\n");

  let receipt;
  try {
    const { TransactionStatus } = await import("genlayer-js/types").catch(() => ({}));
    receipt = await client.waitForTransactionReceipt({
      hash:     txHash,
      status:   TransactionStatus?.ACCEPTED ?? "ACCEPTED",
      retries:  200,
      interval: 2000,
    });
  } catch {
    receipt = await client.waitForTransactionReceipt({
      hash:     txHash,
      status:   "FINALIZED",
      retries:  200,
      interval: 2000,
    });
  }

  const execResult =
    receipt?.consensus_data?.leader_receipt?.[0]?.execution_result;

  if (execResult !== "SUCCESS") {
    console.error("❌  issue_sbt falló. execution_result:", execResult);
    console.error("    Receipt:\n", JSON.stringify(receipt, null, 2));
    process.exit(1);
  }

  console.log("✅  SBT emitido exitosamente!");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("👤  Miembro   :", MEMBER_ADDRESS);
  console.log("🎭  Rol       :", MEMBER_ROLE);
  console.log("🔗  TX        :", txHash);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
  console.log("El miembro ahora puede usar validate_contribution() y");
  console.log("calculate_vote_weight() en el ISC de GenLayer.\n");
}

main().catch((err) => {
  console.error("❌  Error inesperado:", err.message ?? err);
  process.exit(1);
});
