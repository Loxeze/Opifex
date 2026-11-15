-- Padre Casati 3.0: competenze a tre strati (carta d'identita', manuale a sezioni, fonti), livelli senza tetto (studio + esami + pratica),
-- target di studio (canali, playlist, video, temi), esami notturni, richieste degli agenti.
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS carta TEXT NOT NULL DEFAULT '';           -- a cosa serve e quando usarla (1-2 righe, sempre nel prompt di chi ce l'ha)
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS parole TEXT NOT NULL DEFAULT '';          -- parole chiave per riconoscere i compiti in cui serve
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS versione INTEGER NOT NULL DEFAULT 0;
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS aggiornata_il TIMESTAMPTZ;
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS drive_id TEXT;
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS da_drive BOOLEAN NOT NULL DEFAULT FALSE;  -- la copia su Drive va riscritta
ALTER TABLE competenze ADD COLUMN IF NOT EXISTS agenti_valutati BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS competenze_sezioni (
  id SERIAL PRIMARY KEY,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  testo TEXT NOT NULL DEFAULT '',
  ordine INTEGER NOT NULL DEFAULT 0,
  aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS competenze_sezioni_titolo ON competenze_sezioni (competenza_id, lower(titolo));

CREATE TABLE IF NOT EXISTS casati_target (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('canale', 'playlist', 'video', 'tema')),
  indirizzo TEXT NOT NULL,                 -- link YouTube, oppure il tema da cercare
  nome TEXT NOT NULL DEFAULT '',
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  stato TEXT NOT NULL DEFAULT 'attivo' CHECK (stato IN ('proposto', 'attivo', 'in_pausa', 'finito', 'rifiutato')),
  proposto_da TEXT NOT NULL DEFAULT 'lorenzo' CHECK (proposto_da IN ('lorenzo', 'casati')),
  motivo TEXT NOT NULL DEFAULT '',
  priorita INTEGER NOT NULL DEFAULT 0,
  video_totali INTEGER NOT NULL DEFAULT 0,
  ultimo_elenco TIMESTAMPTZ,
  errore TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS casati_target_unico ON casati_target (competenza_id, lower(indirizzo));

CREATE TABLE IF NOT EXISTS competenze_fonti (
  id SERIAL PRIMARY KEY,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  target_id INTEGER REFERENCES casati_target(id) ON DELETE SET NULL,
  tipo TEXT NOT NULL DEFAULT 'video',
  rif TEXT NOT NULL,                       -- id del video YouTube, o indirizzo del documento
  titolo TEXT NOT NULL DEFAULT '',
  autore TEXT NOT NULL DEFAULT '',
  durata INTEGER,                          -- secondi
  pubblicato TEXT NOT NULL DEFAULT '',
  appunti TEXT NOT NULL DEFAULT '',        -- cosa ne ha ricavato Padre Casati (con i minuti di riferimento)
  stato TEXT NOT NULL DEFAULT 'da_studiare' CHECK (stato IN ('da_studiare', 'studiata', 'integrata', 'saltata', 'errore')),
  errore TEXT NOT NULL DEFAULT '',
  tentativi INTEGER NOT NULL DEFAULT 0,
  studiata_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (competenza_id, rif)
);
CREATE INDEX IF NOT EXISTS competenze_fonti_stato ON competenze_fonti (stato, competenza_id);

-- livello senza tetto: si sale solo superando l'esame; oltre il primo serve anche la pratica; il tetto lo da' lo studio
CREATE TABLE IF NOT EXISTS agenti_competenze3 (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  livello INTEGER NOT NULL DEFAULT 0 CHECK (livello >= 0),
  esami_superati INTEGER NOT NULL DEFAULT 0,
  esami_falliti INTEGER NOT NULL DEFAULT 0,
  usi INTEGER NOT NULL DEFAULT 0,
  usi_dal_livello INTEGER NOT NULL DEFAULT 0,  -- pratica dall'ultima promozione
  esame_in_sospeso BOOLEAN NOT NULL DEFAULT FALSE,   -- esame superato, manca la pratica per salire
  prossimo_esame DATE,
  ultimo_esame_il TIMESTAMPTZ,
  assegnata_da TEXT NOT NULL DEFAULT 'casati',
  nota TEXT NOT NULL DEFAULT '',
  assegnata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (agente_id, competenza_id)
);

CREATE TABLE IF NOT EXISTS competenze_esami (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  competenza_id INTEGER NOT NULL REFERENCES competenze(id) ON DELETE CASCADE,
  livello_tentato INTEGER NOT NULL,
  domande JSONB NOT NULL DEFAULT '[]'::jsonb,
  voto INTEGER,                            -- 0-100
  superato BOOLEAN,
  commento TEXT NOT NULL DEFAULT '',
  fatto_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS competenze_esami_quando ON competenze_esami (fatto_il DESC);

CREATE TABLE IF NOT EXISTS competenze_richieste (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE CASCADE,
  tema TEXT NOT NULL,
  motivo TEXT NOT NULL DEFAULT '',
  competenza_id INTEGER REFERENCES competenze(id) ON DELETE SET NULL,
  stato TEXT NOT NULL DEFAULT 'nuova' CHECK (stato IN ('nuova', 'assegnata', 'in_studio', 'chiusa')),
  risposta TEXT NOT NULL DEFAULT '',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS casati_registro (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,
  testo TEXT NOT NULL,
  quando TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS casati_registro_quando ON casati_registro (quando DESC);
