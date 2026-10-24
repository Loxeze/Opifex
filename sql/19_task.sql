-- Task e sottotask per persone e agenti (modello ispirato ad Asana). Le vecchie tabelle "compiti" restano com'erano.
CREATE TABLE IF NOT EXISTS task (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  descrizione TEXT,
  stato TEXT NOT NULL DEFAULT 'da_fare' CHECK (stato IN ('da_fare', 'in_corso', 'in_attesa', 'completata')),
  priorita TEXT NOT NULL DEFAULT 'normale' CHECK (priorita IN ('bassa', 'normale', 'alta', 'urgente')),
  scadenza DATE,
  padre_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  assegnato_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  assegnato_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  completata_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (NOT (assegnato_utente_id IS NOT NULL AND assegnato_agente_id IS NOT NULL)),
  CHECK (padre_id IS NULL OR padre_id <> id)
);
CREATE INDEX IF NOT EXISTS task_utente ON task(assegnato_utente_id, stato);
CREATE INDEX IF NOT EXISTS task_agente ON task(assegnato_agente_id, stato);
CREATE INDEX IF NOT EXISTS task_padre ON task(padre_id);

CREATE TABLE IF NOT EXISTS task_commenti (
  id SERIAL PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  testo TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS task_commenti_task ON task_commenti(task_id, creato_il);

CREATE TABLE IF NOT EXISTS task_documenti (
  task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, documento_id)
);
