"""
HoFi · GSD-014 — Generador de secrets seguros
Ejecutar UNA sola vez para generar JWT_SECRET_KEY y ADMIN_PASSWORD_HASH
"""
import secrets
import bcrypt
import getpass

print("\n=== HoFi · Generador de Secrets JWT ===\n")

# Generar JWT_SECRET_KEY
jwt_secret = secrets.token_hex(32)
print(f"JWT_SECRET_KEY={jwt_secret}")

# Generar hash de password
print("\nIngresá la password del admin (no se mostrará):")
password = getpass.getpass("Password: ")
password_confirm = getpass.getpass("Confirmá: ")

if password != password_confirm:
    print("ERROR: Las passwords no coinciden")
    exit(1)

if len(password) < 12:
    print("ERROR: La password debe tener al menos 12 caracteres")
    exit(1)

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
print(f"\nADMIN_PASSWORD_HASH={hashed}")

print("\n=== Agregá estas variables a Secret Manager ===")
print(f"gcloud secrets create JWT_SECRET_KEY --data-file=-")
print(f"  → valor: {jwt_secret}")
print(f"\ngcloud secrets create ADMIN_PASSWORD_HASH --data-file=-")
print(f"  → valor: {hashed}")
print("\nADMIN_USERNAME=tenzo-admin (podés cambiarlo)")
