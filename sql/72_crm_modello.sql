-- 1.42.0: CRM con persone e organizzazioni, relazioni datate, categorie con motivazione, campi personalizzati per tipo, recapiti multipli, fonte e verifica, storico
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'crm_contatti' AND column_name = 'genere') THEN
    ALTER TABLE crm_contatti ADD COLUMN genere TEXT NOT NULL DEFAULT 'organizzazione';
    -- chi ha solo un nome e nessun ente e' una persona; tutto il resto resta com'e' (organizzazione)
    UPDATE crm_contatti SET genere = 'persona' WHERE ente_cifrato IS NULL AND nome_cifrato IS NOT NULL;
  END IF;
END $$;
ALTER TABLE crm_contatti DROP CONSTRAINT IF EXISTS crm_contatti_genere_check;
ALTER TABLE crm_contatti ADD CONSTRAINT crm_contatti_genere_check CHECK (genere IN ('persona', 'organizzazione'));
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS comune TEXT;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS attributi JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS fonte_editore TEXT;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS fonte_licenza TEXT;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS fonte_url TEXT;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS fonte_data DATE;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS importato_il TIMESTAMPTZ;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS verificato_il DATE;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS verifica_nota TEXT;
CREATE INDEX IF NOT EXISTS crm_contatti_attributi ON crm_contatti USING GIN (attributi);
CREATE INDEX IF NOT EXISTS crm_contatti_comune ON crm_contatti (comune);

-- campi personalizzati: definiti da Lorenzo per tipo di contatto (tipo vuoto = per tutti); nelle schede dove non servono restano vuoti
CREATE TABLE IF NOT EXISTS crm_attributi_def (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL DEFAULT '',
  chiave TEXT NOT NULL CHECK (chiave ~ '^[a-z][a-z0-9_]{1,39}$'),
  etichetta TEXT NOT NULL CHECK (char_length(etichetta) BETWEEN 1 AND 60),
  dato TEXT NOT NULL DEFAULT 'testo' CHECK (dato IN ('testo', 'numero', 'data', 'si_no', 'scelta')),
  scelte JSONB NOT NULL DEFAULT '[]'::jsonb,
  ordine INTEGER NOT NULL DEFAULT 0,
  UNIQUE (tipo, chiave)
);

CREATE TABLE IF NOT EXISTS crm_categorie (
  nome TEXT PRIMARY KEY CHECK (char_length(nome) BETWEEN 2 AND 60),
  descrizione TEXT
);
INSERT INTO crm_categorie (nome, descrizione) VALUES
  ('cliente', 'Cliente attivo o passato'), ('potenziale cliente', 'Da contattare o in trattativa'), ('partner', 'Partner di progetto o di rete'),
  ('fornitore', 'Fornisce beni o servizi'), ('interlocutore istituzionale', 'Ente pubblico o istituzione'), ('contatto accademico', 'Universita'' e ricerca')
ON CONFLICT (nome) DO NOTHING;
CREATE TABLE IF NOT EXISTS crm_contatto_categorie (
  contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  categoria TEXT NOT NULL REFERENCES crm_categorie(nome) ON UPDATE CASCADE ON DELETE RESTRICT,
  motivazione TEXT NOT NULL CHECK (char_length(motivazione) >= 3),
  assegnata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assegnata_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  PRIMARY KEY (contatto_id, categoria)
);

-- chi lavora dove, e in che periodo: un incarico finito non si presenta come attuale
CREATE TABLE IF NOT EXISTS crm_relazioni (
  id SERIAL PRIMARY KEY,
  persona_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  organizzazione_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  ruolo TEXT,
  dal DATE,
  al DATE,
  fonte TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (persona_id <> organizzazione_id),
  CHECK (dal IS NULL OR al IS NULL OR al >= dal)
);
CREATE INDEX IF NOT EXISTS crm_relazioni_persona ON crm_relazioni (persona_id);
CREATE INDEX IF NOT EXISTS crm_relazioni_org ON crm_relazioni (organizzazione_id);

-- recapiti aggiuntivi (altre email, telefoni, siti, indirizzi), ciascuno con la sua fonte e l'ultima verifica
CREATE TABLE IF NOT EXISTS crm_recapiti (
  id SERIAL PRIMARY KEY,
  contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('email', 'telefono', 'sito', 'indirizzo')),
  valore_cifrato TEXT NOT NULL,
  valore_hash TEXT NOT NULL,
  fonte TEXT,
  verificato_il DATE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (contatto_id, tipo, valore_hash)
);

-- storico delle modifiche: chi, quando, quale dato, da quale fonte (i valori sono cifrati)
CREATE TABLE IF NOT EXISTS crm_storico (
  id BIGSERIAL PRIMARY KEY,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE CASCADE,
  utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  campo TEXT NOT NULL,
  prima_cifrato TEXT,
  dopo_cifrato TEXT,
  fonte TEXT,
  quando TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS crm_storico_contatto ON crm_storico (contatto_id, quando DESC);
