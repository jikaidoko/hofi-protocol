const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("\nDeployando contratos HoFi con:", deployer.address);
  console.log("Balance:", hre.ethers.formatEther(
    await hre.ethers.provider.getBalance(deployer.address)
  ), "ETH\n");

  // 1. HoCaToken
  console.log("1/3 Deployando HoCaToken...");
  const HoCaToken = await hre.ethers.getContractFactory("HoCaToken");
  const hocaToken = await HoCaToken.deploy();
  await hocaToken.waitForDeployment();
  const hocaAddress = await hocaToken.getAddress();
  console.log("   HoCaToken:", hocaAddress);

  // 2. HolonSBT
  console.log("2/3 Deployando HolonSBT...");
  const HolonSBT = await hre.ethers.getContractFactory("HolonSBT");
  const holonSBT = await HolonSBT.deploy();
  await holonSBT.waitForDeployment();
  const sbtAddress = await holonSBT.getAddress();
  console.log("   HolonSBT:", sbtAddress);

  // 3. TaskRegistry
  console.log("3/3 Deployando TaskRegistry...");
  const TaskRegistry = await hre.ethers.getContractFactory("TaskRegistry");
  const taskRegistry = await TaskRegistry.deploy(hocaAddress, sbtAddress);
  await taskRegistry.waitForDeployment();
  const registryAddress = await taskRegistry.getAddress();
  console.log("   TaskRegistry:", registryAddress);

  // Otorgar roles
  console.log("\nConfigurando roles...");
  const MINTER_ROLE = hre.ethers.keccak256(hre.ethers.toUtf8Bytes("MINTER_ROLE"));
  await hocaToken.grantRole(MINTER_ROLE, registryAddress);
  console.log("   TaskRegistry puede mintear HoCa");

  console.log("\n=== DEPLOY COMPLETADO ===");
  console.log("HoCaToken:    ", hocaAddress);
  console.log("HolonSBT:     ", sbtAddress);
  console.log("TaskRegistry: ", registryAddress);
  console.log("\nGuarda estas direcciones en tu memory.md");
  console.log("Verifica en: https://sepolia.basescan.org/address/" + hocaAddress);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
