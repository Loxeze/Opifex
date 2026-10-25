-- Iniziative trasversali: un manager apre un'opportunita', che diventa una task madre con sottotask per gli agenti (anche di altri dipartimenti)
CREATE TABLE IF NOT EXISTS iniziative (
  id SERIAL PRIMARY KEY,
  titolo TEXT NOT NULL,
  descrizione TEXT,
  stato TEXT NOT NULL DEFAULT 'in_corso' CHECK (stato IN ('da_approvare', 'in_corso', 'conclusa', 'rifiutata')),
  aperta_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES task(id) ON DELETE SET NULL,
  budget_token INTEGER,
  sintesi TEXT,
  decisa_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  decisa_il TIMESTAMPTZ,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  conclusa_il TIMESTAMPTZ
);
ALTER TABLE task ADD COLUMN IF NOT EXISTS iniziativa_id INTEGER REFERENCES iniziative(id) ON DELETE SET NULL;
ALTER TABLE task ADD COLUMN IF NOT EXISTS esegue_agente BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS task_iniziativa ON task(iniziativa_id);
-- Avvisi tra agenti: il manager di un dipartimento viene informato quando altri lavorano su cose del suo ambito
CREATE TABLE IF NOT EXISTS avvisi_agente (
  id SERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  testo TEXT NOT NULL,
  iniziativa_id INTEGER REFERENCES iniziative(id) ON DELETE CASCADE,
  letto BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS avvisi_agente_da_leggere ON avvisi_agente(agente_id) WHERE NOT letto;
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('iniziative_soglia_token', '40000'), ('iniziative_max_rami', '6')
ON CONFLICT (chiave) DO NOTHING;
