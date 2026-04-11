/**
 * deploy/callGetHolonRules.mjs
 * Lee get_holon_rules() del TenzoEquityOracle v0.2.1 (Studionet Asimov).
 *
 * Uso:
 *   node deploy/callGetHolonRules.mjs
 *
 * Variables de entorno (opcionales):
 *   ORACLE_ADDRESS  — override de dirección, por defecto v0.2.1
 *   HOLON_ID        — override del holón a consultar, por defecto "familia-valdes"
 */

import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const chain = {
  ...studionet,
  rpcUrls: {
    default: { http: ["https://studio.genlayer.com/api"] },
    public:  { http: ["https://studio.genlayer.com/api"] },
  },
};

const ORACLE_ADDRESS = process.env.ORACLE_ADDRESS
  ?? "0x5b125045739238fb6d6664bD1718ff18b883C1C7";  // v0.2.1

const HOLON_ID = process.env.HOLON_ID ?? "familia-valdes";

// Para llamadas de lectura (readContract) no se necesita clave privada real,
// pero genlayer-js requiere una cuenta para inicializar el cliente.
// Usamos una dummy si no hay clave configurada.
const PRIVATE_KEY =
  process.env.GENLAYER_PRIVATE_KEY ??
  "0x0000000000000000000000000000000000000000000000000000000000000001";

async function main() {
  const account = createAccount(PRIVATE_KEY);
  const client  = createClient({ chain, account });

  console.log("\n🏡  HoFi — get_holon_rules");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("📍  Oracle   :", ORACLE_ADDRESS);
  console.log("🆔  Holón    :", HOLON_ID);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  console.log("📖  Leyendo reglas del holón...");
  const rules = await client.readContract({
    address: ORACLE_ADDRESS,
    functionName: "get_holon_rules",
    args: [HOLON_ID],
  });

  console.log("\n✅  Reglas on-chain para el holón", `"${HOLON_ID}":`);
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(rules ?? "(sin reglas registradas)");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
}

main().catch((err) => {
  console.error("❌  Error:", err.message ?? err);
  process.exit(1);
});
