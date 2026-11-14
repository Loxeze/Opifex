-- Posta 2.57: fatture, ricevute e avvisi di pagamento riconosciuti nella posta (base per il controllo di gestione)
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS allegati TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS amm_controllata BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS posta_amministrazione (
  id SERIAL PRIMARY KEY,
  vaglio_id INTEGER NOT NULL UNIQUE REFERENCES posta_vaglio(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('fattura', 'ricevuta', 'avviso_pagamento', 'sollecito', 'nota_credito', 'altro')),
  direzione TEXT NOT NULL DEFAULT 'uscita' CHECK (direzione IN ('uscita', 'entrata')),   -- uscita: Lorenzo paga; entrata: Lorenzo incassa
  controparte TEXT NOT NULL DEFAULT '',
  descrizione TEXT NOT NULL DEFAULT '',
  importo NUMERIC(12,2),
  valuta TEXT NOT NULL DEFAULT 'EUR',
  data_documento DATE,
  scadenza DATE,
  numero TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'da_verificare' CHECK (stato IN ('da_verificare', 'da_pagare', 'pagato', 'da_incassare', 'incassato')),
  attivita TEXT NOT NULL DEFAULT '',        -- a quale attivita' si riferisce (Logos, Renovatio...): la sceglie Lorenzo
  verificato BOOLEAN NOT NULL DEFAULT FALSE, -- Lorenzo ha controllato i dati estratti
  etichetta_casella BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS posta_amministrazione_data ON posta_amministrazione (data_documento DESC);
CREATE INDEX IF NOT EXISTS posta_amministrazione_scadenza ON posta_amministrazione (scadenza) WHERE stato IN ('da_pagare', 'da_incassare');

-- allegati salvati su Drive (Amministrazione/<anno>/<mese>) e ricevute da scaricare da un sito
ALTER TABLE posta_amministrazione ADD COLUMN IF NOT EXISTS file_drive JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE posta_amministrazione ADD COLUMN IF NOT EXISTS drive_stato TEXT NOT NULL DEFAULT '';
ALTER TABLE posta_amministrazione ADD COLUMN IF NOT EXISTS da_sito BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE posta_amministrazione ADD COLUMN IF NOT EXISTS link_sito TEXT NOT NULL DEFAULT '';

-- verbali di tavoli e riunioni salvati anche su Drive (Agenti/Tavoli, Agenti/Riunioni)
ALTER TABLE tavoli ADD COLUMN IF NOT EXISTS drive_link TEXT;
ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS drive_link TEXT;

-- 2.58: recupero della posta dal 1 gennaio (per casella, mese per mese): le email vecchie sono «storiche», non da leggere
ALTER TABLE posta_vaglio DROP CONSTRAINT IF EXISTS posta_vaglio_categoria_check;
ALTER TABLE posta_vaglio ADD CONSTRAINT posta_vaglio_categoria_check CHECK (categoria IN ('da_vagliare', 'importante', 'normale', 'scartabile', 'mia', 'storica'));
