-- 2.70: piu' documenti di contatti per campagna; bozze a blocchi di 50 finche' l'invio automatico e' spento
CREATE TABLE IF NOT EXISTS campagne_fogli (
  id SERIAL PRIMARY KEY,
  campagna_id INTEGER NOT NULL REFERENCES campagne_posta(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  account_id INTEGER,
  righe INTEGER NOT NULL DEFAULT 0,
  errore TEXT NOT NULL DEFAULT '',
  letto_il TIMESTAMPTZ,
  aggiunto_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (campagna_id, url)
);
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS blocco_dal_id INTEGER;   -- il blocco comprende le prime email con id maggiore
-- 2.70: cosa c'e' in ogni colonna (riconosciuto da Opifex o corretto da Lorenzo)
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio_resoconto JSONB NOT NULL DEFAULT '[]';
CREATE TABLE IF NOT EXISTS campagne_colonne (
  id SERIAL PRIMARY KEY,
  campagna_id INTEGER NOT NULL REFERENCES campagne_posta(id) ON DELETE CASCADE,
  documento TEXT NOT NULL,      -- link del documento
  foglio TEXT NOT NULL,         -- nome della scheda
  mappa JSONB NOT NULL,         -- {"ente": 1, "email": 3, ...} indici delle colonne
  UNIQUE (campagna_id, documento, foglio)
);
