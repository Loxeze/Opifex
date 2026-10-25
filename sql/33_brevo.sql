-- Brevo (email marketing): gli agenti preparano campagne, l'invio parte solo dopo l'approvazione di una persona
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS email_attivo BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS campagne_email (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  nome TEXT NOT NULL,
  oggetto TEXT NOT NULL,
  html TEXT NOT NULL,
  mittente_nome TEXT,
  mittente_email TEXT,
  liste JSONB NOT NULL DEFAULT '[]',          -- [{"id": 3, "nome": "Newsletter"}]
  programmata_il TIMESTAMPTZ,
  stato TEXT NOT NULL DEFAULT 'da_approvare' CHECK (stato IN ('da_approvare', 'bozza_brevo', 'inviata', 'rifiutata', 'errore')),
  brevo_id BIGINT,
  nota TEXT,
  errore TEXT,
  approvata_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
