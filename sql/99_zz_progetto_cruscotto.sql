-- Le riunioni lanciate dalla pagina di un progetto restano legate al progetto (appaiono nel suo calendario).
ALTER TABLE tavoli ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_tavoli_progetto ON tavoli (progetto_id) WHERE progetto_id IS NOT NULL;
