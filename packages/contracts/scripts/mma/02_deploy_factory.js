// scripts/mma/02_deploy_factory.js
// Fase 1 — Deploy HolonTokenFactory
// Requiere: MockUSDC ya desplegado (lee deployments/<network>/MockUSDC.json)
// Uso: npx hardhat run scripts/mma/02_deploy_factory.js --network ethSepolia

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

function loadDeployment(networkName, contractName) {
  const filePath = path.join(__dirname, "../../deployments", networkName, `${contractName}.json`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Deployment no encontrado: ${filePath}\nEjecuta primero: 01_deploy_mock_usdc.js`);
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
  console.log(`\n🚀 Deploy HolonTokenFactory`);
  console.log(`   Red:        ${network.name}`);
  console.log(`   Deployer:   ${deployer.address}`);
  console.log(`   Balance:    ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  // Leer MockUSDC ya desplegado
  const usdcDeployment = loadDeployment(network.name, "MockUSDC");
  console.log(`   MockUSDC:   ${usdcDeployment.address}`);

  // Deploy HolonTokenFactory
  const Factory = await ethers.getContractFactory("HolonTokenFactory");
  const factory = await Factory.deploy(usdcDeployment.address);
  await factory.waitForDeployment();
  const factoryAddress = await factory.getAddress();

  console.log(`✅ HolonTokenFactory desplegado: ${factoryAddress}`);

  // Verificar roles
  const REGISTRAR_ROLE = await factory.REGISTRAR_ROLE();
  const hasRole = await factory.hasRole(REGISTRAR_ROLE, deployer.address);
  console.log(`   REGISTRAR_ROLE deployer: ${hasRole}`);

  // Guardar deployment
  saveDeployment(network.name, "HolonTokenFactory", factoryAddress, {
    deployer: deployer.address,
    baseStablecoin: usdcDeployment.address,
    blockNumber: (await ethers.provider.getBlockNumber()),
  });

  console.log(`\n📄 Deployment guardado en deployments/${network.name}/HolonTokenFactory.json`);
  console.log(`\nSiguiente paso:`);
  console.log(`   npx hardhat run scripts/mma/03_create_tokens.js --network ${network.name}\n`);

  return factoryAddress;
}

main().catch((error) => {
  console.error("❌ Error:", error);
  process.exit(1);
});
