// scripts/mma/01_deploy_mock_usdc.js
// Fase 1 — Deploy MockUSDC en testnet
// Uso: npx hardhat run scripts/mma/01_deploy_mock_usdc.js --network ethSepolia
//
// Guarda la dirección en deployments/<network>/MockUSDC.json
// para que los scripts siguientes la lean automáticamente.

const { ethers, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`\n🚀 Deploy MockUSDC`);
  console.log(`   Red:        ${network.name}`);
  console.log(`   Deployer:   ${deployer.address}`);
  console.log(`   Balance:    ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  const MockUSDC = await ethers.getContractFactory("MockUSDC");
  const usdc = await MockUSDC.deploy();
  await usdc.waitForDeployment();
  const usdcAddress = await usdc.getAddress();

  console.log(`✅ MockUSDC desplegado: ${usdcAddress}`);

  // Verificar suministro inicial
  const supply = await usdc.totalSupply();
  console.log(`   Supply inicial: ${ethers.formatUnits(supply, 6)} USDC`);

  // Guardar deployment
  saveDeployment(network.name, "MockUSDC", usdcAddress, {
    deployer: deployer.address,
    decimals: 6,
    initialSupply: supply.toString(),
    blockNumber: (await ethers.provider.getBlockNumber()),
  });

  console.log(`\n📄 Deployment guardado en deployments/${network.name}/MockUSDC.json`);
  console.log(`\nSiguiente paso: npm run mma:fase1 (scripts 02 y 03) o:`);
  console.log(`   npx hardhat run scripts/mma/02_deploy_factory.js --network ${network.name}\n`);

  return usdcAddress;
}

function saveDeployment(networkName, contractName, address, metadata = {}) {
  const dir = path.join(__dirname, "../../deployments", networkName);
  fs.mkdirSync(dir, { recursive: true });
  const filePath = path.join(dir, `${contractName}.json`);
  fs.writeFileSync(filePath, JSON.stringify({ address, ...metadata }, null, 2));
}

main().catch((error) => {
  console.error("❌ Error:", error);
  process.exit(1);
});
