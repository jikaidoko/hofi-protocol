"""
HoFi — test_genlayer_v10.py
Oracle: TenzoEquityOracle v0.2.2

Historial de errores y solucion final:
  v9  eth_call        → -32000 (eth_call no puede correr consenso LLM)
  v10a write_contract → OutOfNativeResourcesDuringValidation (eth_estimateGas falla)
  v10b write_contract → gas limit 500M > block limit 100M
  v10c write_contract → sin fondos (gasPrice != 0, fee > 0)
  v10d gen_call       → -32603 'type' (formato desconocido de args en gen_call)
  v10e tx finaliza OK pero result=5, eq_blocks_outputs identico, vote=UNKNOWN

Solucion final (patron de packages/genlayer/tools/request.py):
  eth_sendRawTransaction con gas=0, gasPrice=0 → fee = 0 → no requiere fondos.
  El tooling oficial del proyecto (request.py) usa exactamente este patron.
  Calldata: rlp.encode([calldata_encode({"method": ..., "args": ...})])
  La TX se firma con eth_account, se envía directa, se espera FINALIZED.

Diagnosticos v10e (output clave):
  - genvm_result.stderr mostro: calldata.DecodingError: unparsed end b'\x04args'... (decoded 45451)
  - BUG ENCONTRADO: data_hex = to_hex(rlp.encode([encoded])) enviaba el RLP wrapper.
    GenLayer pasa entry_data DIRECTAMENTE a calldata.decode() sin strip de RLP.
    Los bytes D9 98 (prefijo RLP de lista+string de 24 bytes) se decodifican como
    ULEB128 de 3 bytes → integer 45451 → calldata "decodeado" como entero, no dict.
    Por lo tanto: num_of_initial_validators=null, round_validators=[], NO_MAJORITY.

Fix v10f:
  data_hex = to_hex(calldata_encode(...))   # SIN rlp.encode wrapper
  GenLayer espera calldata CRUDO como data de la TX, no RLP([calldata_bytes]).
  packages/genlayer/tools/transactions.py → encode_transaction_data() usa rlp.encode
  pero eso es para la estructura de parametros RPC, no para el data field de la TX.

Dependencias:
  pip install eth-account rlp eth-utils   (probablemente ya instaladas)
"""

import json
import time
import base64
import collections.abc

from eth_account import Account
from eth_utils import to_hex
import rlp
from genlayer_py import create_client, create_account as gl_create_account, testnet_bradbury

ORACLE_ADDRESS  = "0x68396D5f7e1887054F54f9a55A71faE08C6a07B7"  # v0.2.2 en Bradbury (deploy 3-abril-2026)
POLL_INTERVAL   = 8    # segundos entre polls de la TX
POLL_RETRIES    = 40   # 40 * 8s = 320s max de espera
HTTP_TIMEOUT    = 30

# Cliente Bradbury (chainId=4221) — usa provider.make_request para los JSON-RPC calls
_GL_CLIENT = create_client(chain=testnet_bradbury, account=gl_create_account())

TESTS = [
    {
        "nombre":   "TV — deberia REJECT",
        "args":     ["estuvo mirando television 2 horas", "familia-valdes", "2.0", "-1.0", "", ""],
        "esperado": "REJECT",
    },
    {
        "nombre":   "Huerta — deberia APPROVE",
        "args":     ["Trabaje en la huerta durante una hora", "familia-valdes", "1.0", "-1.0", "", ""],
        "esperado": "APPROVE",
    },
    {
        "nombre":   "Cuidado hijo enfermo — deberia APPROVE",
        "args":     ["Cuide a mi hijo enfermo durante 3 horas", "familia-valdes", "3.0", "-1.0", "", ""],
        "esperado": "APPROVE",
    },
]


# ── Calldata encoder (copia de packages/genlayer/tools/calldata.py) ───────────

