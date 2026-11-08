CREATE TABLE IF NOT EXISTS novita_viste (
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  area TEXT NOT NULL CHECK (area IN ('progetti','ginnasio','documenti')),
  visto_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (utente_id, area)
);
