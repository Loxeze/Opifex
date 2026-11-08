-- Ricercatore di contatti: proposte da approvare prima di entrare nel CRM
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS crm_ricerca BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS crm_ricerche (
  id SERIAL PRIMARY KEY,
  criteri TEXT NOT NULL,
  quantita INTEGER NOT NULL DEFAULT 20,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','conclusa','errore')),
  proposte INTEGER NOT NULL DEFAULT 0,
  scartate INTEGER NOT NULL DEFAULT 0,
  esito TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  conclusa_il TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS crm_proposte (
  id SERIAL PRIMARY KEY,
  ricerca_id INTEGER REFERENCES crm_ricerche(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  nome_cifrato TEXT, ente_cifrato TEXT, email_cifrata TEXT, telefono_cifrato TEXT,
  email_hash TEXT,
  ruolo TEXT, tipo TEXT, regione TEXT, provincia TEXT, settore TEXT,
  fonte_url TEXT NOT NULL,
  motivo TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta','approvata','scartata')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS crm_proposte_stato ON crm_proposte (stato, ricerca_id);
