-- FARO, fase 1: lettura approfondita (scheda del bando), setaccio di chi ha il reparto Bandi, candidatura che diventa progetto,
-- costo per giro, collaudo con verifica sulla pagina, sezione mensile «Nuove imprese», filone clienti predisposto e spento.

-- profili: le mie societa' (impresa), profili tipo (esterno) e clienti o potenziali clienti (cliente, anche dal CRM)
ALTER TABLE faro_profili DROP CONSTRAINT IF EXISTS faro_profili_tipo_check;
ALTER TABLE faro_profili ADD CONSTRAINT faro_profili_tipo_check CHECK (tipo IN ('impresa','esterno','cliente'));
ALTER TABLE faro_profili ADD COLUMN IF NOT EXISTS cadenza TEXT NOT NULL DEFAULT 'settimanale';
ALTER TABLE faro_profili DROP CONSTRAINT IF EXISTS faro_profili_cadenza_check;
ALTER TABLE faro_profili ADD CONSTRAINT faro_profili_cadenza_check CHECK (cadenza IN ('settimanale','mensile'));
ALTER TABLE faro_profili ADD COLUMN IF NOT EXISTS contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL;
UPDATE faro_profili SET cadenza = 'mensile' WHERE nome = 'Nuove imprese' AND cadenza = 'settimanale';

-- bandi: scheda della lettura approfondita, setaccio, progetto della candidatura, verifica sulla pagina
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS scheda JSONB;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS scheda_stato TEXT NOT NULL DEFAULT '';
ALTER TABLE faro_bandi DROP CONSTRAINT IF EXISTS faro_bandi_scheda_stato_check;
ALTER TABLE faro_bandi ADD CONSTRAINT faro_bandi_scheda_stato_check CHECK (scheda_stato IN ('','in_corso','pronta','errore'));
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS scheda_il TIMESTAMPTZ;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS scheda_costo NUMERIC(10,4) NOT NULL DEFAULT 0;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS scheda_errore TEXT;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS setaccio_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS setaccio_il TIMESTAMPTZ;
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS verifica TEXT NOT NULL DEFAULT '';
ALTER TABLE faro_bandi DROP CONSTRAINT IF EXISTS faro_bandi_verifica_check;
ALTER TABLE faro_bandi ADD CONSTRAINT faro_bandi_verifica_check CHECK (verifica IN ('','confermato','da_controllare','non_trovato'));
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS verifica_nota TEXT NOT NULL DEFAULT '';
ALTER TABLE faro_bandi ADD COLUMN IF NOT EXISTS giudizio_umano TEXT NOT NULL DEFAULT '';
ALTER TABLE faro_bandi DROP CONSTRAINT IF EXISTS faro_bandi_giudizio_umano_check;
ALTER TABLE faro_bandi ADD CONSTRAINT faro_bandi_giudizio_umano_check CHECK (giudizio_umano IN ('','giusto','sbagliato','inventato'));
CREATE INDEX IF NOT EXISTS faro_bandi_giro ON faro_bandi (giro_id);

-- giri: costo del modello e collaudo
ALTER TABLE faro_giri ADD COLUMN IF NOT EXISTS costo NUMERIC(10,4) NOT NULL DEFAULT 0;
ALTER TABLE faro_giri ADD COLUMN IF NOT EXISTS collaudo BOOLEAN NOT NULL DEFAULT FALSE;

-- fonti: controllo degli indirizzi
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS raggiungibile BOOLEAN;
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS controllo_il TIMESTAMPTZ;
ALTER TABLE faro_fonti ADD COLUMN IF NOT EXISTS controllo_esito TEXT NOT NULL DEFAULT '';

-- FILONE 2, clienti: solo il modello dei dati. Una scheda opportunita' per abbinamento bando-cliente, collegabile al CRM.
-- Nulla parte verso l'esterno: lo stato 'approvata' lo mette solo il titolare.
CREATE TABLE IF NOT EXISTS faro_opportunita (
  id SERIAL PRIMARY KEY,
  bando_id INTEGER NOT NULL REFERENCES faro_bandi(id) ON DELETE CASCADE,
  profilo_id INTEGER NOT NULL REFERENCES faro_profili(id) ON DELETE CASCADE,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  crm_opportunita_id INTEGER REFERENCES crm_opportunita(id) ON DELETE SET NULL,
  a_chi_serve TEXT NOT NULL DEFAULT '',
  cosa_finanziare TEXT NOT NULL DEFAULT '',
  cosa_possiamo_fare TEXT NOT NULL DEFAULT '',
  valore_per_noi NUMERIC(12,2),
  valore_nota TEXT NOT NULL DEFAULT '',
  prossimo_passo TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'bozza' CHECK (stato IN ('bozza','approvata','proposta','vinta','persa','scartata')),
  approvata_da INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  approvata_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (bando_id, profilo_id)
);
CREATE INDEX IF NOT EXISTS faro_opportunita_contatto ON faro_opportunita (contatto_id);

INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_clienti_acceso', '0') ON CONFLICT (chiave) DO NOTHING;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_lettura', 'interessanti') ON CONFLICT (chiave) DO NOTHING;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('faro_modello_lettura', 'claude-sonnet-5-5') ON CONFLICT (chiave) DO NOTHING;
