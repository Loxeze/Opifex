-- Aziende, divisioni modificabili, agenti assegnati a una o piu' aziende
ALTER TABLE aziende ADD COLUMN IF NOT EXISTS colore TEXT NOT NULL DEFAULT '#22d3ee';
ALTER TABLE aziende ADD COLUMN IF NOT EXISTS attiva BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE divisioni ADD COLUMN IF NOT EXISTS azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL;
ALTER TABLE divisioni ADD COLUMN IF NOT EXISTS colore TEXT NOT NULL DEFAULT '#a78bfa';

CREATE TABLE IF NOT EXISTS agenti_aziende (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  PRIMARY KEY (agente_id, azienda_id)
);
