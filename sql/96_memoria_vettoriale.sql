-- 1.73.0: memoria condivisa con ricerca per significato (vettori) e importazione delle conversazioni di ChatGPT e Claude
CREATE TABLE IF NOT EXISTS pezzi_vettori (
  pezzo_id INTEGER PRIMARY KEY REFERENCES pezzi_documenti(id) ON DELETE CASCADE,
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  vettore BYTEA NOT NULL,
  modello TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS pezzi_vettori_doc ON pezzi_vettori (documento_id);
CREATE TABLE IF NOT EXISTS importazioni_chat (
  id SERIAL PRIMARY KEY,
  origine TEXT NOT NULL,
  nome_file TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','conclusa','errore')),
  conversazioni INTEGER NOT NULL DEFAULT 0,
  importate INTEGER NOT NULL DEFAULT 0,
  saltate INTEGER NOT NULL DEFAULT 0,
  errore TEXT,
  per_tutti BOOLEAN NOT NULL DEFAULT TRUE,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE documenti ADD COLUMN IF NOT EXISTS origine_chat TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS documenti_origine_chat ON documenti (origine_chat) WHERE origine_chat IS NOT NULL;
