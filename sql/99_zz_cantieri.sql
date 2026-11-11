CREATE TABLE IF NOT EXISTS cantieri (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
  utente_id INTEGER,
  origine TEXT,
  richiesta TEXT NOT NULL,
  piano JSONB NOT NULL DEFAULT '[]',
  esiti JSONB NOT NULL DEFAULT '[]',
  stato TEXT NOT NULL DEFAULT 'in_corso',
  rifatte INTEGER NOT NULL DEFAULT 0,
  da_verificare TEXT,
  token_online INTEGER NOT NULL DEFAULT 0,
  token_locali INTEGER NOT NULL DEFAULT 0,
  costo_online NUMERIC(10,5) NOT NULL DEFAULT 0,
  secondi REAL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cantieri_agente ON cantieri (agente_id, id DESC);
