-- 1.26.0: casi di prova per agente (confronto prima/dopo) e coda di proposte delle sentinelle
CREATE TABLE IF NOT EXISTS casi_prova (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  richiesta TEXT NOT NULL CHECK (length(richiesta) BETWEEN 3 AND 2000),
  criteri TEXT NOT NULL CHECK (length(criteri) BETWEEN 3 AND 2000),
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  generato BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_casi_agente ON casi_prova (agente_id);

CREATE TABLE IF NOT EXISTS prove_lotti (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  etichetta TEXT,
  impronta TEXT,          -- impronta di istruzioni e modello al momento della prova
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso', 'finito', 'errore')),
  totale INTEGER NOT NULL DEFAULT 0,
  fatti INTEGER NOT NULL DEFAULT 0,
  media NUMERIC(4,2),
  errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lotti_agente ON prove_lotti (agente_id, id DESC);

CREATE TABLE IF NOT EXISTS prove_esiti (
  id SERIAL PRIMARY KEY,
  lotto_id INTEGER NOT NULL REFERENCES prove_lotti(id) ON DELETE CASCADE,
  caso_id INTEGER NOT NULL REFERENCES casi_prova(id) ON DELETE CASCADE,
  risposta TEXT,
  punteggio SMALLINT CHECK (punteggio BETWEEN 0 AND 10),
  giudizio TEXT
);
CREATE INDEX IF NOT EXISTS idx_esiti_lotto ON prove_esiti (lotto_id);

CREATE TABLE IF NOT EXISTS proposte_sentinelle (
  id SERIAL PRIMARY KEY,
  sentinella TEXT NOT NULL CHECK (sentinella IN ('qualita', 'costi', 'fonti', 'evoluzione')),
  tipo TEXT NOT NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  motivazione TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'in_attesa' CHECK (stato IN ('in_attesa', 'approvata', 'respinta')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ,
  decisa_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  esito TEXT
);
CREATE INDEX IF NOT EXISTS idx_prop_sent ON proposte_sentinelle (stato, creata_il DESC);
