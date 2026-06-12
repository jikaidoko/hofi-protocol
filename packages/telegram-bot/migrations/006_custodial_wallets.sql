-- Wallets custodiales (Web3-agnósticos): un índice de derivación HD por persona.
-- La clave privada NO se guarda; se re-deriva del seed maestro (KMS) por índice.
CREATE TABLE IF NOT EXISTS custodial_wallets (
  person_id        VARCHAR(100) PRIMARY KEY,
  derivation_index INTEGER UNIQUE NOT NULL,
  cardano_address  TEXT,
  custody_mode     VARCHAR(16) DEFAULT 'custodial',   -- 'custodial' | 'self' (tras graduar)
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
