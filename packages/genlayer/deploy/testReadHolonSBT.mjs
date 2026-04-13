/**
 * deploy/testReadHolonSBT.mjs
 * Diagnóstico — intenta leer un método del HolonSBT ISC v0.2.0 ya finalizado.
 *
 * Si esto funciona y callGetReFiCriteria.mjs falla, confirma que:
 *   - gen_call funciona en Bradbury para contratos finalizados
 *   - el ReFiGovernanceISC necesita esperar a FINALIZED para ser legible
 *
 * Uso:
 *   $env:GENLAYER_PRIVATE_KEY = "0x<tu_clave>"
 *   node deploy/testReadHolonSBT.mjs
 */

import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";

const PRIVATE_KEY = process.env.GENLAYER_PRIVATE_KEY ??
  "0x0000000000000000000000000000000000000000000000000000000000000001";

// HolonSBT ISC v0.2.0 — desplegado 11-abril-2026 en Bradbury (FINALIZED hace tiempo)
const HOLON_SBT = "0x4b89EB9f787dF1e3DC834bF82c7a306492Bd1AD1";

async function main() {
  console.log("\n🔍  Test diagnóstico — leer HolonSBT v0.2.0 (finalizado)");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Contrato:", HOLON_SBT);
  console.log("🌐  Red     : Bradbury");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain: testnetBradbury, account });

  const tests = [
    { fn: "get_owner",         args: [] },
    { fn: "get_holon_name",    args: [] },
    { fn: "get_member_count",  args: [] },
  ];

  for (const t of tests) {
    try {
      console.log(`📖  Probando ${t.fn}(${t.args.join(",")})...`);
      const result = await client.readContract({
        address: HOLON_SBT,
        functionName: t.fn,
        args: t.args,
      });
      console.log(`    ✅  Resultado:`, result);
    } catch (e) {
      console.log(`    ❌  Error:`, e.message?.split("\n")[0] ?? e);
    }
    console.log("");
  }

  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("Si TODOS los métodos de arriba funcionaron:");
  console.log("  → gen_call funciona en Bradbury para contratos FINALIZED");
  console.log("  → El ReFi ISC solo necesita esperar finalización (10–30 min)");
  console.log("");
  console.log("Si TODOS fallaron con 'contract not found':");
  console.log("  → Hay un problema con gen_call en Bradbury en general");
  console.log("  → Hay que reportarlo en GenLayer Discord");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

main().catch(err => {
  console.error("❌  Error inesperado:", err.message ?? err);
  process.exit(1);
});
