-- FARO dentro Opifex: ricerca dei bandi fatta da un agente (Faro), con registro delle fonti, profili per cui cercare,
-- bandi segnalati con la fonte, abbinamenti bando-profilo, avvisi di scadenza e bollettino settimanale.
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS faro BOOLEAN NOT NULL DEFAULT FALSE;

-- Registro delle fonti originali (enti, regioni, ministeri, fondazioni, programmi europei): FARO non dipende da un aggregatore
CREATE TABLE IF NOT EXISTS faro_fonti (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  categoria TEXT NOT NULL DEFAULT 'Altro',
  regione TEXT,
  attiva BOOLEAN NOT NULL DEFAULT TRUE,
  origine TEXT NOT NULL DEFAULT 'manuale',
  trovati INTEGER NOT NULL DEFAULT 0,
  ultima_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS faro_fonti_giro ON faro_fonti (attiva, ultima_il);

-- Per chi si cerca: le imprese di Lorenzo (tipo 'impresa') e i profili tipo per il bollettino a terzi (tipo 'esterno', es. piccolo museo locale)
CREATE TABLE IF NOT EXISTS faro_profili (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,
  tipo TEXT NOT NULL DEFAULT 'impresa' CHECK (tipo IN ('impresa','esterno')),
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  descrizione TEXT NOT NULL,
  regioni TEXT NOT NULL DEFAULT '',
  importo_min INTEGER NOT NULL DEFAULT 5000 CHECK (importo_min >= 0),
  copertura_min INTEGER NOT NULL DEFAULT 50 CHECK (copertura_min BETWEEN 0 AND 100),
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faro_giri (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  modo TEXT NOT NULL DEFAULT 'fonti' CHECK (modo IN ('fonti','portali','libero')),
  fonti INTEGER[] NOT NULL DEFAULT '{}',
  richiesta TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','concluso','errore')),
  segnalati INTEGER NOT NULL DEFAULT 0,
  scartati INTEGER NOT NULL DEFAULT 0,
  esito TEXT,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  concluso_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS faro_giri_stato ON faro_giri (stato, creato_il DESC);

-- stato: nuovo (appena trovato) | interessante (passato al primo setaccio) | candidatura (ci si lavora) | scartato | archiviato (scaduto)
CREATE TABLE IF NOT EXISTS faro_bandi (
  id SERIAL PRIMARY KEY,
  giro_id INTEGER REFERENCES faro_giri(id) ON DELETE SET NULL,
  fonte_id INTEGER REFERENCES faro_fonti(id) ON DELETE SET NULL,
  titolo TEXT NOT NULL,
  ente TEXT NOT NULL,
  url TEXT NOT NULL,
  url_chiave TEXT NOT NULL UNIQUE,
  scadenza DATE,
  scadenza_nota TEXT,
  importo NUMERIC(14,2),
  importo_nota TEXT,
  copertura INTEGER CHECK (copertura BETWEEN 0 AND 100),
  beneficiari TEXT,
  regione TEXT,
  categoria TEXT,
  sintesi TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'nuovo' CHECK (stato IN ('nuovo','interessante','candidatura','scartato','archiviato')),
  nota TEXT NOT NULL DEFAULT '',
  avviso_scadenza_il TIMESTAMPTZ,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS faro_bandi_stato ON faro_bandi (stato, scadenza);
CREATE INDEX IF NOT EXISTS faro_bandi_titolo ON faro_bandi (lower(titolo), lower(ente));

CREATE TABLE IF NOT EXISTS faro_abbinamenti (
  bando_id INTEGER NOT NULL REFERENCES faro_bandi(id) ON DELETE CASCADE,
  profilo_id INTEGER NOT NULL REFERENCES faro_profili(id) ON DELETE CASCADE,
  esito TEXT NOT NULL DEFAULT 'adatto' CHECK (esito IN ('adatto','da_valutare')),
  motivo TEXT NOT NULL,
  PRIMARY KEY (bando_id, profilo_id)
);
CREATE INDEX IF NOT EXISTS faro_abbinamenti_profilo ON faro_abbinamenti (profilo_id);

CREATE TABLE IF NOT EXISTS faro_bollettini (
  id SERIAL PRIMARY KEY,
  profilo_id INTEGER NOT NULL REFERENCES faro_profili(id) ON DELETE CASCADE,
  dal DATE NOT NULL,
  al DATE NOT NULL,
  bandi INTEGER NOT NULL DEFAULT 0,
  testo TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS faro_bollettini_profilo ON faro_bollettini (profilo_id, id DESC);
