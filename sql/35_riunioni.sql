-- Riunioni importate (es. verbali Plaud ricevuti per email) e task proposti da approvare
CREATE TABLE IF NOT EXISTS riunioni_importate (
  id SERIAL PRIMARY KEY,
  casella_id INTEGER REFERENCES caselle_posta(id) ON DELETE SET NULL,
  uid TEXT NOT NULL,
  titolo TEXT NOT NULL,
  mittente TEXT,
  data_email TIMESTAMPTZ,
  testo TEXT NOT NULL,
  riassunto TEXT,
  stato TEXT NOT NULL DEFAULT 'nuova' CHECK (stato IN ('nuova', 'elaborata', 'ignorata', 'errore')),
  errore TEXT,
  importata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (casella_id, uid)
);
CREATE TABLE IF NOT EXISTS task_proposte (
  id SERIAL PRIMARY KEY,
  riunione_id INTEGER NOT NULL REFERENCES riunioni_importate(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  descrizione TEXT,
  priorita TEXT NOT NULL DEFAULT 'normale' CHECK (priorita IN ('bassa', 'normale', 'alta', 'urgente')),
  scadenza DATE,
  assegnatario_suggerito TEXT,
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta', 'approvata', 'scartata')),
  task_id INTEGER REFERENCES task(id) ON DELETE SET NULL,
  decisa_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  decisa_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_proposte_stato ON task_proposte (stato, riunione_id);