BITS_IN_TYPE = 3
TYPE_SPECIAL = 0; TYPE_PINT = 1; TYPE_NINT = 2
TYPE_BYTES   = 3; TYPE_STR  = 4; TYPE_ARR  = 5; TYPE_MAP = 6
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
            cur = i & 0x7F; i >>= 7
            if i > 0: cur |= 0x80
            mem.append(cur)

    def impl(b):
        if b is None:           mem.append(SPECIAL_NULL)
        elif b is True:         mem.append(SPECIAL_TRUE)
        elif b is False:        mem.append(SPECIAL_FALSE)
        elif isinstance(b, int):
            uleb128(((b << 3) | TYPE_PINT) if b >= 0 else ((-b-1 << 3) | TYPE_NINT))
        elif isinstance(b, bytes):
            uleb128((len(b) << 3) | TYPE_BYTES); mem.extend(b)
        elif isinstance(b, str):
            enc = b.encode("utf-8"); uleb128((len(enc) << 3) | TYPE_STR); mem.extend(enc)
        elif isinstance(b, collections.abc.Sequence):
            uleb128((len(b) << 3) | TYPE_ARR)
            for x in b: impl(x)
        elif isinstance(b, collections.abc.Mapping):
            keys = sorted(b.keys())
            uleb128((len(keys) << 3) | TYPE_MAP)
            for k in keys:
                enc = k.encode("utf-8"); uleb128(len(enc)); mem.extend(enc); impl(b[k])
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
            m = mem[0]; ret |= (m & 0x7F) << off; off += 7; mem = mem[1:]
            if not (m & 0x80): break
        return ret

    def impl():
        nonlocal mem
        code = uleb128(); typ = code & 0x7
        if typ == TYPE_SPECIAL:
            if code == SPECIAL_NULL:  return None
            if code == SPECIAL_FALSE: return False
            if code == SPECIAL_TRUE:  return True
            raise ValueError(f"unknown special {code}")
        code >>= 3
        if typ == TYPE_PINT: return code
        if typ == TYPE_NINT: return -code - 1
        if typ == TYPE_BYTES: r = bytes(mem[:code]); mem = mem[code:]; return r
        if typ == TYPE_STR:   r = str(mem[:code], "utf-8"); mem = mem[code:]; return r
        if typ == TYPE_ARR:   return [impl() for _ in range(code)]
        if typ == TYPE_MAP:
            d = {}
            for _ in range(code):
                le = uleb128(); k = str(mem[:le], "utf-8"); mem = mem[le:]; d[k] = impl()
            return d
        raise ValueError(f"invalid type {typ}")

    return impl()


# ── JSON-RPC helper ───────────────────────────────────────────────────────────

def rpc(method, *params):
    data = _GL_CLIENT.provider.make_request(method, list(params))
    if "error" in data:
        code = data["error"].get("code")
        msg  = data["error"].get("message", "unknown")
        raise RuntimeError(f"RPC {method} error {code}: {msg}")
    return data.get("result")


# ── Oracle call (patron de request.py: gas=0, gasPrice=0, sin fondos) ─────────

def call_oracle(args: list) -> dict:
    """
    Llama validate_task_equity via eth_sendRawTransaction con gas=0, gasPrice=0.

    Por que gas=0/gasPrice=0:
      packages/genlayer/tools/request.py (tooling oficial del proyecto)
      firma todas las TXs con gas=0 y gasPrice=0. Esto hace que
      fee = gas * gasPrice = 0, por lo que la cuenta no necesita fondos.
      GenLayer Studio Studionet Asimov acepta TXs sin gas porque los ISCs
      con LLM no usan el modelo de gas de EVM.
    """
    account = Account.create()

    # Obtener chain ID y nonce
    chain_id_hex = rpc("eth_chainId")
    chain_id     = int(chain_id_hex, 16) if isinstance(chain_id_hex, str) else chain_id_hex
    nonce_raw    = rpc("eth_getTransactionCount", account.address)
    nonce        = int(nonce_raw, 16) if isinstance(nonce_raw, str) else (nonce_raw or 0)

    print(f"  Cuenta: {account.address} | chainId: {chain_id} | nonce: {nonce}")

    # Construir calldata (mismo formato que request.py)
    encoded  = calldata_encode({"method": "validate_task_equity", "args": args})
    data_hex = to_hex(encoded)  # SIN rlp.encode: GenLayer espera calldata crudo, NO RLP-wrapped

    # Bradbury requiere gas > 0 (intrinsic gas min ~21000). gasPrice=0 → fee=0, sin fondos.
    tx = {
        "nonce":    nonce,
        "gasPrice": 0,
        "gas":      90_000_000,
        "to":       ORACLE_ADDRESS,
        "value":    0,
        "data":     data_hex,
        "chainId":  chain_id,
    }
    signed  = Account.sign_transaction(tx, account.key)
    raw_hex = to_hex(signed.raw_transaction)
    print(f"  TX firmada (gas=90M, gasPrice=0) | data: {data_hex[:60]}...")

    # Enviar
    tx_hash = rpc("eth_sendRawTransaction", raw_hex)
    print(f"  TX enviada: {tx_hash}")
    print(f"  Esperando FINALIZED (hasta {POLL_RETRIES * POLL_INTERVAL}s)...")

    # Esperar finalizacion
    for attempt in range(POLL_RETRIES):
        time.sleep(POLL_INTERVAL)
        tx_data = rpc("eth_getTransactionByHash", tx_hash)
        if not tx_data:
            print(f"  [{attempt+1}/{POLL_RETRIES}] TX pendiente...")
            continue
        status = tx_data.get("status", "")
        print(f"  [{attempt+1}/{POLL_RETRIES}] status: {status}")
        if status == "FINALIZED":
            return tx_data
        if status in ("REJECTED", "FAILED", "ERROR"):
            raise RuntimeError(f"TX {status}: {json.dumps(tx_data)[:300]}")

    raise TimeoutError(f"TX {tx_hash} no finalizo en {POLL_RETRIES * POLL_INTERVAL}s")


