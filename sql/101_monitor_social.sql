-- 1.78.0: profili social da monitorare (propri e di altri), rilevazioni periodiche e rapporti dell'Analista
CREATE TABLE IF NOT EXISTS profili_monitorati (
  id SERIAL PRIMARY KEY,
  piattaforma TEXT NOT NULL CHECK (piattaforma IN ('instagram', 'facebook', 'youtube', 'linkedin', 'altro')),
  nome TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  identificativo TEXT NOT NULL DEFAULT '',
  proprio BOOLEAN NOT NULL DEFAULT FALSE,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  ultimo_controllo TIMESTAMPTZ,
  errore TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS profili_monitorati_uq ON profili_monitorati (piattaforma, lower(identificativo)) WHERE identificativo <> '';
CREATE TABLE IF NOT EXISTS rilevazioni_profili (
  id BIGSERIAL PRIMARY KEY,
  profilo_id INTEGER NOT NULL REFERENCES profili_monitorati(id) ON DELETE CASCADE,
  rilevata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  seguaci BIGINT,
  contenuti INTEGER,
  visualizzazioni BIGINT,
  dati JSONB NOT NULL DEFAULT '{}',
  origine TEXT NOT NULL DEFAULT 'api' CHECK (origine IN ('api', 'manuale'))
);
CREATE INDEX IF NOT EXISTS rilevazioni_profili_idx ON rilevazioni_profili (profilo_id, rilevata_il DESC);
CREATE TABLE IF NOT EXISTS rapporti_social (
  id SERIAL PRIMARY KEY,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  origine TEXT NOT NULL DEFAULT 'manuale',
  testo TEXT,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso', 'pronto', 'errore')),
  errore TEXT,
  documento_id INTEGER REFERENCES documenti(id) ON DELETE SET NULL
);
