-- 2.64.0: campagne a blocchi. Brief, foglio Google come partenza, Redattore delle campagne con note del contatto,
-- risposte smistate in automatico, solleciti, opportunita' con link di prenotazione, tetto di spesa, invio automatico guadagnato.

ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS categoria TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS brief JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio_account_id INTEGER REFERENCES account_google(id) ON DELETE SET NULL;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio_letto_il TIMESTAMPTZ;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio_errore TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS foglio_righe INTEGER NOT NULL DEFAULT 0;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS lista_id INTEGER REFERENCES crm_liste(id) ON DELETE SET NULL;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS personalizza BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS modello TEXT NOT NULL DEFAULT 'claude-haiku-5-5';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS tetto_spesa NUMERIC(8, 2) NOT NULL DEFAULT 5;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS spesa NUMERIC(10, 4) NOT NULL DEFAULT 0;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS sollecito_giorni INTEGER NOT NULL DEFAULT 14;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS solleciti INTEGER NOT NULL DEFAULT 2;   -- 0, 1 (solo la seconda), 2 (seconda e, se c'e' qualcosa di nuovo, terza)
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS link_prenotazione TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS invio_automatico BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta ADD COLUMN IF NOT EXISTS copiata_da INTEGER REFERENCES campagne_posta(id) ON DELETE SET NULL;

ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS passo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS prossimo_il TIMESTAMPTZ;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS angolo TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS angolo_motivo TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS zona TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS personalizzata BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS risposta_vaglio_id INTEGER;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS risposta_sintesi TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS opportunita_id INTEGER REFERENCES crm_opportunita(id) ON DELETE SET NULL;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS nota TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest DROP CONSTRAINT IF EXISTS campagne_posta_dest_stato_check;
ALTER TABLE campagne_posta_dest ADD CONSTRAINT campagne_posta_dest_stato_check CHECK (stato IN (
  'in_attesa', 'in_studio', 'da_approvare', 'approvata', 'inviata', 'scartata', 'errore',
  'risposto', 'interessato', 'non_interessato', 'rimosso', 'nessuna_risposta'));
CREATE INDEX IF NOT EXISTS campagne_posta_dest_prossimo ON campagne_posta_dest (stato, prossimo_il);

ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS oggetto_proposto TEXT;
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS testo_proposto TEXT;
ALTER TABLE email_in_uscita ADD COLUMN IF NOT EXISTS tipo_campagna TEXT NOT NULL DEFAULT 'primo';   -- primo | sollecito | risposta

-- righe del foglio Google gia' lette (il foglio e' di Lorenzo: Opifex lo legge soltanto)
CREATE TABLE IF NOT EXISTS campagne_foglio_righe (
  campagna_id INTEGER NOT NULL REFERENCES campagne_posta(id) ON DELETE CASCADE,
  chiave TEXT NOT NULL,                -- sito o email o nome, normalizzati: riconosce la riga anche se la si corregge
  impronta TEXT NOT NULL,              -- cambia quando la riga cambia
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  letta_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (campagna_id, chiave)
);

-- note del contatto: quello che il Redattore ha trovato online, per non ristudiare lo stesso sito
CREATE TABLE IF NOT EXISTS crm_note_web (
  contatto_id INTEGER PRIMARY KEY REFERENCES crm_contatti(id) ON DELETE CASCADE,
  sito TEXT NOT NULL DEFAULT '',
  sintesi_cifrata TEXT,
  comune_sito TEXT NOT NULL DEFAULT '',
  provincia_sito TEXT NOT NULL DEFAULT '',
  pagine JSONB NOT NULL DEFAULT '[]'::jsonb,
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- correzioni che il Redattore propone al CRM (lui non lo puo' modificare): le approva Lorenzo
CREATE TABLE IF NOT EXISTS crm_correzioni (
  id SERIAL PRIMARY KEY,
  contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  campo TEXT NOT NULL CHECK (campo IN ('comune', 'provincia', 'regione')),
  valore TEXT NOT NULL,
  motivo TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta', 'accettata', 'rifiutata')),
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (contatto_id, campo, valore)
);

-- imbuto: i gradini delle opportunita' nate dalle campagne
ALTER TABLE crm_opportunita DROP CONSTRAINT IF EXISTS crm_opportunita_stato_check;
ALTER TABLE crm_opportunita ADD CONSTRAINT crm_opportunita_stato_check CHECK (stato IN (
  'nuova', 'contattato', 'in_trattativa', 'vinta', 'persa', 'in_pausa',
  'interessato', 'call_fissata', 'call_fatta', 'proposta'));
ALTER TABLE crm_opportunita ADD COLUMN IF NOT EXISTS campagna_id INTEGER REFERENCES campagne_posta(id) ON DELETE SET NULL;
