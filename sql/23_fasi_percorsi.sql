-- Fasi di lavoro di un agente (facoltative) e percorsi: un lavoro svolto fase per fase, con approvazioni
CREATE TABLE IF NOT EXISTS fasi_agente (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  posizione INTEGER NOT NULL,
  titolo TEXT NOT NULL,
  istruzioni TEXT NOT NULL DEFAULT '',
  approvazione BOOLEAN NOT NULL DEFAULT TRUE,        -- a fine fase si ferma e attende la decisione umana
  parere_superiore BOOLEAN NOT NULL DEFAULT FALSE,   -- il superiore (manager) scrive un parere prima della decisione
  UNIQUE (agente_id, posizione)
);

CREATE TABLE IF NOT EXISTS percorsi_lavoro (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  titolo TEXT NOT NULL,
  brief TEXT NOT NULL,
  fascia_dati TEXT NOT NULL DEFAULT 'interno' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL,
  fasi JSONB NOT NULL,                               -- copia delle fasi al momento dell'avvio
  fase_corrente INTEGER NOT NULL DEFAULT 1,
  stato TEXT NOT NULL DEFAULT 'in_elaborazione' CHECK (stato IN ('in_elaborazione', 'in_attesa', 'completato', 'annullato', 'errore')),
  errore TEXT,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS percorsi_stato ON percorsi_lavoro (stato, aggiornato_il DESC);

CREATE TABLE IF NOT EXISTS esiti_fasi (
  id SERIAL PRIMARY KEY,
  percorso_id INTEGER NOT NULL REFERENCES percorsi_lavoro(id) ON DELETE CASCADE,
  posizione INTEGER NOT NULL,
  tentativo INTEGER NOT NULL DEFAULT 1,
  testo TEXT NOT NULL,
  parere_superiore TEXT,
  decisione TEXT CHECK (decisione IN ('approvata', 'modifiche')),
  nota TEXT,
  decisa_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deciso_il TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS esiti_percorso ON esiti_fasi (percorso_id, posizione, tentativo);
