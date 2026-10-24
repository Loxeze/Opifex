-- Memoria delle conversazioni utente-agente, visione d'insieme per l'agente referente, file Google creati dagli agenti
CREATE TABLE IF NOT EXISTS chat_messaggi (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  ruolo TEXT NOT NULL CHECK (ruolo IN ('utente', 'agente')),
  testo TEXT NOT NULL,
  fascia_dati TEXT NOT NULL DEFAULT 'interno' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS chat_agente_utente ON chat_messaggi (agente_id, utente_id, id DESC);
CREATE INDEX IF NOT EXISTS chat_utente ON chat_messaggi (utente_id, id DESC);

ALTER TABLE agenti ADD COLUMN IF NOT EXISTS vede_tutto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS drive_attivo BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE agenti SET vede_tutto = TRUE, drive_attivo = TRUE WHERE tipo = 'sistema' AND livello = 'referente' AND NOT sentinella;

CREATE TABLE IF NOT EXISTS file_google_agenti (
  file_id TEXT PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('foglio', 'documento')),
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
