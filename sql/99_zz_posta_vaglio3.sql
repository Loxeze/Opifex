-- Posta 2.56: il filtro impara da Lorenzo (mi interessa / non mi interessa, email aperte, compiti creati), compiti dalle email, letta anche nella casella
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS interessa BOOLEAN;
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS task_id INTEGER REFERENCES task(id) ON DELETE SET NULL;
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS non_letta_casella BOOLEAN;
ALTER TABLE posta_vaglio ADD COLUMN IF NOT EXISTS imparata TEXT NOT NULL DEFAULT '';

-- ogni segnale di interesse: esplicito (pulsante), dal comportamento (aperta in Opifex, letta nella casella, compito creato)
CREATE TABLE IF NOT EXISTS posta_interesse (
  id SERIAL PRIMARY KEY,
  vaglio_id INTEGER REFERENCES posta_vaglio(id) ON DELETE CASCADE,
  mittente TEXT NOT NULL DEFAULT '',       -- indirizzo, minuscolo
  dominio TEXT NOT NULL DEFAULT '',
  oggetto TEXT NOT NULL DEFAULT '',
  peso SMALLINT NOT NULL,                  -- +2 mi interessa / compito, +1 aperta o letta, -2 non mi interessa
  fonte TEXT NOT NULL CHECK (fonte IN ('pulsante', 'aperta', 'letta_altrove', 'compito')),
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (vaglio_id, fonte)
);
CREATE INDEX IF NOT EXISTS posta_interesse_mittente ON posta_interesse (mittente);
CREATE INDEX IF NOT EXISTS posta_interesse_dominio ON posta_interesse (dominio);