def diagnose_contract():
    """
    Diagnostico profundo v10g:
      1. View functions (confirmar calldata)
      2. eth_call sobre validate_task_equity — capturar error response COMPLETO
         (en versiones anteriores genvm_result.stderr aparecia en el error de eth_call)
      3. Comparar eth_sendRawTransaction con calldata CRUDO vs RLP-wrapped
         (el tooling oficial usa rlp.encode([calldata]) — probar si ESO funciona)
      4. gen_call (el otro metodo RPC que GenLayer expone)
    """
    print()
    print("=" * 70)
    print("=== DIAGNOSTICO PROFUNDO v10g ===")
    print("=" * 70)

    dummy = Account.create()

    # ── 1. View functions ────────────────────────────────────────────────
    print("\n--- 1. View functions (calldata crudo) ---")
    for method, args in [("get_owner", []), ("get_holon_rules", ["familia-valdes"])]:
        encoded  = calldata_encode({"method": method, "args": args})
        data_hex = to_hex(encoded)
        try:
            data = _GL_CLIENT.provider.make_request(
                "eth_call",
                [{"to": ORACLE_ADDRESS, "from": dummy.address, "data": data_hex}],
            )
            if "error" in data:
                print(f"  {method}: ERROR {json.dumps(data['error'])[:500]}")
            else:
                raw_result = data.get("result", "")
                if raw_result:
                    try:
                        raw_bytes = bytes.fromhex(raw_result[2:]) if raw_result.startswith("0x") else base64.b64decode(raw_result)
                        decoded = calldata_decode(raw_bytes)
                        print(f"  {method}: OK → {str(decoded)[:200]}")
                    except Exception as e:
                        print(f"  {method}: decode error {e} | raw={raw_result[:100]}")
                else:
                    print(f"  {method}: resultado vacio")
        except Exception as e:
            print(f"  {method}: excepcion {e}")

    # ── 2. eth_call sobre validate_task_equity — VOLCAR ERROR COMPLETO ──
    print("\n--- 2. eth_call sobre validate_task_equity (capturar stderr) ---")
    test_args = ["Trabaje en la huerta una hora", "familia-valdes", "1.0", "-1.0", "", ""]
    encoded = calldata_encode({"method": "validate_task_equity", "args": test_args})
    for label, data_hex in [("crudo", to_hex(encoded)), ("rlp_wrapped", to_hex(rlp.encode([encoded])))]:
        print(f"\n  [{label}] data_hex={data_hex[:80]}...")
        try:
            data = _GL_CLIENT.provider.make_request(
                "eth_call",
                [{"to": ORACLE_ADDRESS, "from": dummy.address, "data": data_hex}],
            )
            # VOLCAR TODA la respuesta — buscamos stderr/genvm_result
            resp_str = json.dumps(data, indent=2, default=str)
            print(f"  [{label}] response ({len(resp_str)} chars):")
            # Mostrar hasta 3000 chars
            print(resp_str[:3000])
            if len(resp_str) > 3000:
                print(f"  ... [truncado, total {len(resp_str)} chars]")
        except TimeoutError:
            print(f"  [{label}] TIMEOUT (120s)")
        except Exception as e:
            print(f"  [{label}] excepcion: {type(e).__name__}: {e}")

    # ── 3. eth_sendRawTransaction: crudo vs RLP wrapper ──────────────────
    print("\n--- 3. eth_sendRawTransaction: crudo vs RLP wrapper ---")
    test_args_tx = ["test diagnostico corto", "familia-valdes", "1.0", "-1.0", "", ""]
    encoded_tx = calldata_encode({"method": "validate_task_equity", "args": test_args_tx})

    for label, data_hex in [("crudo", to_hex(encoded_tx)), ("rlp_wrapped", to_hex(rlp.encode([encoded_tx])))]:
        print(f"\n  [{label}] Enviando TX con data={data_hex[:60]}...")
        try:
            account = Account.create()
            chain_id_hex = rpc("eth_chainId")
            chain_id = int(chain_id_hex, 16) if isinstance(chain_id_hex, str) else chain_id_hex
            nonce_raw = rpc("eth_getTransactionCount", account.address)
            nonce = int(nonce_raw, 16) if isinstance(nonce_raw, str) else (nonce_raw or 0)
            tx = {
                "nonce": nonce, "gasPrice": 0, "gas": 90_000_000,
                "to": ORACLE_ADDRESS, "value": 0,
                "data": data_hex, "chainId": chain_id,
            }
            signed = Account.sign_transaction(tx, account.key)
            raw_hex = to_hex(signed.raw_transaction)
            tx_hash = rpc("eth_sendRawTransaction", raw_hex)
            print(f"  [{label}] TX hash: {tx_hash}")

            # Polling hasta 120s
            for attempt in range(15):
                time.sleep(8)
                tx_data = rpc("eth_getTransactionByHash", tx_hash)
                if not tx_data:
                    continue
                status = tx_data.get("status", "")
                if status == "FINALIZED":
                    result = tx_data.get("result")
                    result_name = tx_data.get("result_name", "?")
                    num_rounds = tx_data.get("num_of_rounds", "?")
                    num_init = tx_data.get("num_of_initial_validators")
                    eq_out = tx_data.get("eq_blocks_outputs", "")
                    cd = tx_data.get("consensus_data")
                    print(f"  [{label}] FINALIZED: result={result} ({result_name})")
                    print(f"  [{label}]   num_of_rounds={num_rounds}, num_of_initial_validators={num_init}")
                    print(f"  [{label}]   eq_blocks_outputs={eq_out[:200] if eq_out else 'vacio'}")

                    # Decodificar eq_blocks_outputs para buscar errores
                    if eq_out and eq_out.startswith("0x") and len(eq_out) > 4:
                        try:
                            raw_bytes = bytes.fromhex(eq_out[2:])
                            decoded_eq = rlp.decode(raw_bytes)
                            print(f"  [{label}]   eq decoded: {decoded_eq!r}")
                        except Exception as e:
                            print(f"  [{label}]   eq decode error: {e}")

                    if cd:
                        cd_str = json.dumps(cd, default=str)
                        print(f"  [{label}]   consensus_data: {cd_str[:800]}")
                    else:
                        print(f"  [{label}]   consensus_data: null")

                    # Buscar stderr en TODOS los campos del receipt
                    _search_stderr(tx_data, label)
                    break
                elif status in ("REJECTED", "FAILED", "ERROR"):
                    print(f"  [{label}] {status}!")
                    _search_stderr(tx_data, label)
                    break
            else:
                print(f"  [{label}] TIMEOUT (120s)")
        except Exception as e:
            print(f"  [{label}] error: {type(e).__name__}: {e}")

    # ── 4. gen_call (metodo alternativo) ─────────────────────────────────
    print("\n--- 4. gen_call ---")
    try:
        call_obj = {
            "to": ORACLE_ADDRESS, "from": dummy.address,
            "function": "validate_task_equity",
            "args": test_args, "value": "0",
        }
        data = _GL_CLIENT.provider.make_request("gen_call", [call_obj])
        resp_str = json.dumps(data, indent=2, default=str)
        print(f"  gen_call response ({len(resp_str)} chars):")
        print(resp_str[:2000])
    except Exception as e:
        print(f"  gen_call excepcion: {e}")

    print()
    print("=" * 70)
    print("=== FIN DIAGNOSTICO ===")
    print("=" * 70)
    print()


