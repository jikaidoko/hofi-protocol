# HolonChain — Avalanche L1 Deployment Guide

## Overview

HolonChain is HoFi Protocol's sovereign Avalanche L1 subnet.
Only addresses holding an active HolonSBT can interact with the liquidity pool.
Governance rules are embedded at the network infrastructure level.

**Chain ID:** 73621
**Block time:** 2 seconds
**Gas limit:** 15,000,000
**Min base fee:** 25 Gwei

---

## Prerequisites

```bash
# Install Avalanche CLI
curl -sSfL https://raw.githubusercontent.com/ava-labs/avalanche-cli/main/scripts/install.sh | sh

# Verify installation
avalanche --version

# Install avalanchego (node software)
# https://docs.avax.network/nodes/run/with-installer-script
```

---

## Step 1 — Create the Subnet

```bash
# Import the genesis config
avalanche blockchain create HolonChain \
  --genesis subnet-config.json \
  --evm \
  --chainid 73621 \
  --tokenName "HoCa" \
  --tokenSymbol "HOCA"
```

---

## Step 2 — Configure Validator Whitelist

HolonChain uses a permissioned validator set based on HolonSBT membership.
Only Holón members with active SBTs can become validators.

```bash
# Add initial validators (must hold HolonSBT)
# NodeID format: NodeID-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

avalanche blockchain addValidator HolonChain \
  --nodeID NodeID-YOUR_VALIDATOR_NODE_ID \
  --stakeAmount 1 \
  --startTime $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --endTime 2027-01-01T00:00:00Z

# Verify HolonSBT membership before adding:
# cast call 0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036 \
#   "isMember(address,string)" VALIDATOR_ADDRESS "holon-piloto" \
#   --rpc-url https://sepolia.ethereum-rpc.publicnode.com
```

---

## Step 3 — Deploy to Fuji Testnet

```bash
# Set network to Fuji (Avalanche testnet)
avalanche network fuji

# Deploy subnet
avalanche blockchain deploy HolonChain --fuji

# Fund your account with AVAX testnet tokens
# Faucet: https://faucet.avax.network
```

---

## Step 4 — Configure MetaMask

```
Network Name:    HolonChain (HoFi Protocol)
RPC URL:         https://subnets.avax.network/holonchain/rpc
Chain ID:        73621
Currency Symbol: HOCA
Explorer:        https://subnets.avax.network/holonchain
```

---

## Step 5 — Deploy HoFi Contracts to HolonChain

```bash
# Update hardhat.config.js with HolonChain network
# Then deploy
npx hardhat run scripts/deploy.js --network holonchain
```

---

## Validator Requirements

| Requirement | Value |
|-------------|-------|
| HolonSBT | Active membership required |
| Uptime | ≥ 95% |
| Stake | 1 AVAX minimum |
| Hardware | 8 vCPU, 16GB RAM, 500GB SSD |
| Network | 5 Mbps symmetric |

---

## HolonSBT Gating — How It Works

The validator whitelist is enforced at the subnet level.
Before adding a validator, governance must verify their HolonSBT:

```solidity
// HolonSBT.isMember(validatorWallet, holonId) must return true
// Contract: 0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036 (Ethereum Sepolia)
// Future: mirrored on HolonChain itself via bridge
```

---

## Security Notes

- ChainID 73621 should be verified against the Avalanche subnet registry before mainnet
- Validator rotation requires governance proposal + HolonSBT verification
- Private keys for initial validators must be stored in HSM or hardware wallet
- Monitor validator uptime via Avalanche explorer
- Gas parameters should be reviewed after first month of operation

---

## Roadmap

- **Phase 1 (now):** Deploy on Fuji testnet
- **Phase 2:** Deploy on Avalanche mainnet
- **Phase 3:** Bridge HoCaToken from Ethereum Sepolia to HolonChain
- **Phase 4:** Full ZK-gated validator set (Semaphore proofs)
