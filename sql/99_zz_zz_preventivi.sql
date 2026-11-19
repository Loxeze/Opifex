-- 2.66.0: preventivi preparati in Opifex dal resoconto della call e creati in Fatture in Cloud (luogo dei documenti ufficiali)
CREATE TABLE IF NOT EXISTS preventivi (
  id SERIAL PRIMARY KEY,
  opportunita_id INTEGER REFERENCES crm_opportunita(id) ON DELETE SET NULL,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  oggetto TEXT NOT NULL DEFAULT '',
  voci JSONB NOT NULL DEFAULT '[]'::jsonb,        -- [{nome, descrizione, quantita, prezzo, iva}]
  note TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'bozza' CHECK (stato IN ('bozza', 'in_fatture', 'accettato', 'rifiutato', 'errore')),
  totale_netto NUMERIC(12, 2) NOT NULL DEFAULT 0,
  fic_id BIGINT,
  fic_numero TEXT,
  fic_url TEXT,
  errore TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  inviato_il TIMESTAMPTZ,
  controllato_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS preventivi_opportunita ON preventivi (opportunita_id);
