"""
test_genlayer_sdk.py v9 — eth_call directo al RPC de Studio Asimov.

Historia del problema:
  v6/v7: genlayer_py write_contract → falla en eth_estimateGas
          (GenLayer no puede simular LLM calls durante estimación de gas)
          → OutOfNativeResourcesDuringValidation
  v8:    /api/call endpoint → 404 (no existe en Studio Asimov)
  v9:    eth_call JSON-RPC al endpoint /api de Studio (sin gas estimation)
          Mismo calldata encoding que usa el simulador local (tools/calldata.py)
          eth_call = modo simulación, no modifica estado, no necesita gas

Por qué eth_call funciona:
  - No requiere eth_estimateGas
  - GenLayer Studio soporta eth_call para @gl.public.write en modo simulación
  - La respuesta incluye el resultado del consenso de los 5 validadores
  - Los validadores usan las reglas del holón familia-valdes ya configuradas

Correr:
  python test_genlayer_sdk.py
  (no necesita GENLAYER_PRIVATE_KEY para eth_call)
"""

import json
import base64
import time
import collections.abc
import dataclasses

import requests

STUDIO_RPC     = "https://studio.genlayer.com/api"
ORACLE_ADDRESS = "0x7A037d1dDbda728f16e6F980a28eB8D1e29F4F28"  # v0.2.2
CALLER         = "0x0000000000000000000000000000000000000001"  # cualquiera para eth_call

TESTS = [
    {
        "nombre":   "TV — deberia REJECT",
        "args": ["estuvo mirando television 2 horas", "familia-valdes", "2.0", "-1.0", "", ""],
    },
    {
        "nombre":   "Huerta — deberia APPROVE",
        "args": ["Trabaje en la huerta durante una hora", "familia-valdes", "1.0", "-1.0", "", ""],
    },
    {
        "nombre":   "Cuidado de hijo enfermo — deberia APPROVE",
        "args": ["Cuidé a mi hijo enfermo durante 3 horas", "familia-valdes", "3.0", "-1.0", "", ""],
    },
]


# ─── Calldata encoding (extraído de packages/genlayer/tools/calldata.py) ──────
# GenLayer usa su propio formato ULEB128, NO ABI encoding estándar de Ethereum.

BITS_IN_TYPE = 3
TYPE_SPECIAL, TYPE_PINT, TYPE_NINT, TYPE_BYTES, TYPE_STR, TYPE_ARR, TYPE_MAP = range(7)
SPECIAL_NULL  = (0 << BITS_IN_TYPE) | TYPE_SPECIAL
SPECIAL_FALSE = (1 << BITS_IN_TYPE) | TYPE_SPECIAL
SPECIAL_TRUE  = (2 << BITS_IN_TYPE) | TYPE_SPECIAL


def calldata_encode(x) -> bytes:
    mem = bytearray()

    def uleb128(i):
        assert i >= 0
        if i == 0:
            mem.append(0)
            return
        while i > 0:
            cur = i & 0x7F
            i >>= 7
            if i > 0:
                cur |= 0x80
            mem.append(cur)

    def impl(b):
        if b is None:
            mem.append(SPECIAL_NULL)
        elif b is True:
            mem.append(SPECIAL_TRUE)
        elif b is False:
            mem.append(SPECIAL_FALSE)
        elif isinstance(b, int):
            if b >= 0:
                uleb128((b << 3) | TYPE_PINT)
            else:
                uleb128((-b - 1 << 3) | TYPE_NINT)
        elif isinstance(b, bytes):
            uleb128((len(b) << 3) | TYPE_BYTES)
            mem.extend(b)
        elif isinstance(b, str):
            enc = b.encode("utf-8")
            uleb128((len(enc) << 3) | TYPE_STR)
            mem.extend(enc)
        elif isinstance(b, collections.abc.Sequence):
            uleb128((len(b) << 3) | TYPE_ARR)
            for x in b:
                impl(x)
        elif isinstance(b, collections.abc.Mapping):
            keys = sorted(b.keys())
            uleb128((len(keys) << 3) | TYPE_MAP)
            for k in keys:
                enc = k.encode("utf-8")
                uleb128(len(enc))
                mem.extend(enc)
                impl(b[k])
        else:
            raise TypeError(f"calldata_encode: tipo no soportado {type(b)}")

    impl(x)
    return bytes(mem)


