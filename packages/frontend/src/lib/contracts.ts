// HoFi - ABIs y direcciones de contratos (Ethereum Sepolia)

export const CHAIN_ID = parseInt(process.env.NEXT_PUBLIC_CHAIN_ID || '11155111');

export const CONTRACT_ADDRESSES = {
  HoCaToken:    process.env.NEXT_PUBLIC_HOCA_TOKEN    || '0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc',
  HolonSBT:     process.env.NEXT_PUBLIC_HOLON_SBT     || '0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036',
  TaskRegistry: process.env.NEXT_PUBLIC_TASK_REGISTRY || '0xd9B253E6E1b494a7f2030f9961101fC99d3fD038',
};

export const HOCA_TOKEN_ABI = [
  'function balanceOf(address owner) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)',
  'function symbol() view returns (string)',
  'function decimals() view returns (uint8)',
];

export const HOLON_SBT_ABI = [
  'function isMember(address account) view returns (bool)',
  'function getHolonId(address account) view returns (string)',
  'function mint(address to, string holonId, string role) returns (uint256)',
];

export const TASK_REGISTRY_ABI = [
  'function registerTask(string titulo, string categoria, uint256 recompensa) returns (uint256)',
  'function getTask(uint256 taskId) view returns (tuple(string titulo, address contributor, uint256 recompensa, bool completed))',
  'function completeTask(uint256 taskId)',
];
