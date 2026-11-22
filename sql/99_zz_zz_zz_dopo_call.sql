-- 2.75: dopo la call, promemoria sulla proposta, risposte pronte
ALTER TABLE crm_analisi_call ADD COLUMN IF NOT EXISTS riassunto TEXT NOT NULL DEFAULT '';
ALTER TABLE crm_analisi_call ADD COLUMN IF NOT EXISTS passi JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE preventivi ADD COLUMN IF NOT EXISTS sollecito_il TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS risposte_pronte (
  id SERIAL PRIMARY KEY,
  domanda TEXT NOT NULL,
  risposta TEXT NOT NULL,
  attiva BOOLEAN NOT NULL DEFAULT TRUE,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
