require("@nomicfoundation/hardhat-toolbox");

// Fallback a clave dummy para que `hardhat compile` funcione sin PRIVATE_KEY.
// En deploy real, PRIVATE_KEY debe estar seteada en el entorno.
const PRIVATE_KEY = process.env.PRIVATE_KEY || "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";

module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      viaIR: true,
    },
  },
  networks: {
    ethSepolia: {
      url: "https://ethereum-sepolia-rpc.publicnode.com",
      accounts: [PRIVATE_KEY],
      chainId: 11155111,
      timeout: 60000,
    },
    baseSepolia: {
      url: "https://sepolia.base.org",
      accounts: [PRIVATE_KEY],
      chainId: 84532,
      timeout: 60000,
    },
    // HolonChain — activar cuando bootstrap P-Chain = true
    holonchain: {
      url: "http://34.69.27.168:9650/ext/bc/2iQdZzzFtdvWH2hpDm5ReijM8AtLdVmVMxGV4j4pWMz3LpoRzZ/rpc",
      accounts: [PRIVATE_KEY],
      chainId: 73621,
      timeout: 60000,
    },
  },
};