def _search_stderr(tx_data: dict, label: str):
    """Busca genvm_result.stderr recursivamente en el receipt."""
    def _recurse(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("stderr", "error", "traceback", "exception"):
                    if v:
                        print(f"  [{label}]   FOUND {path}.{k}: {str(v)[:500]}")
                elif k == "genvm_result" and isinstance(v, dict):
                    stderr = v.get("stderr")
                    if stderr:
                        print(f"  [{label}]   FOUND {path}.genvm_result.stderr: {stderr[:500]}")
                _recurse(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _recurse(item, f"{path}[{i}]")

    _recurse(tx_data, "receipt")


def parsear_tx_result(tx_data: dict) -> dict:
    """
    Extrae el resultado de validate_task_equity del receipt de la TX.
    v10e: vuelca el receipt COMPLETO + decodifica eq_blocks_outputs via RLP.
    """
    # ── 1. Volcado completo del receipt ───────────────────────────────────────
    print()
    print("  ── RECEIPT COMPLETO (todas las claves) ──")
    for k, v in tx_data.items():
        v_str = json.dumps(v) if not isinstance(v, str) else v
        # Truncar solo campos muy largos
        if len(v_str) > 600:
            v_str = v_str[:600] + "... [truncado]"
        print(f"  {k}: {v_str}")
    print("  ── FIN RECEIPT ──")
    print()

    # ── 2. Intentar decodificar eq_blocks_outputs via RLP ────────────────────
    eq_raw = tx_data.get("eq_blocks_outputs")
    if eq_raw and isinstance(eq_raw, str) and eq_raw.startswith("0x"):
        print(f"  eq_blocks_outputs hex: {eq_raw}")
        try:
            import rlp as _rlp
            raw_bytes = bytes.fromhex(eq_raw[2:])
            decoded_rlp = _rlp.decode(raw_bytes)
            print(f"  eq_blocks_outputs RLP decoded: {decoded_rlp!r}")
            # Intentar calldata_decode en cada elemento
            for i, item in enumerate(decoded_rlp if isinstance(decoded_rlp, list) else [decoded_rlp]):
                if isinstance(item, bytes) and item:
                    try:
                        cd = calldata_decode(item)
                        print(f"    item[{i}] calldata_decode: {str(cd)[:200]}")
                        r = _decode_result(cd)
                        if r.get("vote") in ("APPROVE", "REJECT"):
                            return r
                    except Exception as e:
                        print(f"    item[{i}] calldata_decode error: {e} | bytes={item.hex()[:60]}")
                elif isinstance(item, list):
                    for j, sub in enumerate(item):
                        if isinstance(sub, bytes) and sub:
                            try:
                                cd = calldata_decode(sub)
                                print(f"    item[{i}][{j}] calldata_decode: {str(cd)[:200]}")
                                r = _decode_result(cd)
                                if r.get("vote") in ("APPROVE", "REJECT"):
                                    return r
                            except Exception as e:
                                print(f"    item[{i}][{j}] calldata_decode error: {e}")
        except Exception as e:
            print(f"  eq_blocks_outputs RLP decode error: {e}")

    # ── 3. Intentar resultado del campo "result" directamente ────────────────
    result_field = tx_data.get("result")
    print(f"  result field: {result_field!r} (type={type(result_field).__name__})")
    if isinstance(result_field, str) and result_field.startswith("0x"):
        try:
            raw_bytes = bytes.fromhex(result_field[2:])
            # Intentar calldata_decode directo
            try:
                cd = calldata_decode(raw_bytes)
                print(f"  result calldata_decode: {str(cd)[:300]}")
                r = _decode_result(cd)
                if r.get("vote") in ("APPROVE", "REJECT"):
                    return r
            except Exception:
                pass
            # Intentar RLP+calldata
            try:
                import rlp as _rlp
                items = _rlp.decode(raw_bytes)
                for item in (items if isinstance(items, list) else [items]):
                    if isinstance(item, bytes) and item:
                        cd = calldata_decode(item)
                        print(f"  result rlp+calldata: {str(cd)[:300]}")
                        r = _decode_result(cd)
                        if r.get("vote") in ("APPROVE", "REJECT"):
                            return r
            except Exception:
                pass
        except Exception as e:
            print(f"  result decode error: {e}")

    # ── 4. Buscar en consensus_data ───────────────────────────────────────────
    consensus = tx_data.get("consensus_data")
    if isinstance(consensus, dict):
        for sub in ("final_result", "result", "leader_result", "output", "data"):
            val = consensus.get(sub)
            if val is not None:
                print(f"  → consensus_data.{sub}: {str(val)[:300]}")
                r = _decode_result(val)
                if r.get("vote") in ("APPROVE", "REJECT"):
                    return r

    # ── 5. Buscar en messages ─────────────────────────────────────────────────
    messages = tx_data.get("messages")
    if messages:
        for i, msg in enumerate(messages if isinstance(messages, list) else [messages]):
            print(f"    message[{i}]: {str(msg)[:200]}")
            r = _decode_result(msg)
            if r.get("vote") in ("APPROVE", "REJECT"):
                return r

    print(f"  *** No se encontro vote en ningún campo. result={result_field!r} ***")
    return {"vote": "UNKNOWN", "_result_raw": result_field}


def _decode_result(val) -> dict:
    """Decodifica el resultado que puede ser dict, JSON string, o base64+calldata."""
    if isinstance(val, dict) and "vote" in val:
        return val
    if isinstance(val, str):
        # Intentar JSON directo
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # Intentar base64 + calldata_decode (como en eth_call)
        try:
            decoded = calldata_decode(base64.b64decode(val))
            if isinstance(decoded, str):
                return json.loads(decoded)
            return decoded
        except Exception:
            pass
    return {"vote": "UNKNOWN", "_raw": str(val)[:200]}


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print()
    print("HoFi — test_genlayer v10 (eth_sendRawTransaction, gas=0)")
    print("=" * 60)
    print(f"Oracle:  {ORACLE_ADDRESS}")
    print(f"Metodo:  eth_sendRawTransaction | gas=0, gasPrice=0, sin fondos")
    print(f"Patron:  packages/genlayer/tools/request.py (tooling oficial)")
    print("=" * 60)

    diagnose_contract()

    import sys
    if "--diag-only" in sys.argv:
        print("\n[--diag-only] Saliendo tras diagnostico.")
        return

    pasaron = 0
    fallaron = 0

    for i, test in enumerate(TESTS, start=1):
        print()
        print("-" * 60)
        print(f"TEST {i}: {test['nombre']}")
        print(f"Args:    {test['args']}")
        print(f"Espera:  {test['esperado']}")
        print("-" * 60)

        t0 = time.time()
        try:
            tx_data = call_oracle(test["args"])
            elapsed = time.time() - t0
            result  = parsear_tx_result(tx_data)

            vote     = result.get("vote", "?")
            hoca     = result.get("recompensa_hoca", 0)
            cats     = result.get("clasificacion", [])
            conf     = result.get("confidence", 0)
            just     = result.get("justification", "")
            alerta   = result.get("alerta")
            coincide = test["esperado"].upper() in str(vote).upper()

            print(f"Tiempo:        {elapsed:.1f}s")
            print(f"vote:          {vote}")
            print(f"recompensa:    {hoca} HoCa")
            print(f"clasificacion: {cats}")
            print(f"confidence:    {conf}")
            print(f"justification: {just}")
            if alerta:
                print(f"alerta:        {alerta}")

            if coincide:
                print(f"PASS — coincide con {test['esperado']}")
            else:
                print(f"RESULTADO DISTINTO — esperaba {test['esperado']}, obtuvo {vote}")
            pasaron += 1

        except RuntimeError as e:
            elapsed = time.time() - t0
            print(f"ERROR ({elapsed:.1f}s): {e}")
            fallaron += 1
        except TimeoutError as e:
            print(f"TIMEOUT: {e}")
            fallaron += 1
        except Exception as e:
            import traceback
            elapsed = time.time() - t0
            print(f"EXCEPCION ({elapsed:.1f}s): {type(e).__name__}: {e}")
            traceback.print_exc()
            fallaron += 1

    total = pasaron + fallaron
    print()
    print("=" * 60)
    print(f"Resultado: {pasaron} pasaron / {fallaron} fallaron ({total} total)")
    print("=" * 60)


if __name__ == "__main__":
    main()
