/**
 * deploy/testRpcEndpoint.mjs
 * Diagnóstico de bajo nivel — verifica si gen_call y gen_getContractSchema 
 * responden correctamente en Bradbury.
 */
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";

const PRIVATE_KEY = process.env.GENLAYER_PRIVATE_KEY ??
  "0x0000000000000000000000000000000000000000000000000000000000000001";

// Ambos contratos conocidos
const CONTRACTS = {
  "HolonSBT (old)": "0x4b89EB9f787dF1e3DC834bF82c7a306492Bd1AD1",
  "ReFiGovernanceISC (new)": "0x9Ed284f82c75230CA7deBe38253F06Aee94a8d9D"
};

async function main() {
  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain: testnetBradbury, account });

  console.log("\n🔍  Diagnóstico RPC Bradbury — gen_getContractSchema");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("🌐  RPC:", testnetBradbury.rpcUrls?.default?.http?.[0] ?? "unknown");

  for (const [name, addr] of Object.entries(CONTRACTS)) {
    console.log(`\n📍  ${name}: ${addr}`);
    try {
      // gen_getContractSchema es un método de consulta que no requiere estado FINALIZED
      const schema = await client.request({
        method: "gen_getContractSchema",
        params: [addr]
      });
      console.log("    ✅  Schema encontrado:", JSON.stringify(schema).slice(0, 200));
    } catch (e) {
      console.log("    ❌  gen_getContractSchema falló:", e.message?.split("\n")[0]);
    }
  }

  console.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("💡  Si gen_getContractSchema devuelve el schema:");
  console.log("    → El nodo SÍ reconoce el contrato");
  console.log("    → El problema está en gen_call específicamente");
  console.log("    → Solución: redeploy en studionet o esperar parche de Bradbury");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

main().catch(e => { console.error("Error:", e.message); process.exit(1); });
