-- Utenti umani: secondo fattore (app di autenticazione), codici di recupero, blocco dopo troppi errori
ALTER TABLE utenti ADD COLUMN IF NOT EXISTS totp_segreto_cifrato TEXT;
ALTER TABLE utenti ADD COLUMN IF NOT EXISTS totp_attivo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE utenti ADD COLUMN IF NOT EXISTS totp_ultimo_passo BIGINT NOT NULL DEFAULT 0;
ALTER TABLE utenti ADD COLUMN IF NOT EXISTS deve_cambiare_password BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE utenti ADD COLUMN IF NOT EXISTS token_valido_dal TIMESTAMPTZ NOT NULL DEFAULT '2000-01-01';

CREATE TABLE IF NOT EXISTS codici_recupero (
  id SERIAL PRIMARY KEY,
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  codice_hash TEXT NOT NULL,
  usato_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS codici_recupero_utente ON codici_recupero(utente_id);

CREATE TABLE IF NOT EXISTS tentativi_accesso (
  id BIGSERIAL PRIMARY KEY,
  chiave TEXT NOT NULL,                 -- impronta dell'email (anche se non esiste)
  quando TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS tentativi_accesso_chiave ON tentativi_accesso(chiave, quando);
