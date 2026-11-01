-- Invio di email da parte degli agenti con casella: solo bozze (predefinito), con approvazione oppure diretto
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS invio_posta TEXT NOT NULL DEFAULT 'bozze';
ALTER TABLE agenti DROP CONSTRAINT IF EXISTS agenti_invio_posta_check;
ALTER TABLE agenti ADD CONSTRAINT agenti_invio_posta_check CHECK (invio_posta IN ('bozze', 'approvazione', 'diretto'));
ALTER TABLE caselle_posta ADD COLUMN IF NOT EXISTS smtp_host TEXT;
ALTER TABLE caselle_posta ADD COLUMN IF NOT EXISTS smtp_porta INTEGER;

CREATE TABLE IF NOT EXISTS email_in_uscita (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  canale TEXT NOT NULL CHECK (canale IN ('gmail', 'imap')),
  account_id INTEGER NOT NULL,                      -- account Google o casella IMAP, secondo il canale
  mittente TEXT NOT NULL DEFAULT '',
  destinatari TEXT NOT NULL,
  oggetto TEXT NOT NULL,
  testo TEXT NOT NULL,
  rispondi_a TEXT,
  diretta BOOLEAN NOT NULL DEFAULT FALSE,
  stato TEXT NOT NULL DEFAULT 'da_approvare' CHECK (stato IN ('da_approvare', 'inviata', 'rifiutata', 'errore')),
  errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  decisa_il TIMESTAMPTZ,
  decisa_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS email_in_uscita_stato ON email_in_uscita (stato, creata_il DESC);
