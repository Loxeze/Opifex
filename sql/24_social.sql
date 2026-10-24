-- Collegamento a Buffer e coda dei post social da approvare
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS social_attivo BOOLEAN NOT NULL DEFAULT FALSE;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('buffer_chiave_cifrata', ''), ('buffer_organizzazione_id', '')
ON CONFLICT (chiave) DO NOTHING;

CREATE TABLE IF NOT EXISTS post_social (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  canale_id TEXT NOT NULL,
  canale_nome TEXT NOT NULL DEFAULT '',
  servizio TEXT NOT NULL DEFAULT '',
  testo TEXT NOT NULL,
  media JSONB NOT NULL DEFAULT '[]',                 -- [{"tipo": "image"|"video", "url": "https://..."}]
  programmato_il TIMESTAMPTZ,                        -- vuoto = nella coda di Buffer, al prossimo orario libero
  stato TEXT NOT NULL DEFAULT 'da_approvare' CHECK (stato IN ('da_approvare', 'inviato', 'rifiutato', 'errore')),
  nota TEXT,
  buffer_post_id TEXT,
  errore TEXT,
  approvato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS post_social_stato ON post_social (stato, creato_il DESC);
