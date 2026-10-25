-- CRM contatti: i dati che identificano le persone sono cifrati (cassaforte); gli agenti ricevono solo conteggi aggregati
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS crm_attivo BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS crm_liste (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  fonte TEXT,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  natura TEXT NOT NULL CHECK (natura IN ('pubblico', 'personale')),
  base_giuridica TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS crm_contatti (
  id SERIAL PRIMARY KEY,
  lista_id INTEGER NOT NULL REFERENCES crm_liste(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL DEFAULT 'altro',
  regione TEXT, provincia TEXT, fascia_dimensione TEXT, settore TEXT,
  relazione TEXT NOT NULL DEFAULT 'nessuna',
  ultimo_contatto DATE,
  consenso_marketing BOOLEAN,
  nome_cifrato TEXT, ente_cifrato TEXT, email_cifrata TEXT, telefono_cifrato TEXT, note_cifrate TEXT,
  email_hash TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS crm_contatti_unico ON crm_contatti (lista_id, email_hash) WHERE email_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS crm_contatti_filtri ON crm_contatti (tipo, regione, provincia, fascia_dimensione);
CREATE TABLE IF NOT EXISTS crm_accessi (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  azione TEXT NOT NULL,
  filtri JSONB,
  esito INTEGER,
  quando TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
