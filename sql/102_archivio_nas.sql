-- 1.81.0: archivio sul NAS (foto e video). Sul NAS gira un piccolo programma che cataloga i file e manda a Opifex solo schede e miniature.
CREATE TABLE IF NOT EXISTS archivio_connettori (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  versione TEXT,
  ultimo_contatto TIMESTAMPTZ,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS archivio_cartelle (
  id SERIAL PRIMARY KEY,
  connettore_id INTEGER NOT NULL REFERENCES archivio_connettori(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  percorso TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL DEFAULT 'misto' CHECK (tipo IN ('foto', 'video', 'misto')),
  prefisso_pc TEXT NOT NULL DEFAULT '',
  descrivi BOOLEAN NOT NULL DEFAULT TRUE,
  trascrivi BOOLEAN NOT NULL DEFAULT FALSE,
  progetto_id INTEGER,
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  attiva BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_scansione TIMESTAMPTZ,
  errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS archivio_file (
  id BIGSERIAL PRIMARY KEY,
  cartella_id INTEGER NOT NULL REFERENCES archivio_cartelle(id) ON DELETE CASCADE,
  rel TEXT NOT NULL,
  nome TEXT NOT NULL,
  estensione TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL CHECK (tipo IN ('foto', 'video', 'audio')),
  dimensione BIGINT NOT NULL DEFAULT 0,
  modificato_il TIMESTAMPTZ,
  visto_scan BIGINT NOT NULL DEFAULT 0,
  assente BOOLEAN NOT NULL DEFAULT FALSE,
  durata_s REAL,
  larghezza INTEGER,
  altezza INTEGER,
  codec TEXT,
  fps REAL,
  scattato_il TIMESTAMPTZ,
  fotocamera TEXT,
  luogo JSONB,
  progetto_id INTEGER,
  descrizione TEXT,
  descritto_il TIMESTAMPTZ,
  etichette TEXT[] NOT NULL DEFAULT '{}',
  trascrizione TEXT,
  stato TEXT NOT NULL DEFAULT 'da_analizzare' CHECK (stato IN ('da_analizzare', 'analizzato', 'senza_miniatura', 'errore')),
  errore TEXT,
  ricerca TSVECTOR,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cartella_id, rel)
);
CREATE INDEX IF NOT EXISTS idx_archivio_ricerca ON archivio_file USING GIN (ricerca);
CREATE INDEX IF NOT EXISTS idx_archivio_stato ON archivio_file (stato) WHERE NOT assente;
CREATE INDEX IF NOT EXISTS idx_archivio_progetto ON archivio_file (progetto_id);
CREATE OR REPLACE FUNCTION archivio_indicizza() RETURNS trigger AS $$
BEGIN
  NEW.ricerca := to_tsvector('italian', replace(replace(coalesce(NEW.rel, ''), '/', ' '), '_', ' ') || ' ' || coalesce(NEW.descrizione, '') || ' ' ||
                 coalesce(array_to_string(NEW.etichette, ' '), '') || ' ' || left(coalesce(NEW.trascrizione, ''), 200000));
  RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_archivio_indicizza ON archivio_file;
CREATE TRIGGER trg_archivio_indicizza BEFORE INSERT OR UPDATE OF rel, descrizione, etichette, trascrizione ON archivio_file FOR EACH ROW EXECUTE FUNCTION archivio_indicizza();
CREATE TABLE IF NOT EXISTS archivio_miniature (
  file_id BIGINT NOT NULL REFERENCES archivio_file(id) ON DELETE CASCADE,
  ordine SMALLINT NOT NULL,
  dati BYTEA NOT NULL,
  PRIMARY KEY (file_id, ordine)
);
CREATE TABLE IF NOT EXISTS archivio_richieste (
  id SERIAL PRIMARY KEY,
  file_id BIGINT NOT NULL REFERENCES archivio_file(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('foto', 'trascrizione')),
  lato_max INTEGER,
  stato TEXT NOT NULL DEFAULT 'in_attesa' CHECK (stato IN ('in_attesa', 'consegnata', 'errore')),
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  evasa_il TIMESTAMPTZ,
  errore TEXT,
  mime TEXT,
  dati BYTEA,
  parziale TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_archivio_richieste_stato ON archivio_richieste (stato, id);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agenti' AND column_name = 'archivio_attivo') THEN
    ALTER TABLE agenti ADD COLUMN archivio_attivo BOOLEAN NOT NULL DEFAULT FALSE;
    UPDATE agenti SET archivio_attivo = TRUE WHERE divisione_id IN (SELECT id FROM divisioni WHERE nome IN ('Contenuti', 'Social'));
  END IF;
END $$;
