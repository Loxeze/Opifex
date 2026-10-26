-- 1.29.0: invio in chat senza attesa: il messaggio entra in coda e l'agente risponde appena e' libero
CREATE TABLE IF NOT EXISTS chat_coda (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE CASCADE,
  messaggio TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'in_coda' CHECK (stato IN ('in_coda', 'in_lavoro', 'finito', 'errore')),
  risultato JSONB,
  errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  iniziato_il TIMESTAMPTZ,
  finito_il TIMESTAMPTZ,
  secondi NUMERIC(8,1)
);
CREATE INDEX IF NOT EXISTS idx_chat_coda_utente ON chat_coda (utente_id, id DESC);
