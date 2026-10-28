-- 1.63.0: tetto di spesa mensile per reparto e controllo periodico delle dipendenze
ALTER TABLE divisioni ADD COLUMN IF NOT EXISTS tetto_spesa_mese NUMERIC(10,2);
ALTER TABLE divisioni DROP CONSTRAINT IF EXISTS divisioni_tetto_spesa_check;
ALTER TABLE divisioni ADD CONSTRAINT divisioni_tetto_spesa_check CHECK (tetto_spesa_mese IS NULL OR tetto_spesa_mese > 0);

CREATE TABLE IF NOT EXISTS controlli_dipendenze (
  id SERIAL PRIMARY KEY,
  eseguito_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  esito TEXT NOT NULL CHECK (esito IN ('ok','vulnerabilita','non_raggiungibile')),
  dettagli JSONB NOT NULL DEFAULT '[]'
);
