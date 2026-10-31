-- Banco di lavoro: postazioni (PC di montaggio) che eseguono per gli agenti inventari, fotogrammi, silenzi e ffmpeg.
CREATE TABLE IF NOT EXISTS banco_postazioni (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  attiva BOOLEAN NOT NULL DEFAULT TRUE,
  versione TEXT,
  ultimo_contatto TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS banco_lavori (
  id SERIAL PRIMARY KEY,
  postazione_id INTEGER,
  agente_id INTEGER,
  progetto_id INTEGER,
  tipo TEXT NOT NULL CHECK (tipo IN ('inventario', 'fotogrammi', 'silenzi', 'ffmpeg')),
  parametri JSONB NOT NULL DEFAULT '{}'::jsonb,
  stato TEXT NOT NULL DEFAULT 'in_attesa' CHECK (stato IN ('in_attesa', 'in_corso', 'fatto', 'errore')),
  risultato TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  iniziato_il TIMESTAMPTZ,
  finito_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS banco_lavori_stato ON banco_lavori (stato, id);
CREATE TABLE IF NOT EXISTS banco_file (
  id SERIAL PRIMARY KEY,
  lavoro_id INTEGER NOT NULL,
  nome TEXT NOT NULL,
  mime TEXT NOT NULL DEFAULT 'image/jpeg',
  dati BYTEA NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS banco_file_lavoro ON banco_file (lavoro_id);
