// scripts/mma/04_deploy_pools.js
// Fase 2 — Deploy CommonStakePool + HoFiMMAPool por holon
//
// Orden de operaciones:
//   1. Deploy CommonStakePool (stablecoin)
//   2. Por cada holon: deploy HoFiMMAPool
//   3. Registrar cada MMAPool en CommonStakePool (grantRole MMA_POOL_ROLE)
//   4. Linkear MMAPool en HolonTokenFactory
//   5. Seed de liquidez inicial (requiere balance en deployer)
//
// Variables de entorno requeridas:
//   PRIVATE_KEY          — clave del deployer (también es governance en testnet)
//   GOVERNANCE_ADDRESS   — (opcional) dirección de governance; default = deployer
//
// Uniswap V3 Router por red:
//   Por defecto: 0x000...000 (sin bridge — AMM local funciona igual)
//   Para activar bridge: $env:UNISWAP_ROUTER="0x<dirección_correcta>"
//
// Uso: npx hardhat run scripts/mma/04_deploy_pools.js --network ethSepolia

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

// ═══════════════════════════════════════════════════════════════
// CONFIGURACIÓN DE POOLS
// ═══════════════════════════════════════════════════════════════

// Uniswap V3 Router address por red
// NOTA: usar UNISWAP_ROUTER env var para sobreescribir en cualquier red.
// La dirección 0x000...000 indica "sin bridge Uniswap" — el AMM local sigue funcionando.
// El bridge solo se activa para swaps > umbral (10k USDC); en testnet esto no aplica.
// TODO: verificar dirección exacta de SwapRouter02 en Sepolia antes de producción.
const UNISWAP_ROUTERS = {
  ethSepolia:  process.env.UNISWAP_ROUTER || "0x0000000000000000000000000000000000000000",
  baseSepolia: process.env.UNISWAP_ROUTER || "0x0000000000000000000000000000000000000000",
  holonchain:  "0x0000000000000000000000000000000000000000",
  hardhat:     "0x0000000000000000000000000000000000000000",
};

// Pool fee tier de Uniswap (0.3% = 3000)
const UNISWAP_POOL_FEE = 3000;

// Liquidez inicial por pool (en unidades nativas)
// Requiere que el deployer tenga balance suficiente de MockUSDC y HolonToken
const SEED_LIQUIDITY = {
  "familia-valdes": {
    holonAmount: ethers.parseEther("1000"),          // 1000 CUIDA
    stableAmount: ethers.parseUnits("100", 6),       // 100 USDC → precio inicial 0.1 USDC/CUIDA
    seedEnabled: true,
  },
  "archi-brazo": {
    holonAmount: ethers.parseEther("500"),           // 500 BRAZO
    stableAmount: ethers.parseUnits("250", 6),       // 250 USDC → precio inicial 0.5 USDC/BRAZO
    seedEnabled: true,
  },
};

// ═══════════════════════════════════════════════════════════════

