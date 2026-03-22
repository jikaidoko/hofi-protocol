"""
HoFi · On-chain Bridge
Connects the Tenzo Agent to the TaskRegistry on Ethereum Sepolia.
When Tenzo approves a task, this bridge registers it on-chain
and mints HOCA to the executor.
"""
import os
import logging
from web3 import Web3

logger = logging.getLogger("TenzoBridge")

# ── Config ─────────────────────────────────────────────────────────────────
RPC_URL          = os.getenv("ETH_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
TENZO_WALLET_KEY = os.getenv("TENZO_WALLET_KEY", "").strip()
TASK_REGISTRY    = os.getenv("TASK_REGISTRY_ADDRESS", "0xd9B253E6E1b494a7f2030f9961101fC99d3fD038")
HOLON_SBT        = os.getenv("HOLON_SBT_ADDRESS",     "0x977E4eac99001aD8fe02D8d7f31E42E3d0Ffb036")
HOCA_TOKEN       = os.getenv("HOCA_TOKEN_ADDRESS",    "0x2a6339b63ec0344619923Dbf8f8B27cC5c9b40dc")

TASK_REGISTRY_ABI = [
    {
        "inputs": [
            {"name": "executor",       "type": "address"},
            {"name": "holonId",        "type": "string"},
            {"name": "categoria",      "type": "string"},
            {"name": "duracionHoras",  "type": "uint256"},
            {"name": "recompensaHoca", "type": "uint256"},
            {"name": "razonamiento",   "type": "string"},
        ],
        "name": "approveTask",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getStats",
        "outputs": [
            {"name": "_totalTasks",      "type": "uint256"},
            {"name": "_totalHocaMinted", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

HOLON_SBT_ABI = [
    {
        "inputs": [
            {"name": "to",      "type": "address"},
            {"name": "holonId", "type": "string"},
            {"name": "role",    "type": "string"},
        ],
        "name": "issue",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "holder",  "type": "address"},
            {"name": "holonId", "type": "string"},
        ],
        "name": "isMember",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class TenzoBridge:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to {RPC_URL}")
        if not TENZO_WALLET_KEY:
            raise ValueError("TENZO_WALLET_KEY not configured")
        self.account = self.w3.eth.account.from_key(TENZO_WALLET_KEY)
        self.registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(TASK_REGISTRY),
            abi=TASK_REGISTRY_ABI,
        )
        self.sbt = self.w3.eth.contract(
            address=Web3.to_checksum_address(HOLON_SBT),
            abi=HOLON_SBT_ABI,
        )
        logger.info("TenzoBridge connected | wallet: %s", self.account.address)

    def is_member(self, executor: str, holon_id: str) -> bool:
        try:
            return self.sbt.functions.isMember(
                Web3.to_checksum_address(executor), holon_id
            ).call()
        except Exception as e:
            logger.error("Membership check error: %s", e)
            return False

    def issue_sbt(self, member_address: str, holon_id: str, role: str = "member") -> str:
        tx = self.sbt.functions.issue(
            Web3.to_checksum_address(member_address), holon_id, role,
        ).build_transaction({
            "from":     self.account.address,
            "nonce":    self.w3.eth.get_transaction_count(self.account.address),
            "gas":      200000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed   = self.account.sign_transaction(tx)
        tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt  = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info("SBT issued | tx: %s", tx_hash.hex())
        return tx_hash.hex()

    def approve_task_onchain(
        self,
        executor:        str,
        holon_id:        str,
        categoria:       str,
        duracion_horas:  float,
        recompensa_hoca: float,
        razonamiento:    str,
    ) -> dict:
        recompensa_wei = int(recompensa_hoca * 10**18)
        duracion_int   = int(duracion_horas * 100)

        tx = self.registry.functions.approveTask(
            Web3.to_checksum_address(executor),
            holon_id, categoria, duracion_int,
            recompensa_wei, razonamiento[:200],
        ).build_transaction({
            "from":     self.account.address,
            "nonce":    self.w3.eth.get_transaction_count(self.account.address),
            "gas":      300000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed  = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info("Task approved on-chain | hoca=%s | tx=%s", recompensa_hoca, tx_hash.hex())
        return {
            "tx_hash":     tx_hash.hex(),
            "block":       receipt["blockNumber"],
            "gas_used":    receipt["gasUsed"],
            "explorer":    f"https://sepolia.etherscan.io/tx/{tx_hash.hex()}",
            "hoca_minted": recompensa_hoca,
        }

    def get_stats(self) -> dict:
        total_tasks, total_hoca = self.registry.functions.getStats().call()
        return {
            "total_tasks":       total_tasks,
            "total_hoca_minted": total_hoca / 10**18,
        }


_bridge = None

def get_bridge() -> "TenzoBridge | None":
    global _bridge
    if _bridge is not None:
        return _bridge
    if not TENZO_WALLET_KEY:
        return None
    try:
        _bridge = TenzoBridge()
        return _bridge
    except Exception as e:
        logger.warning("On-chain bridge unavailable: %s", e)
        return None
