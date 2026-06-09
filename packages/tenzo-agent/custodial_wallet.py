#!/usr/bin/env python3
"""Servicio de wallets custodiales (Web3-agnósticos) — PyCardano.

Modelo dual del addendum:
- Usuarios que entran por **wallet (CIP-30)** → self-custody, sin custodial.
- Usuarios que entran por **voz/mail** → se les deriva una wallet **custodial**:
  una cuenta HD de UN único seed maestro (en KMS), con un **índice de derivación**
  por `person_id`. La clave NUNCA se guarda por usuario; se re-deriva on-demand.

Identidad: todo cuelga del `person_id` canónico (los canales —voz, telegram, mail,
wallet— son puentes a ese id en `member_identities`). La custodial se deriva del
`person_id`, así la persona es la misma a través de todos los métodos.

Graduación (custodial → self): cuando el usuario conecta SU wallet y firma
(Sign-In with Cardano = prueba de control), se barren los activos fungibles
(CUIDA + recibos + ADA) de la dirección custodial a la suya en UNA tx; la membresía
(soul-bound, en el validador) y la reputación quedan intactas porque están atadas
al `person_id`, no a la wallet.

Schema sugerido (Neon, tabla users / member_identities):
    derivation_index  INTEGER UNIQUE    -- índice HD; NULL si es self-custody
    cardano_address   TEXT              -- dirección actual del usuario
    custody_mode      VARCHAR(16)       -- 'custodial' | 'self'

Entorno:
    HOFI_MASTER_MNEMONIC   frase semilla maestra (en KMS/Secret Manager, NO en repo)

Setup (una vez): `python custodial_wallet.py gen-mnemonic` → guardar en KMS.
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Protocol

from pycardano import (
    Address,
    ExtendedSigningKey,
    HDWallet,
    Network,
    Transaction,
    TransactionBuilder,
)

# Cuenta 0, cadena externa (0), índice por persona: m/1852'/1815'/0'/0/<index>
DERIVATION_PATH = "m/1852'/1815'/0'/0/{index}"


class IndexStore(Protocol):
    """Lo implementa el Tenzo contra Neon (columna derivation_index)."""
    def get_index(self, person_id: str) -> Optional[int]: ...
    def assign_index(self, person_id: str) -> int: ...  # asigna el siguiente libre


class CustodialWallets:
    def __init__(self, mnemonic: Optional[str] = None, network: Network = Network.TESTNET):
        mnemonic = mnemonic or os.environ.get("HOFI_MASTER_MNEMONIC")
        if not mnemonic:
            raise ValueError("falta HOFI_MASTER_MNEMONIC (seed maestro, desde KMS)")
        self._hdw = HDWallet.from_mnemonic(mnemonic)
        self.network = network

    # ── derivación ──────────────────────────────────────────────────────────
    def _skey(self, index: int) -> ExtendedSigningKey:
        child = self._hdw.derive_from_path(DERIVATION_PATH.format(index=index))
        return ExtendedSigningKey.from_hdwallet(child)

    def address(self, index: int) -> Address:
        vkey = self._skey(index).to_verification_key()
        return Address(payment_part=vkey.hash(), network=self.network)

    def signing_key(self, index: int) -> ExtendedSigningKey:
        return self._skey(index)

    # ── alta / lookup por persona ─────────────────────────────────────────────
    def get_or_create(self, person_id: str, store: IndexStore) -> tuple[int, Address]:
        """Devuelve (index, address) de la custodial del person_id; la crea si no existe.
        Lazy: el Tenzo llama esto cuando la persona necesita por primera vez una
        dirección on-chain (p. ej. su primera recompensa)."""
        idx = store.get_index(person_id)
        if idx is None:
            idx = store.assign_index(person_id)
        return idx, self.address(idx)

    # ── graduación: barrer todo a una wallet self-custody ─────────────────────
    def build_graduation_tx(self, index: int, to_address: str, context) -> Transaction:
        """Barre los activos (CUIDA + recibos + ADA) de la custodial a `to_address`.
        Firma con la clave custodial re-derivada. La membresía soul-bound NO se
        toca (vive en el validador, atada al person_id)."""
        custodial_addr = self.address(index)
        utxos = context.utxos(str(custodial_addr))
        if not utxos:
            raise RuntimeError(f"custodial {custodial_addr} vacía; nada que graduar")
        builder = TransactionBuilder(context)
        for u in utxos:
            builder.add_input(u)
        # sin output explícito: todo el change (todos los assets) va a la nueva wallet
        return builder.build_and_sign(
            [self._skey(index)],
            change_address=Address.from_primitive(to_address),
            merge_change=True,
        )


# ── almacén en memoria (solo para pruebas; el Tenzo usa Neon) ──────────────────
class InMemoryIndexStore:
    def __init__(self) -> None:
        self._m: dict[str, int] = {}
        self._next = 0

    def get_index(self, person_id: str) -> Optional[int]:
        return self._m.get(person_id)

    def assign_index(self, person_id: str) -> int:
        idx = self._next
        self._m[person_id] = idx
        self._next += 1
        return idx


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "gen-mnemonic":
        print(HDWallet.generate_mnemonic())
        print("# Guardá esta frase en KMS/Secret Manager como HOFI_MASTER_MNEMONIC. NO la commitees.")
        return
    # demo: mostrar direcciones derivadas de un seed efímero
    cw = CustodialWallets(mnemonic=HDWallet.generate_mnemonic())
    store = InMemoryIndexStore()
    for pid in ["uma", "luna", "amaru"]:
        idx, addr = cw.get_or_create(pid, store)
        print(f"{pid:6} -> idx {idx} -> {addr}")


if __name__ == "__main__":
    main()
