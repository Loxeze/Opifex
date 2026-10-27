-- 1.38.0: squadre di progetto (composte dal project manager, approvate da Lorenzo), KPI per agente e valutazioni date da manager e PM.
ALTER TABLE progetti ADD COLUMN IF NOT EXISTS brief TEXT NOT NULL DEFAULT '';
ALTER TABLE progetti_agenti ADD COLUMN IF NOT EXISTS ruolo_progetto TEXT;
ALTER TABLE progetti_agenti ADD COLUMN IF NOT EXISTS squadra BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE progetti_agenti ADD COLUMN IF NOT EXISTS aggregato_il TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS squadre_proposte (
  id SERIAL PRIMARY KEY,
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  proposta_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  motivazione TEXT NOT NULL DEFAULT '',
  lacune TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'proposta' CHECK (stato IN ('proposta', 'approvata', 'respinta')),
  nota TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deciso_il TIMESTAMPTZ,
  deciso_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS squadre_proposte_membri (
  proposta_id INTEGER NOT NULL REFERENCES squadre_proposte(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  ruolo_progetto TEXT NOT NULL DEFAULT '',
  motivo TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (proposta_id, agente_id)
);

CREATE TABLE IF NOT EXISTS kpi_progetto (
  id SERIAL PRIMARY KEY,
  progetto_id INTEGER NOT NULL REFERENCES progetti(id) ON DELETE CASCADE,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  obiettivo TEXT NOT NULL DEFAULT '',
  unita TEXT NOT NULL DEFAULT '',
  valore_obiettivo NUMERIC,
  valore NUMERIC,
  scadenza DATE,
  esito TEXT CHECK (esito IS NULL OR esito IN ('in_linea', 'a_rischio', 'fuori_rotta', 'raggiunto')),
  nota TEXT,
  assegnato_da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  assegnato_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  chiuso BOOLEAN NOT NULL DEFAULT FALSE,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kpi_progetto ON kpi_progetto (progetto_id, agente_id);

-- i pollici possono arrivare anche da un manager o da un project manager
ALTER TABLE valutazioni ADD COLUMN IF NOT EXISTS da_agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL;
ALTER TABLE valutazioni ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS valutazioni_unica_agente ON valutazioni (da_agente_id, oggetto, oggetto_id) WHERE oggetto_id IS NOT NULL AND da_agente_id IS NOT NULL;
