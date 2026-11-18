-- 2.63.0: copia dalla 2 di imprese, CRM e affari; campagne email della Posta legate al CRM; traffico dei siti da Google Analytics

-- righe gia' copiate dalla 2 (per poter rifare la copia senza doppioni)
CREATE TABLE IF NOT EXISTS importazioni_2 (
  tabella TEXT NOT NULL,
  vecchio_id BIGINT NOT NULL,
  nuovo_id BIGINT NOT NULL,
  PRIMARY KEY (tabella, vecchio_id)
);

-- ---------- campagne email ----------
CREATE TABLE IF NOT EXISTS campagne_posta (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL CHECK (char_length(nome) BETWEEN 2 AND 120),
  obiettivo TEXT NOT NULL DEFAULT '',
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  mittente TEXT NOT NULL DEFAULT '',            -- 'gmail:<id account>' oppure 'imap:<id casella>'
  filtri JSONB NOT NULL DEFAULT '{}'::jsonb,     -- i filtri del CRM (come i segmenti) che scelgono i destinatari
  oggetto TEXT NOT NULL DEFAULT '',
  testo TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'bozza' CHECK (stato IN ('bozza', 'in_corso', 'in_pausa', 'chiusa')),
  per_ora INTEGER NOT NULL DEFAULT 20 CHECK (per_ora BETWEEN 1 AND 120),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  chiusa_il TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS campagne_posta_dest (
  id SERIAL PRIMARY KEY,
  campagna_id INTEGER NOT NULL REFERENCES campagne_posta(id) ON DELETE CASCADE,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  email_hash TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'in_attesa' CHECK (stato IN ('in_attesa', 'da_approvare', 'approvata', 'inviata', 'scartata', 'errore',
                                                          'risposto', 'interessato', 'non_interessato', 'rimosso')),
  email_id INTEGER REFERENCES email_in_uscita(id) ON DELETE SET NULL,
  inviata_il TIMESTAMPTZ,
  risposta_il TIMESTAMPTZ,
  risposta_oggetto TEXT,
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (campagna_id, email_hash)
);
CREATE INDEX IF NOT EXISTS campagne_destinatari_stato ON campagne_posta_dest (campagna_id, stato);
CREATE INDEX IF NOT EXISTS campagne_destinatari_hash ON campagne_posta_dest (email_hash);

ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS campagna_id INTEGER REFERENCES campagne_posta(id) ON DELETE SET NULL;
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS destinatario_id INTEGER REFERENCES campagne_posta_dest(id) ON DELETE SET NULL;
ALTER TABLE email_in_uscita DROP CONSTRAINT IF EXISTS email_in_uscita_stato_check;
ALTER TABLE email_in_uscita ADD CONSTRAINT email_in_uscita_stato_check CHECK (stato IN ('da_approvare', 'approvata', 'inviata', 'rifiutata', 'errore'));
CREATE INDEX IF NOT EXISTS email_in_uscita_campagna ON email_in_uscita (campagna_id, stato);

-- ---------- Google Analytics ----------
CREATE TABLE IF NOT EXISTS siti_analytics (
  id SERIAL PRIMARY KEY,
  account_google_id INTEGER REFERENCES account_google(id) ON DELETE SET NULL,
  proprieta TEXT NOT NULL UNIQUE,                 -- 'properties/123456789'
  nome TEXT NOT NULL DEFAULT '',
  indirizzo TEXT NOT NULL DEFAULT '',
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  scaricato_il TIMESTAMPTZ,
  errore TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS siti_analytics_giorni (
  sito_id INTEGER NOT NULL REFERENCES siti_analytics(id) ON DELETE CASCADE,
  giorno DATE NOT NULL,
  utenti INTEGER NOT NULL DEFAULT 0,
  nuovi_utenti INTEGER NOT NULL DEFAULT 0,
  sessioni INTEGER NOT NULL DEFAULT 0,
  visualizzazioni INTEGER NOT NULL DEFAULT 0,
  durata_media NUMERIC(10, 1) NOT NULL DEFAULT 0,
  PRIMARY KEY (sito_id, giorno)
);
CREATE TABLE IF NOT EXISTS siti_analytics_fonti (
  sito_id INTEGER NOT NULL REFERENCES siti_analytics(id) ON DELETE CASCADE,
  giorno DATE NOT NULL,
  fonte TEXT NOT NULL,
  sessioni INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (sito_id, giorno, fonte)
);
CREATE TABLE IF NOT EXISTS siti_analytics_pagine (
  sito_id INTEGER NOT NULL REFERENCES siti_analytics(id) ON DELETE CASCADE,
  pagina TEXT NOT NULL,
  titolo TEXT NOT NULL DEFAULT '',
  visualizzazioni INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (sito_id, pagina)
);
