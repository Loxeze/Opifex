-- Documenti di riferimento per gli agenti (memoria): testo estratto e ricercabile
CREATE TABLE IF NOT EXISTS documenti (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  nome_file TEXT NOT NULL,
  fascia_dati TEXT NOT NULL DEFAULT 'interno' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  per_tutti BOOLEAN NOT NULL DEFAULT FALSE,
  caratteri INTEGER NOT NULL DEFAULT 0,
  caricato_da INTEGER REFERENCES utenti(id),
  creato_il TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documenti_agenti (
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  PRIMARY KEY (documento_id, agente_id)
);

CREATE TABLE IF NOT EXISTS pezzi_documenti (
  id SERIAL PRIMARY KEY,
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  ordine INTEGER NOT NULL,
  testo TEXT NOT NULL,
  ricerca TSVECTOR GENERATED ALWAYS AS (to_tsvector('italian', testo)) STORED
);
CREATE INDEX IF NOT EXISTS idx_pezzi_ricerca ON pezzi_documenti USING GIN (ricerca);
