-- Prove di regressione: compiti di esempio con criteri, rieseguiti dopo ogni modifica importante per vedere se la qualita' sale o scende.
CREATE TABLE IF NOT EXISTS regressione_compiti (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  agente_id INTEGER,
  compito TEXT NOT NULL,
  criteri TEXT NOT NULL,
  attiva BOOLEAN NOT NULL DEFAULT TRUE,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS regressione_esiti (
  id SERIAL PRIMARY KEY,
  prova_id INTEGER NOT NULL,
  versione TEXT NOT NULL DEFAULT '',
  punteggio NUMERIC(5,2) NOT NULL DEFAULT 0,
  dettaglio JSONB NOT NULL DEFAULT '[]'::jsonb,
  giudice TEXT NOT NULL DEFAULT 'parole',
  risposta TEXT NOT NULL DEFAULT '',
  token INTEGER NOT NULL DEFAULT 0,
  errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS regressione_esiti_compito ON regressione_esiti (prova_id, id DESC);
