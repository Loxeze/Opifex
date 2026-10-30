-- 1.74.0: caricamento in blocco, relazioni tra documenti, giro di aggiornamento con domande brevi
CREATE TABLE IF NOT EXISTS caricamenti_blocco (
  id SERIAL PRIMARY KEY,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('in_corso','concluso','errore')),
  totale INTEGER NOT NULL DEFAULT 0,
  caricati INTEGER NOT NULL DEFAULT 0,
  saltati INTEGER NOT NULL DEFAULT 0,
  problemi JSONB NOT NULL DEFAULT '[]'::jsonb,
  creato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS documenti_relazioni (
  documento_a INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  documento_b INTEGER NOT NULL REFERENCES documenti(id) ON DELETE CASCADE,
  somiglianza REAL NOT NULL,
  PRIMARY KEY (documento_a, documento_b),
  CHECK (documento_a < documento_b)
);
CREATE INDEX IF NOT EXISTS documenti_relazioni_b ON documenti_relazioni (documento_b);
CREATE TABLE IF NOT EXISTS giri_aggiornamento (
  id SERIAL PRIMARY KEY,
  stato TEXT NOT NULL DEFAULT 'aperto' CHECK (stato IN ('aperto','chiuso')),
  origine TEXT NOT NULL DEFAULT 'automatico',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  chiuso_il TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS domande_giro (
  id SERIAL PRIMARY KEY,
  giro_id INTEGER NOT NULL REFERENCES giri_aggiornamento(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  domanda TEXT NOT NULL,
  risposta TEXT,
  stato TEXT NOT NULL DEFAULT 'attesa' CHECK (stato IN ('attesa','risposta','saltata')),
  risposta_il TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS fatti_condivisi (
  id SERIAL PRIMARY KEY,
  testo TEXT NOT NULL,
  domanda_id INTEGER REFERENCES domande_giro(id) ON DELETE SET NULL,
  attivo BOOLEAN NOT NULL DEFAULT TRUE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
