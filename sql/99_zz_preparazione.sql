CREATE TABLE IF NOT EXISTS verifiche_competenza (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  competenza_id INTEGER REFERENCES competenze(id) ON DELETE SET NULL,
  competenza_nome TEXT NOT NULL,
  livello INTEGER NOT NULL,
  domande TEXT, risposte TEXT, correzione TEXT, lacune TEXT,
  voto NUMERIC(3,1),
  esito TEXT NOT NULL DEFAULT 'in_corso' CHECK (esito IN ('in_corso','ok','lacune','errore')),
  errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  conclusa_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS verifiche_agente ON verifiche_competenza (agente_id, competenza_id, creata_il DESC);
