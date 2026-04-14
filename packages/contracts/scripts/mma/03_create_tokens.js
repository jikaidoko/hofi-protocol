// scripts/mma/03_create_tokens.js
// Fase 1 — Crear los HolonTokens para los holones piloto
//
// Holones configurados:
//   familia-valdes  → CuidaCoin (CUIDA) — Algorítmico, reserveRatio=50%, precio inicial=0.10 USDC
//   archi-brazo     → BrazoCoin (BRAZO) — Basket, 60% USDC + 40% DAI, colateral mínimo 150%
//
// Requiere: HolonTokenFactory ya desplegado (lee deployments/<network>/HolonTokenFactory.json)
// Uso: npx hardhat run scripts/mma/03_create_tokens.js --network ethSepolia

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

// ═══════════════════════════════════════════════════════════════
// CONFIGURACIÓN DE HOLONES
// Editar aquí para añadir/modificar holones antes del deploy
// ═══════════════════════════════════════════════════════════════
const HOLONES = [
  {
    holonId: "familia-valdes",
    name: "CuidaCoin",
    symbol: "CUIDA",
    decimals: 18,
    mode: "ALGORITHMIC",
    // Bonding curve: 50% reserveRatio = precio elástico pero moderado
    reserveRatio: 5000,          // 50% en basis points
    initialPrice: 100_000,       // 0.10 USDC (6 decimales: 100_000 = 0.1 USDC)
    maxSupplyCap: 0,             // Ilimitado
  },
  {
    holonId: "archi-brazo",
    name: "BrazoCoin",
    symbol: "BRAZO",
    decimals: 18,
    mode: "BASKET",
    // Basket: 60% USDC + 40% DAI, mínimo 150% colateralización
    // En testnet usamos el mismo MockUSDC como ambos colaterales (simplificación)
    collateralRatios: [6000, 4000],   // 60% + 40% = 10000
    collateralRatioMin: 15000,        // 150%
  },
];

// ═══════════════════════════════════════════════════════════════

function loadDeployment(networkName, contractName) {
  const filePath = path.join(__dirname, "../../deployments", networkName, `${contractName}.json`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Deployment no encontrado: ${filePath}`);
  }
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function saveDeployment(networkName, contractName, address, metadata = {}) {
  const dir = path.join(__dirname, "../../deployments", networkName);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, `${contractName}.json`),
    JSON.stringify({ address, ...metadata }, null, 2)
  );
}

// Dirección del DAI en cada red (para basket real)
const DAI_ADDRESSES = {
  ethSepolia: "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357",  // DAI Sepolia (Aave testnet)
  holonchain: "0x0000000000000000000000000000000000000000",   // TODO: bridge DAI
  hardhat:    "0x0000000000000000000000000000000000000000",
};

async function main() {
  const [deployer] = await ethers.getSigners();
  const governanceAddress = process.env.GOVERNANCE_ADDRESS || deployer.address;

  console.log(`\n🚀 Crear HolonTokens`);
  console.log(`   Red:         ${network.name}`);
  console.log(`   Deployer:    ${deployer.address}`);
  console.log(`   Governance:  ${governanceAddress}`);
  console.log(`   Balance:     ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  // Cargar Factory
  const factoryDeployment = loadDeployment(network.name, "HolonTokenFactory");
  const usdcDeployment = loadDeployment(network.name, "MockUSDC");

  const factory = await ethers.getContractAt("HolonTokenFactory", factoryDeployment.address);
  console.log(`   Factory:  ${factoryDeployment.address}`);
  console.log(`   MockUSDC: ${usdcDeployment.address}\n`);

  const daiAddress = DAI_ADDRESSES[network.name] || DAI_ADDRESSES.hardhat;
  const results = {};

  for (const holon of HOLONES) {
    console.log(`── Holon: ${holon.holonId} (${holon.mode}) ──`);

    let tx, tokenAddress;

    if (holon.mode === "ALGORITHMIC") {
      tx = await factory.createAlgorithmicToken(
        holon.holonId,
        holon.name,
        holon.symbol,
        holon.decimals,
        governanceAddress,
        holon.reserveRatio,
        holon.initialPrice,
        holon.maxSupplyCap
      );
      const receipt = await tx.wait();
      // Leer evento HolonTokenCreated
      const event = receipt.logs
        .map((log) => { try { return factory.interface.parseLog(log); } catch { return null; } })
        .find((e) => e && e.name === "HolonTokenCreated");
      tokenAddress = event ? event.args.tokenAddress : await factory.getTokenAddress(holon.holonId);

      console.log(`   ✅ ${holon.symbol} (CUIDA): ${tokenAddress}`);
      console.log(`      reserveRatio=${holon.reserveRatio/100}%, initialPrice=${holon.initialPrice} (${holon.initialPrice/1e6} USDC)`);

    } else if (holon.mode === "BASKET") {
      // En testnet: usamos MockUSDC + DAI (si existe) o dos veces MockUSDC
      const collateralTokens = [
        usdcDeployment.address,
        daiAddress !== "0x0000000000000000000000000000000000000000" ? daiAddress : usdcDeployment.address,
      ];
      console.log(`   Colaterales: [${collateralTokens[0]}, ${collateralTokens[1]}]`);
      console.log(`   Ratios:      [${holon.collateralRatios}], min colateral: ${holon.collateralRatioMin/100}%`);

      tx = await factory.createBasketToken(
        holon.holonId,
        holon.name,
        holon.symbol,
        holon.decimals,
        governanceAddress,
        collateralTokens,
        holon.collateralRatios,
        holon.collateralRatioMin
      );
      const receipt = await tx.wait();
      const event = receipt.logs
        .map((log) => { try { return factory.interface.parseLog(log); } catch { return null; } })
        .find((e) => e && e.name === "HolonTokenCreated");
      tokenAddress = event ? event.args.tokenAddress : await factory.getTokenAddress(holon.holonId);

      console.log(`   ✅ ${holon.symbol} (BRAZO): ${tokenAddress}`);
    }

    results[holon.holonId] = {
      holonId: holon.holonId,
      tokenAddress,
      symbol: holon.symbol,
      name: holon.name,
      mode: holon.mode,
      governance: governanceAddress,
    };

    // Guardar por holonId
    saveDeployment(network.name, `HolonToken_${holon.holonId}`, tokenAddress, results[holon.holonId]);
    console.log();
  }

  // Guardar resumen de todos los tokens
  saveDeployment(network.name, "HolonTokens_all", "N/A", { tokens: results });

  console.log(`\n📄 Tokens guardados en deployments/${network.name}/`);
  console.log(`\nSiguiente paso (Fase 2):`);
  console.log(`   npx hardhat run scripts/mma/04_deploy_pools.js --network ${network.name}\n`);

  return results;
}

main().catch((error) => {
  console.error("❌ Error:", error);
  process.exit(1);
});
