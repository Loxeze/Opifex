-- 1.21.0: collaboratori per impresa, project manager per progetto, milestone
CREATE TABLE IF NOT EXISTS accessi_azienda (
    utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
    azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
    PRIMARY KEY (utente_id, azienda_id)
);
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS pm_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL;
CREATE TABLE IF NOT EXISTS milestone (
    id SERIAL PRIMARY KEY,
    progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
    titolo TEXT NOT NULL CHECK (char_length(titolo) BETWEEN 3 AND 200),
    scadenza DATE,
    raggiunta_il TIMESTAMPTZ,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS milestone_progetto ON milestone (progetto_id, scadenza);
