-- 2.65.0: imbuto, call (calendario e PLAUD), analisi delle call, quadro di settore, promemoria chiesti dai contatti

-- «ci sentiamo a marzo»: la data che il contatto ha indicato
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS richiamo_il DATE;
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS richiamo_nota TEXT NOT NULL DEFAULT '';
ALTER TABLE campagne_posta_dest ADD COLUMN IF NOT EXISTS richiamo_fatto BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS campagne_posta_dest_richiamo ON campagne_posta_dest (richiamo_il) WHERE richiamo_il IS NOT NULL AND NOT richiamo_fatto;

-- la call: fissata (dal calendario) e fatta (dal resoconto PLAUD)
ALTER TABLE crm_opportunita ADD COLUMN IF NOT EXISTS call_il TIMESTAMPTZ;
ALTER TABLE crm_opportunita ADD COLUMN IF NOT EXISTS call_evento TEXT;
ALTER TABLE crm_opportunita ADD COLUMN IF NOT EXISTS riunione_id INTEGER REFERENCES riunioni_importate(id) ON DELETE SET NULL;
ALTER TABLE crm_opportunita ADD COLUMN IF NOT EXISTS aggiornata_il TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL;
ALTER TABLE riunioni_importate ADD COLUMN IF NOT EXISTS analizzata BOOLEAN NOT NULL DEFAULT FALSE;

-- analisi di ogni call con un cliente: esigenze dette e non dette, angoli per l'upselling, prossimo passo
CREATE TABLE IF NOT EXISTS crm_analisi_call (
  id SERIAL PRIMARY KEY,
  riunione_id INTEGER UNIQUE REFERENCES riunioni_importate(id) ON DELETE CASCADE,
  contatto_id INTEGER REFERENCES crm_contatti(id) ON DELETE SET NULL,
  opportunita_id INTEGER REFERENCES crm_opportunita(id) ON DELETE SET NULL,
  categoria TEXT NOT NULL DEFAULT '',
  esigenze_dette JSONB NOT NULL DEFAULT '[]'::jsonb,
  esigenze_non_dette JSONB NOT NULL DEFAULT '[]'::jsonb,
  upselling JSONB NOT NULL DEFAULT '[]'::jsonb,
  prossimo_passo TEXT NOT NULL DEFAULT '',
  idea TEXT NOT NULL DEFAULT '',
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS crm_analisi_call_categoria ON crm_analisi_call (categoria, creata_il DESC);

-- il quadro di settore: cosa chiedono hotel, musei, sponsor... aggiornato dalle call
CREATE TABLE IF NOT EXISTS quadri_settore (
  categoria TEXT PRIMARY KEY,
  testo TEXT NOT NULL DEFAULT '',
  n_call INTEGER NOT NULL DEFAULT 0,
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
