"""IndexStore de wallets custodiales contra Neon (tabla custodial_wallets).

Asigna un índice de derivación HD persistente por person_id, para que la dirección
custodial de cada persona sea siempre la misma. Usa el mismo patrón de conexión
psycopg2 que el resto del Tenzo (DB_HOST/DB_NAME/DB_USER/DB_PASS).

Migración requerida (Neon):
    CREATE TABLE IF NOT EXISTS custodial_wallets (
      person_id        VARCHAR(100) PRIMARY KEY,
      derivation_index INTEGER UNIQUE NOT NULL,
      cardano_address  TEXT,
      custody_mode     VARCHAR(16) DEFAULT 'custodial',
      created_at       TIMESTAMPTZ DEFAULT NOW()
    );
"""
import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "hofi")
DB_USER = os.getenv("DB_USER", "")
DB_PASS = os.getenv("DB_PASS", "")


def _conn():
    import psycopg2
    return psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS)


class NeonIndexStore:
    """Implementa el IndexStore que espera CustodialWallets.get_or_create."""

    def get_index(self, person_id: str):
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT derivation_index FROM custodial_wallets WHERE person_id = %s",
                (person_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def assign_index(self, person_id: str) -> int:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(derivation_index), -1) + 1 FROM custodial_wallets")
            idx = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO custodial_wallets (person_id, derivation_index) "
                "VALUES (%s, %s) ON CONFLICT (person_id) DO NOTHING",
                (person_id, idx),
            )
            c.commit()
            return idx

    def save_address(self, person_id: str, address: str) -> None:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "UPDATE custodial_wallets SET cardano_address = %s WHERE person_id = %s",
                (address, person_id),
            )
            c.commit()

    def set_custody_self(self, person_id: str, address: str) -> None:
        """Tras graduar: marca la custodia como self y guarda la dirección propia."""
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                "UPDATE custodial_wallets SET custody_mode = 'self', cardano_address = %s "
                "WHERE person_id = %s",
                (address, person_id),
            )
            c.commit()
