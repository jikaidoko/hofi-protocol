"""
test_genlayer_call.py — Diagnóstico del call a TenzoEquityOracle v0.2.1
Corré con: python test_genlayer_call.py

No tiene dependencias fuera de la stdlib + httpx (ya está en tenzo-agent).
"""

import json
import httpx

GENLAYER_RPC   = "https://studio.genlayer.com/api"
ORACLE_ADDRESS = "0x5b125045739238fb6d6664bD1718ff18b883C1C7"
CALLER         = "0x0000000000000000000000000000000000000001"

# ── Casos de prueba ────────────────────────────────────────────────────────────
TESTS = [
    {
        "nombre": "TV (confianza baja — debería rechazarse)",
        "args": ["estuvo mirando television 2 horas", "familia-valdes", 2.0, -1.0, "", ""],
    },
    {
        "nombre": "Huerta (confianza alta — debería aprobarse)",
        "args": ["Trabaje en la huerta durante una hora", "familia-valdes", 1.0, -1.0, "", ""],
    },
]

def call_isc(args: list, test_id: int) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "method":  "gen_call",
        "id":      test_id,
        "params":  [{
            "from":     CALLER,
            "to":       ORACLE_ADDRESS,
            "function": "validate_task_equity",
            "args":     args,
            "value":    0,          # int, no string
        }],
    }
    print(f"\n→ Enviando payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    resp = httpx.post(GENLAYER_RPC, json=payload, timeout=60)
    print(f"\n← HTTP {resp.status_code}")
    try:
        return resp.json()
    except Exception:
        print("  (respuesta no es JSON)")
        print(resp.text[:500])
        return {}

def main():
    for i, test in enumerate(TESTS, start=1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {test['nombre']}")
        print('='*60)

        raw = call_isc(test["args"], i)
        print("\n← Respuesta completa:")
        print(json.dumps(raw, indent=2, ensure_ascii=False))

        if "error" in raw:
            err = raw["error"]
            print(f"\n❌ ERROR JSON-RPC {err.get('code')}: {err.get('message')}")
            data = err.get("data", "")
            if data:
                print(f"   data: {data}")
        elif "result" in raw:
            result = raw["result"]
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    pass
            print(f"\n✅ RESULTADO: {json.dumps(result, ensure_ascii=False)}")
        else:
            print("\n⚠ Respuesta inesperada (ni error ni result)")

if __name__ == "__main__":
    main()
