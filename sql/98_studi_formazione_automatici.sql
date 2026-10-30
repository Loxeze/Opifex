-- 1.75.0: coda degli studi che parte da sola; giro dei desideri di formazione; livello minimo per le competenze necessarie
ALTER TABLE richieste_formazione ADD COLUMN IF NOT EXISTS minimo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE richieste_formazione DROP CONSTRAINT IF EXISTS richieste_formazione_origine_check;
ALTER TABLE richieste_formazione ADD CONSTRAINT richieste_formazione_origine_check CHECK (origine IN ('manuale', 'manager', 'pm', 'lacuna', 'cerimoniere', 'desiderio', 'minimo'));
CREATE TABLE IF NOT EXISTS competenze_necessarie (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS competenze_necessarie_uq ON competenze_necessarie (agente_id, lower(nome));
CREATE TABLE IF NOT EXISTS desideri_agenti (
  agente_id INTEGER PRIMARY KEY REFERENCES agenti(id) ON DELETE CASCADE,
  ultimo_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  esito TEXT
);
CREATE TABLE IF NOT EXISTS desideri_giri (
  id SERIAL PRIMARY KEY,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','concluso','errore')),
  interrogati INTEGER NOT NULL DEFAULT 0,
  richieste INTEGER NOT NULL DEFAULT 0,
  errore TEXT,
  avviato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  concluso_il TIMESTAMPTZ
);
ALTER TABLE studi ADD COLUMN IF NOT EXISTS avviato_il TIMESTAMPTZ;