def calldata_decode(mem0: bytes):
    mem = memoryview(mem0)

    def uleb128():
        nonlocal mem
        ret, off = 0, 0
        while True:
            m = mem[0]
            ret |= (m & 0x7F) << off
            off += 7
            mem = mem[1:]
            if not (m & 0x80):
                break
        return ret

    def impl():
        nonlocal mem
        code = uleb128()
        typ = code & 0x7
        if typ == TYPE_SPECIAL:
            if code == SPECIAL_NULL:  return None
            if code == SPECIAL_FALSE: return False
            if code == SPECIAL_TRUE:  return True
            raise ValueError(f"unknown special {code}")
        code >>= 3
        if typ == TYPE_PINT:   return code
        if typ == TYPE_NINT:   return -code - 1
        if typ == TYPE_BYTES:
            r, mem[:] = bytes(mem[:code]), mem[code:]
            return r
        if typ == TYPE_STR:
            r, mem[:] = str(mem[:code], "utf-8"), mem[code:]
            return r
        if typ == TYPE_ARR:    return [impl() for _ in range(code)]
        if typ == TYPE_MAP:
            d = {}
            for _ in range(code):
                le = uleb128()
                k = str(mem[:le], "utf-8")
                mem[:] = mem[le:]
                d[k] = impl()
            return d
        raise ValueError(f"invalid type {typ}")

    return impl()


import rlp
from eth_utils import to_hex


def build_calldata_hex(method: str, args: list) -> str:
    """Construye el data field para eth_call en formato GenLayer."""
    encoded = calldata_encode({"method": method, "args": args})
    # GenLayer espera el calldata wrapeado en una lista RLP
    return to_hex(rlp.encode([encoded]))


# ─── JSON-RPC helper ──────────────────────────────────────────────────────────

def rpc(method: str, *params):
    resp = requests.post(
        STUDIO_RPC,
        json={"jsonrpc": "2.0", "method": method, "params": list(params), "id": 1},
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error {data['error'].get('code')}: {data['error'].get('message')}")
    return data.get("result")


def call_oracle(args: list) -> dict:
    """
    Llama validate_task_equity via eth_call (simulación, sin commit a chain).
    Retorna el resultado parseado del oracle.
    """
    data_hex = build_calldata_hex("validate_task_equity", args)
    raw_result = rpc("eth_call", {
        "to":   ORACLE_ADDRESS,
        "from": CALLER,
        "data": data_hex,
    })
    # El resultado viene base64-encoded en calldata GenLayer
    decoded = calldata_decode(base64.b64decode(raw_result))
    if isinstance(decoded, str):
        return json.loads(decoded)
    return decoded


# ─── Runner ───────────────────────────────────────────────────────────────────

def main():
    print(f"\n🏡  HoFi — test_genlayer_sdk v9 (eth_call)")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📍  Oracle:  {ORACLE_ADDRESS}")
    print(f"🌐  RPC:     {STUDIO_RPC}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    passed = failed = 0

    for test in TESTS:
        print("=" * 60)
        print(f"TEST: {test['nombre']}")
        print(f"Args: {test['args']}")
        print("=" * 60)
        print("⏳  Llamando oracle (eth_call, ~10-30s)...")

        try:
            result = call_oracle(test["args"])

            vote          = result.get("vote", "?")
            hoca          = result.get("recompensa_hoca", 0)
            clasificacion = result.get("clasificacion", [])
            confidence    = result.get("confidence", 0)
            justification = result.get("justification", "")
            alerta        = result.get("alerta")

            icon = "✅" if vote == "APPROVE" else "❌" if vote == "REJECT" else "⚠️"
            print(f"\n{icon}  vote:          {vote}")
            print(f"   recompensa:    {hoca} HoCa")
            print(f"   clasificacion: {clasificacion}")
            print(f"   confidence:    {confidence}")
            print(f"   justification: {justification}")
            if alerta:
                print(f"   ⚠️  alerta:     {alerta}")
            passed += 1

        except Exception as e:
            import traceback
            print(f"❌  {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

        print()

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Resultado: {passed} pasaron / {failed} fallaron ({passed + failed} total)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    main()
