-- Radar: temi da tenere d'occhio (clienti, collaboratori, partner, opportunita') con ricerche periodiche su notizie, articoli e blog
CREATE TABLE IF NOT EXISTS radar_temi (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'cliente' CHECK (tipo IN ('cliente','collaboratore','partner','opportunita')),
  descrizione TEXT NOT NULL,
  giorni INTEGER NOT NULL DEFAULT 1 CHECK (giorni BETWEEN 1 AND 30),
  quantita INTEGER NOT NULL DEFAULT 10 CHECK (quantita BETWEEN 1 AND 40),
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_il TIMESTAMPTZ,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE crm_ricerche ADD COLUMN IF NOT EXISTS tema_id INTEGER REFERENCES radar_temi(id) ON DELETE SET NULL;
ALTER TABLE crm_proposte ADD COLUMN IF NOT EXISTS segnale TEXT;
CREATE INDEX IF NOT EXISTS crm_proposte_fonte ON crm_proposte (fonte_url);