function loadDeployment(networkName, contractName) {
  const filePath = path.join(__dirname, "../../deployments", networkName, `${contractName}.json`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Deployment no encontrado: ${filePath}\nAsegúrate de haber ejecutado las fases anteriores.`);
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

async function main() {
  const [deployer] = await ethers.getSigners();
  const governanceAddress = ethers.getAddress(process.env.GOVERNANCE_ADDRESS || deployer.address);
  const uniswapRouter = ethers.getAddress(UNISWAP_ROUTERS[network.name] || UNISWAP_ROUTERS.hardhat);

  console.log(`\n🚀 Deploy Pools MMA`);
  console.log(`   Red:         ${network.name}`);
  console.log(`   Deployer:    ${deployer.address}`);
  console.log(`   Governance:  ${governanceAddress}`);
  console.log(`   UniswapV3:   ${uniswapRouter}`);
  console.log(`   Balance:     ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  if (uniswapRouter === "0x0000000000000000000000000000000000000000") {
    console.log(`⚠️  AVISO: Uniswap V3 no disponible en ${network.name}.`);
    console.log(`   Los swaps > umbral fallarán hasta configurar un router alternativo.\n`);
  }

  // Cargar deployments previos
  const usdcDeployment = loadDeployment(network.name, "MockUSDC");
  const factoryDeployment = loadDeployment(network.name, "HolonTokenFactory");

  // Normalizar direcciones de deployments previos a checksum EIP-55
  const usdcAddress = ethers.getAddress(usdcDeployment.address);
  const factoryAddress = ethers.getAddress(factoryDeployment.address);

  const usdc = await ethers.getContractAt("MockUSDC", usdcAddress);
  const factory = await ethers.getContractAt("HolonTokenFactory", factoryAddress);

  console.log(`   MockUSDC:   ${usdcAddress}`);
  console.log(`   Factory:    ${factoryAddress}\n`);

  // ── 1. Deploy CommonStakePool ─────────────────────────────────
  console.log(`── 1. Deploy CommonStakePool ──`);
  const CommonStakePool = await ethers.getContractFactory("CommonStakePool");
  const commonPool = await CommonStakePool.deploy(usdcAddress, uniswapRouter);
  await commonPool.waitForDeployment();
  const commonPoolAddress = await commonPool.getAddress();
  console.log(`   ✅ CommonStakePool: ${commonPoolAddress}`);

  // Otorgar GOVERNANCE_ROLE al governance address (si es diferente del deployer)
  if (governanceAddress !== deployer.address) {
    const GOVERNANCE_ROLE = await commonPool.GOVERNANCE_ROLE();
    await (await commonPool.grantRole(GOVERNANCE_ROLE, governanceAddress)).wait();
    console.log(`   ✅ GOVERNANCE_ROLE → ${governanceAddress}`);
  }

  saveDeployment(network.name, "CommonStakePool", commonPoolAddress, {
    deployer: deployer.address,
    governance: governanceAddress,
    stablecoin: usdcDeployment.address,
    blockNumber: (await ethers.provider.getBlockNumber()),
  });

  // ── 2. Deploy HoFiMMAPool por holon ──────────────────────────
  const mmaPoolAddresses = {};
  const holones = ["familia-valdes", "archi-brazo"];

  for (const holonId of holones) {
    console.log(`\n── 2. Deploy HoFiMMAPool: ${holonId} ──`);

    const tokenDeployment = loadDeployment(network.name, `HolonToken_${holonId}`);
    const tokenAddress = ethers.getAddress(tokenDeployment.tokenAddress);
    console.log(`   HolonToken: ${tokenAddress}`);

    const MMAPool = await ethers.getContractFactory("HoFiMMAPool");
    const mmaPool = await MMAPool.deploy(
      tokenAddress,        // holonToken
      usdcAddress,         // stablecoin
      holonId,             // holonId
      governanceAddress,   // governance
      uniswapRouter,       // uniswapRouter
      commonPoolAddress,   // commonStakePool
      UNISWAP_POOL_FEE     // uniswapPoolFee
    );
    await mmaPool.waitForDeployment();
    const mmaPoolAddress = await mmaPool.getAddress();
    console.log(`   ✅ HoFiMMAPool: ${mmaPoolAddress}`);

    mmaPoolAddresses[holonId] = mmaPoolAddress;

    // ── 3. Registrar MMAPool en CommonStakePool ───────────────
    console.log(`   → Registrando en CommonStakePool (MMA_POOL_ROLE)...`);
    await (await commonPool.registerMMAPool(mmaPoolAddress)).wait();
    console.log(`   ✅ MMA_POOL_ROLE otorgado a ${mmaPoolAddress}`);

    // ── 4. Linkear MMAPool en Factory ────────────────────────
    console.log(`   → Linkeando MMAPool en HolonTokenFactory...`);
    await (await factory.linkMMAPool(holonId, mmaPoolAddress)).wait();
    console.log(`   ✅ MMAPool linkeado en Factory`);

    saveDeployment(network.name, `HoFiMMAPool_${holonId}`, mmaPoolAddress, {
      holonId,
      holonToken: tokenDeployment.tokenAddress,
      stablecoin: usdcDeployment.address,
      commonStakePool: commonPoolAddress,
      governance: governanceAddress,
      uniswapRouter,
      blockNumber: (await ethers.provider.getBlockNumber()),
    });
  }

  // ── 5. Seed de liquidez inicial ───────────────────────────────
  console.log(`\n── 5. Seed de liquidez inicial ──`);

  for (const holonId of holones) {
    const seed = SEED_LIQUIDITY[holonId];
    if (!seed || !seed.seedEnabled) {
      console.log(`   ⏭  ${holonId}: seed deshabilitado, saltando.`);
      continue;
    }

    const tokenDeployment = loadDeployment(network.name, `HolonToken_${holonId}`);
    const mmaPoolAddress = mmaPoolAddresses[holonId];

    const holonToken = await ethers.getContractAt("HolonToken", ethers.getAddress(tokenDeployment.tokenAddress));
    const mmaPool = await ethers.getContractAt("HoFiMMAPool", mmaPoolAddress);

    console.log(`\n   ${holonId}:`);
    console.log(`      CUIDA/BRAZO: ${ethers.formatEther(seed.holonAmount)}`);
    console.log(`      USDC:        ${ethers.formatUnits(seed.stableAmount, 6)}`);

    // Verificar si el deployer tiene el MINTER_ROLE para mintear tokens
    const MINTER_ROLE = await holonToken.MINTER_ROLE();
    const hasMinterRole = await holonToken.hasRole(MINTER_ROLE, deployer.address);

    if (hasMinterRole) {
      // Mintear HolonTokens para el deployer
      console.log(`      → Minteando ${ethers.formatEther(seed.holonAmount)} ${tokenDeployment.symbol}...`);
      await (await holonToken.mint(deployer.address, seed.holonAmount)).wait();
    } else {
      console.log(`   ⚠️  ${deployer.address} no tiene MINTER_ROLE para ${holonId}. Omitiendo mint.`);
      console.log(`      El governance debe mintear manualmente o usar faucet.`);
      continue;
    }

    // Obtener USDC desde faucet si balance insuficiente
    const usdcBalance = await usdc.balanceOf(deployer.address);
    if (usdcBalance < seed.stableAmount) {
      const needed = seed.stableAmount - usdcBalance;
      console.log(`      → Faucet MockUSDC: ${ethers.formatUnits(needed, 6)} USDC...`);
      await (await usdc.faucet(needed)).wait();
    }

    // Aprobar transfers
    console.log(`      → Aprobando tokens para MMAPool...`);
    await (await holonToken.approve(mmaPoolAddress, seed.holonAmount)).wait();
    await (await usdc.approve(mmaPoolAddress, seed.stableAmount)).wait();

    // Añadir liquidez (sin slippage en testnet: min = 0)
    console.log(`      → Añadiendo liquidez...`);
    const tx = await mmaPool.addLiquidity(seed.holonAmount, seed.stableAmount, 0, 0);
    const receipt = await tx.wait();

    // Leer shares emitidas
    const event = receipt.logs
      .map((log) => { try { return mmaPool.interface.parseLog(log); } catch { return null; } })
      .find((e) => e && e.name === "LiquidityAdded");

    if (event) {
      console.log(`   ✅ Liquidez añadida. LP Shares: ${ethers.formatEther(event.args.shares)}`);
    } else {
      console.log(`   ✅ Liquidez añadida.`);
    }

    // Verificar precio inicial
    const price = await mmaPool.getHolonPrice();
    console.log(`      Precio inicial: ${ethers.formatUnits(price, 12)} USDC/${tokenDeployment.symbol}`);
    //  price tiene precisión 1e18; stablecoin tiene 6 decimales → efectivamente: price / 1e18 * 1e6 = price / 1e12
  }

  // ── Resumen final ─────────────────────────────────────────────
  console.log(`\n${"═".repeat(60)}`);
  console.log(`✅ DEPLOY COMPLETO — ${network.name}`);
  console.log(`${"═".repeat(60)}`);
  console.log(`   MockUSDC:          ${usdcAddress}`);
  console.log(`   HolonTokenFactory: ${factoryAddress}`);
  console.log(`   CommonStakePool:   ${commonPoolAddress}`);
  for (const [holonId, addr] of Object.entries(mmaPoolAddresses)) {
    console.log(`   HoFiMMAPool [${holonId}]: ${addr}`);
  }
  console.log(`\n📄 Todos los deployments guardados en deployments/${network.name}/`);
  console.log(`\nPróximos pasos:`);
  console.log(`   1. Verificar contratos en el explorer`);
  console.log(`   2. Configurar GOVERNANCE_ADDRESS (multisig / Safe)`);
  console.log(`   3. Asignar REFI_EXECUTOR_ROLE al relayer de GenLayer`);
  console.log(`   4. Deploy ReFiGovernanceISC en GenLayer Studionet\n`);

  // Guardar resumen global
  saveDeployment(network.name, "deployment_summary", "N/A", {
    network: network.name,
    deployedAt: new Date().toISOString(),
    contracts: {
      MockUSDC: usdcAddress,
      HolonTokenFactory: factoryAddress,
      CommonStakePool: commonPoolAddress,
      ...Object.fromEntries(
        Object.entries(mmaPoolAddresses).map(([id, addr]) => [`HoFiMMAPool_${id}`, addr])
      ),
    },
  });
}

main().catch((error) => {
  console.error("❌ Error:", error);
  process.exit(1);
});
