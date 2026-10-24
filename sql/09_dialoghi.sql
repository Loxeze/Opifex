-- Dialoghi tra agenti: modello dedicato ai dialoghi, conversazioni, messaggi, limiti
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS modello_dialogo TEXT;
ALTER TABLE agenti ADD COLUMN IF NOT EXISTS dialoghi_attivi BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE costi_api ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'lavoro' CHECK (tipo IN ('lavoro', 'dialogo'));

CREATE TABLE IF NOT EXISTS impostazioni_sistema (
  chiave TEXT PRIMARY KEY,
  valore TEXT NOT NULL
);
INSERT INTO impostazioni_sistema (chiave, valore) VALUES
  ('dialoghi_max_messaggi', '8'),              -- messaggi massimi per conversazione
  ('dialoghi_max_domande', '3'),               -- domande che un agente puo' fare durante un solo compito
  ('dialoghi_budget_token_giornaliero', '200000'),
  ('modello_dialogo_predefinito', 'claude-haiku-5-5')
ON CONFLICT (chiave) DO NOTHING;

CREATE TABLE IF NOT EXISTS conversazioni (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  fascia_dati TEXT NOT NULL DEFAULT 'pubblico' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  iniziata_da_agente INTEGER REFERENCES agenti(id),
  iniziata_da_utente INTEGER REFERENCES utenti(id),
  stato TEXT NOT NULL DEFAULT 'aperta' CHECK (stato IN ('aperta', 'chiusa')),
  creata_il TIMESTAMPTZ DEFAULT NOW(),
  ultimo_messaggio_il TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messaggi_agenti (
  id SERIAL PRIMARY KEY,
  conversazione_id INTEGER NOT NULL REFERENCES conversazioni(id) ON DELETE CASCADE,
  da_agente_id INTEGER REFERENCES agenti(id),
  a_agente_id INTEGER REFERENCES agenti(id),
  testo TEXT NOT NULL,
  modello TEXT,
  token_input INTEGER,
  token_output INTEGER,
  creato_il TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messaggi_conv ON messaggi_agenti (conversazione_id, id);
