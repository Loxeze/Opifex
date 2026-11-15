-- Social per marchio (2.61): un agente per marchio (Renovatio, Lorenzo, Castello di Montarrenti, Filigrana...), la scheda del marchio
-- (tono, stile, colori, temi), i canali che gli appartengono, i commenti con le risposte preparate e approvate.
CREATE TABLE IF NOT EXISTS social_marchi (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'impresa' CHECK (tipo IN ('impresa', 'personale', 'progetto')),
  azienda_id INTEGER REFERENCES aziende(id) ON DELETE SET NULL,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  colore TEXT NOT NULL DEFAULT '#8A6A2F',
  reti TEXT[] NOT NULL DEFAULT '{}',                 -- dove e' presente (anche se non ancora collegato)
  scheda JSONB NOT NULL DEFAULT '{}',                -- tono, stile, colori [{hex, nome, quota}], temi, pubblico, da_evitare, cosa_funziona, note
  note_lorenzo TEXT NOT NULL DEFAULT '',             -- cosa vuole Lorenzo per questo marchio, a parole
  analizzata_il TIMESTAMPTZ,
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS social_marchi_nome ON social_marchi (lower(nome));

CREATE TABLE IF NOT EXISTS social_marchi_canali (
  id SERIAL PRIMARY KEY,
  marchio_id INTEGER NOT NULL REFERENCES social_marchi(id) ON DELETE CASCADE,
  rete TEXT NOT NULL,
  indirizzo TEXT NOT NULL DEFAULT '',                -- link pubblico del profilo
  canale_id TEXT,                                    -- canale collegato: 'n:<id>' (diretto) o id Buffer
  UNIQUE (marchio_id, rete)
);

CREATE TABLE IF NOT EXISTS social_commenti (
  id SERIAL PRIMARY KEY,
  marchio_id INTEGER REFERENCES social_marchi(id) ON DELETE CASCADE,
  rete TEXT NOT NULL,
  canale_nativo_id INTEGER REFERENCES canali_nativi(id) ON DELETE SET NULL,
  ext_id TEXT,                                       -- id del commento sulla rete (vuoto se incollato a mano)
  post_url TEXT NOT NULL DEFAULT '',
  post_testo TEXT NOT NULL DEFAULT '',
  autore TEXT NOT NULL DEFAULT '',
  testo TEXT NOT NULL,
  ricevuto_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  risposta TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'da_rispondere' CHECK (stato IN ('da_rispondere', 'proposta', 'pubblicata', 'copiata', 'scartata', 'errore')),
  origine TEXT NOT NULL DEFAULT 'api' CHECK (origine IN ('api', 'manuale')),
  errore TEXT NOT NULL DEFAULT '',
  pubblicata_il TIMESTAMPTZ,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS social_commenti_ext ON social_commenti (rete, ext_id) WHERE ext_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS social_commenti_stato ON social_commenti (stato, marchio_id);
