-- 1.22.0: CRM con schede (interazioni, opportunita', promemoria) e riunioni collegate a progetti e persone
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS responsabile_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS prossimo_passo TEXT;
ALTER TABLE crm_contatti ADD COLUMN IF NOT EXISTS prossimo_passo_il DATE;
CREATE INDEX IF NOT EXISTS crm_contatti_passo ON crm_contatti (prossimo_passo_il) WHERE prossimo_passo_il IS NOT NULL;

CREATE TABLE IF NOT EXISTS crm_interazioni (
    id SERIAL PRIMARY KEY,
    contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
    quando TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    canale TEXT NOT NULL CHECK (canale IN ('email', 'telefono', 'incontro', 'riunione', 'messaggio', 'social', 'altro')),
    direzione TEXT NOT NULL DEFAULT 'uscita' CHECK (direzione IN ('uscita', 'entrata')),
    da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
    da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
    oggetto TEXT,
    esito TEXT NOT NULL DEFAULT 'altro' CHECK (esito IN ('nessuna_risposta', 'risposto', 'interessato', 'non_interessato', 'da_richiamare', 'altro')),
    note_cifrate TEXT,
    riunione_id INTEGER REFERENCES riunioni_importate(id) ON DELETE SET NULL,
    progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS crm_interazioni_contatto ON crm_interazioni (contatto_id, quando DESC);

CREATE TABLE IF NOT EXISTS crm_opportunita (
    id SERIAL PRIMARY KEY,
    contatto_id INTEGER NOT NULL REFERENCES crm_contatti(id) ON DELETE CASCADE,
    titolo TEXT NOT NULL CHECK (char_length(titolo) BETWEEN 3 AND 200),
    tipo TEXT NOT NULL DEFAULT 'altro' CHECK (tipo IN ('bando', 'cliente', 'partnership', 'sponsor', 'consulenza', 'altro')),
    stato TEXT NOT NULL DEFAULT 'nuova' CHECK (stato IN ('nuova', 'contattato', 'in_trattativa', 'vinta', 'persa', 'in_pausa')),
    valore_euro NUMERIC(12, 2),
    azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
    progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
    responsabile_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
    prossima_azione TEXT,
    scadenza DATE,
    note_cifrate TEXT,
    creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    chiusa_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS crm_opportunita_stato ON crm_opportunita (stato, scadenza);

ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS data_riunione DATE;
ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS partecipanti JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE task_proposte ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
