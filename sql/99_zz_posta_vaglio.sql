-- Posta letta e filtrata SOLO dal modello locale: le email vagliate e le «situazioni» (memoria dei dialoghi)
CREATE TABLE IF NOT EXISTS posta_situazioni (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  interlocutori TEXT NOT NULL DEFAULT '',
  riassunto TEXT NOT NULL DEFAULT '',
  aperta BOOLEAN NOT NULL DEFAULT TRUE,
  email_n INTEGER NOT NULL DEFAULT 0,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS posta_vaglio (
  id SERIAL PRIMARY KEY,
  origine TEXT NOT NULL CHECK (origine IN ('gmail', 'imap')),
  casella_id INTEGER NOT NULL,
  msg_id TEXT NOT NULL,
  casella TEXT NOT NULL DEFAULT '',
  data TIMESTAMPTZ,
  mittente TEXT NOT NULL DEFAULT '',
  oggetto TEXT NOT NULL DEFAULT '',
  categoria TEXT NOT NULL DEFAULT 'da_vagliare' CHECK (categoria IN ('da_vagliare', 'importante', 'normale', 'scartabile')),
  urgenza SMALLINT NOT NULL DEFAULT 0,
  riassunto TEXT NOT NULL DEFAULT '',
  motivo TEXT NOT NULL DEFAULT '',
  situazione_id INTEGER REFERENCES posta_situazioni(id) ON DELETE SET NULL,
  letta BOOLEAN NOT NULL DEFAULT FALSE,
  vagliata_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (origine, casella_id, msg_id)
);
CREATE INDEX IF NOT EXISTS posta_vaglio_da_leggere ON posta_vaglio (categoria, letta, data DESC);
CREATE INDEX IF NOT EXISTS posta_vaglio_situazione ON posta_vaglio (situazione_id, data DESC);
