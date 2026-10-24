-- Richieste di informazioni mancanti, coda notifiche, dialoghi per manager e supervisori
CREATE TABLE IF NOT EXISTS richieste_informazioni (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id),
  domanda TEXT NOT NULL,
  bloccante BOOLEAN NOT NULL DEFAULT FALSE,
  stato TEXT NOT NULL DEFAULT 'aperta' CHECK (stato IN ('aperta', 'risposta', 'annullata')),
  risposta TEXT,
  consegnata BOOLEAN NOT NULL DEFAULT FALSE,
  creata_il TIMESTAMPTZ DEFAULT NOW(),
  risposta_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_richieste_stato ON richieste_informazioni (stato, agente_id);

CREATE TABLE IF NOT EXISTS notifiche (
  id SERIAL PRIMARY KEY,
  testo TEXT NOT NULL,
  urgente BOOLEAN NOT NULL DEFAULT FALSE,
  creata_il TIMESTAMPTZ DEFAULT NOW(),
  inviata_il TIMESTAMPTZ,
  canale TEXT
);

-- Manager, referente e agenti di sistema possono fare domande ai colleghi
UPDATE agenti SET dialoghi_attivi = TRUE WHERE livello IN ('manager', 'referente') OR tipo = 'sistema';
