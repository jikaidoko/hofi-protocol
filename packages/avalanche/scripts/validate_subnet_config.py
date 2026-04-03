"""
HoFi · HolonChain — Subnet Config Validator
Validates subnet-config.json before Avalanche Fuji deployment.
Usage: python validate_subnet_config.py [path/to/subnet-config.json]
"""
import json
import sys
import hashlib
from pathlib import Path

# ── Path safety ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def safe_path(user_input: str) -> Path:
    """Resolve path and verify it stays within project root."""
    resolved = Path(user_input).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        print(f"ERROR: Path {resolved} is outside project root {PROJECT_ROOT}")
        sys.exit(1)
    return resolved

# ── EIP-55 checksum ────────────────────────────────────────────────────────
def keccak256_hex(data: bytes) -> str:
    """keccak256 using eth_hash (pysha3 backend)."""
    try:
        from eth_hash.auto import keccak
        return keccak(data).hex()
    except ImportError:
        try:
            from web3 import Web3
            return Web3.keccak(data).hex()
        except ImportError:
            # Pure fallback using pysha3
            import _pysha3
            k = _pysha3.keccak_256()
            k.update(data)
            return k.hexdigest()

def eip55_checksum(address: str) -> str:
    """Returns EIP-55 checksummed address."""
    addr = address.lower().replace("0x", "")
    if len(addr) != 40 or not all(c in "0123456789abcdef" for c in addr):
        raise ValueError(f"Invalid hex address: {address}")
    h = keccak256_hex(addr.encode("ascii"))
    result = "0x"
    for i, char in enumerate(addr):
        if char.isdigit():
            result += char
        elif int(h[i], 16) >= 8:
            result += char.upper()
        else:
            result += char.lower()
    return result

def is_valid_eip55(address: str) -> tuple[bool, str]:
    """Returns (is_valid, expected_checksum)."""
    try:
        expected = eip55_checksum(address)
        normalized = "0x" + address.lower().replace("0x", "")
        return (address == expected), expected
    except Exception as e:
        return False, str(e)

# ── Validators ─────────────────────────────────────────────────────────────
def validate(config: dict) -> tuple[list, list]:
    errors = []
    warnings = []

    # chainId consistency
    top = config.get("chainId")
    gen = config.get("genesis", {}).get("config", {}).get("chainId")
    if top != gen:
        errors.append(f"chainId mismatch: top-level={top}, genesis.config={gen}")
    else:
        print(f"  ✓ chainId consistent: {top}")

    # extraData length (Clique: 32 vanity + 20*n signers + 65 seal bytes)
    extra = config.get("genesis", {}).get("extraData", "")
    nb = len(extra.replace("0x", "")) // 2
    if nb < 97:
        errors.append(f"extraData too short: {nb} bytes (min 97 = 32+0+65)")
    else:
        print(f"  ✓ extraData: {nb} bytes")

    # alloc addresses — EIP-55
    alloc = config.get("genesis", {}).get("alloc", {})
    if not alloc:
        warnings.append("alloc is empty — no pre-funded addresses")
    for addr in alloc:
        prefixed = addr if addr.startswith("0x") else "0x" + addr
        valid, expected = is_valid_eip55(prefixed)
        if valid:
            print(f"  ✓ EIP-55 valid: {prefixed}")
        else:
            errors.append(f"EIP-55 invalid: {prefixed}\n    expected: {expected}")

    # feeConfig
    fee = config.get("genesis", {}).get("config", {}).get("feeConfig", {})
    gas = fee.get("gasLimit", 0)
    if isinstance(gas, int) and gas >= 8_000_000:
        print(f"  ✓ gasLimit: {gas:,}")
    else:
        warnings.append(f"gasLimit {gas} may be too low (recommend ≥ 8M)")

    mbf = fee.get("minBaseFee", 0)
    if isinstance(mbf, int) and mbf >= 1_000_000_000:
        print(f"  ✓ minBaseFee: {mbf/1e9:.0f} Gwei")
    else:
        warnings.append(f"minBaseFee {mbf} < 1 Gwei")

    return errors, warnings

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        config_path = safe_path(sys.argv[1])
    else:
        config_path = safe_path(str(PROJECT_ROOT / "subnet-config.json"))

    if not config_path.exists():
        print(f"ERROR: {config_path} not found")
        sys.exit(1)

    # File size check
    size = config_path.stat().st_size
    if size > 100_000:
        print(f"ERROR: file too large ({size} bytes, max 100KB)")
        sys.exit(1)
    print(f"  ✓ File: {config_path.name} ({size} bytes)")

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON — {e}")
        sys.exit(1)

    errors, warnings = validate(config)

    if warnings:
        print()
        for w in warnings:
            print(f"  ⚠  {w}")

    if errors:
        print()
        for e in errors:
            print(f"  ✗  {e}")
        print(f"\n{len(errors)} error(s) — fix before deploying to Fuji")
        sys.exit(1)

    print("\n  ✓ All checks passed — safe to deploy to Fuji testnet")
    sys.exit(0)

if __name__ == "__main__":
    main()
