-- 2.69: email formattate, immagini nel testo, allegati; niente piu' riga «RIMUOVI» nelle email delle campagne
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS html TEXT;

CREATE TABLE IF NOT EXISTS email_allegati (
  id SERIAL PRIMARY KEY,
  email_id INTEGER NOT NULL REFERENCES email_in_uscita(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  mime TEXT NOT NULL DEFAULT 'application/octet-stream',
  dati BYTEA NOT NULL,
  dimensione INTEGER NOT NULL,
  inline BOOLEAN NOT NULL DEFAULT FALSE,     -- immagine dentro il testo
  cid TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS email_allegati_email ON email_allegati (email_id);

CREATE TABLE IF NOT EXISTS campagne_allegati (
  id SERIAL PRIMARY KEY,
  campagna_id INTEGER NOT NULL REFERENCES campagne_posta(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  mime TEXT NOT NULL DEFAULT 'application/octet-stream',
  dati BYTEA NOT NULL,
  dimensione INTEGER NOT NULL,
  in_solleciti BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- le bozze non ancora partite perdono la riga per non ricevere altre email
UPDATE email_in_uscita SET testo = regexp_replace(testo, E'\\n*—\\nSe non desidera ricevere altre comunicazioni di questo tipo.*$', '')
 WHERE campagna_id IS NOT NULL AND stato IN ('da_approvare', 'approvata', 'errore') AND testo LIKE '%Se non desidera ricevere altre comunicazioni%';
UPDATE email_in_uscita SET testo_proposto = regexp_replace(testo_proposto, E'\\n*—\\nSe non desidera ricevere altre comunicazioni di questo tipo.*$', '')
 WHERE campagna_id IS NOT NULL AND stato IN ('da_approvare', 'approvata', 'errore') AND testo_proposto LIKE '%Se non desidera ricevere altre comunicazioni%';
