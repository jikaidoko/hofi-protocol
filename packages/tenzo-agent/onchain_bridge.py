"""
HoFi · On-chain Bridge — HolonChain
Conecta el Tenzo Agent a CuidaCoin (HolonToken) en HolonChain.
Cuando Tenzo aprueba una tarea, este bridge mintea HOCA directamente
llamando a mint() en el contrato CuidaCoin del holon correspondiente.

Red: HolonChain (chainId 73621)
RPC: http://104.154.138.51:9650/ext/bc/czfN9bkKgPqpJ5SxegkDCRSSWuSPGDveAB6nLwtSPyWybRwHD/rpc

Contratos HolonChain (21-abr-2026):
  CuidaCoin (familia-mourino): 0xe06eAf03992d9B3D2BCAC219D0838b34A4dBEA75
  BrazoCoin  (archi-brazo):    0xA16DF94634E2Dd09Bf311Ec0d88EDe41f3F88E91

Prerequisito: TENZO_WALLET debe tener MINTER_ROLE en el contrato.
  grantRole(MINTER_ROLE, tenzo_wallet) desde el deployer (governance).
"""
import os
import logging
from web3 import Web3

logger = logging.getLogger("TenzoBridge")

# ── Config ─────────────────────────────────────────────────────────────────
HOLONCHAIN_RPC   = (
    "http://104.154.138.51:9650/ext/bc/"
    "czfN9bkKgPqpJ5SxegkDCRSSWuSPGDveAB6nLwtSPyWybRwHD/rpc"
)
RPC_URL          = os.getenv("ETH_RPC_URL", HOLONCHAIN_RPC)
CHAIN_ID         = int(os.getenv("CHAIN_ID", "73621"))
TENZO_WALLET_KEY = os.getenv("TENZO_WALLET_KEY", "").strip()

# CuidaCoin del holon activo — familia-mourino por defecto
HOCA_TOKEN       = os.getenv(
    "HOCA_TOKEN_ADDRESS", "0xe06eAf03992d9B3D2BCAC219D0838b34A4dBEA75"
)

# Mapa holon_id -> direccion CuidaCoin en HolonChain
HOLON_TOKENS = {
    "familia-mourino": "0xe06eAf03992d9B3D2BCAC219D0838b34A4dBEA75",
    "archi-brazo":     "0xA16DF94634E2Dd09Bf311Ec0d88EDe41f3F88E91",
}

# ABI minimo de HolonToken (ERC20 + AccessControl + mint)
HOLON_TOKEN_ABI = [
    {
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "MINTER_ROLE",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "role", "type": "bytes32"}, {"name": "account", "type": "address"}],
        "name": "hasRole",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class TenzoBridge:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to HolonChain at {RPC_URL}")
        if not TENZO_WALLET_KEY:
            raise ValueError("TENZO_WALLET_KEY no configurado")
        self.account = self.w3.eth.account.from_key(TENZO_WALLET_KEY)
        # Contrato por defecto (familia-mourino / CuidaCoin)
        self._token_cache: dict[str, object] = {}
        logger.info(
            "TenzoBridge conectado a HolonChain | wallet: %s | chain: %s",
            self.account.address, CHAIN_ID,
        )

    def _get_token(self, holon_id: str):
        """Retorna el contrato HolonToken para el holon dado."""
        if holon_id not in self._token_cache:
            address = HOLON_TOKENS.get(holon_id, HOCA_TOKEN)
            self._token_cache[holon_id] = self.w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=HOLON_TOKEN_ABI,
            )
        return self._token_cache[holon_id]

    def has_minter_role(self, holon_id: str = "familia-mourino") -> bool:
        """Verifica que el wallet del Tenzo tiene MINTER_ROLE."""
        try:
            token = self._get_token(holon_id)
            role = token.functions.MINTER_ROLE().call()
            return token.functions.hasRole(role, self.account.address).call()
        except Exception as e:
            logger.error("Error verificando MINTER_ROLE: %s", e)
            return False

    def approve_task_onchain(
        self,
        executor:        str,
        holon_id:        str,
        categoria:       str,
        duracion_horas:  float,
        recompensa_hoca: float,
        razonamiento:    str,
    ) -> dict:
        """
        Mintea HOCA al executor cuando Tenzo aprueba una tarea.
        Llama a mint(executor, recompensa_wei) en el HolonToken del holon.
        """
        token          = self._get_token(holon_id)
        token_address  = HOLON_TOKENS.get(holon_id, HOCA_TOKEN)
        recompensa_wei = int(recompensa_hoca * 10**18)

        tx = token.functions.mint(
            Web3.to_checksum_address(executor),
            recompensa_wei,
        ).build_transaction({
            "from":    self.account.address,
            "nonce":   self.w3.eth.get_transaction_count(self.account.address),
            "gas":     150000,
            "chainId": CHAIN_ID,
        })
        signed  = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        logger.info(
            "HOCA minteado | executor=%s holon=%s hoca=%.2f tx=%s",
            executor, holon_id, recompensa_hoca, tx_hash.hex(),
        )
        return {
            "tx_hash":     tx_hash.hex(),
            "block":       receipt["blockNumber"],
            "gas_used":    receipt["gasUsed"],
            "hoca_minted": recompensa_hoca,
            "token":       token_address,
            "network":     "holonchain",
        }

    def get_stats(self, holon_id: str = "familia-mourino") -> dict:
        """Total supply del HolonToken del holon."""
        token = self._get_token(holon_id)
        supply = token.functions.totalSupply().call()
        return {
            "holon_id":     holon_id,
            "total_supply": supply / 10**18,
            "token":        HOLON_TOKENS.get(holon_id, HOCA_TOKEN),
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
        logger.warning("On-chain bridge no disponible: %s", e)
        return None
