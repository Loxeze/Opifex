-- Scheda di progetto viva: obiettivo, stato, prossimi passi, nodi aperti, decisioni, storico modifiche e documentazione allegata.
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS obiettivo TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS stato_attuale TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS prossimi_passi TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS nodi_aperti TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS scheda_il TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS progetti_decisioni (
  id SERIAL PRIMARY KEY,
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  testo TEXT NOT NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  superata BOOLEAN NOT NULL DEFAULT FALSE,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prog_decisioni ON progetti_decisioni (progetto_id, creata_il DESC);

CREATE TABLE IF NOT EXISTS progetti_versioni (
  id SERIAL PRIMARY KEY,
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  campo TEXT NOT NULL,
  prima TEXT NOT NULL DEFAULT '',
  dopo TEXT NOT NULL DEFAULT '',
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prog_versioni ON progetti_versioni (progetto_id, creata_il DESC);

-- documenti di base del progetto: li leggono tutti gli agenti assegnati al progetto (e i loro superiori)
CREATE TABLE IF NOT EXISTS progetti_documenti (
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  documento_id INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  aggiunto_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (progetto_id, documento_id)
);
