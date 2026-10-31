-- Memoria condivisa delle buone pratiche: a progetto chiuso il lavoro svolto diventa una scheda consultabile da tutti gli agenti.
CREATE TABLE IF NOT EXISTS best_practice (
  id SERIAL PRIMARY KEY,
  progetto_id INTEGER,
  progetto_nome TEXT NOT NULL DEFAULT '',
  titolo TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'generale',
  contesto TEXT NOT NULL DEFAULT '',
  cosa_funziona TEXT NOT NULL DEFAULT '',
  da_evitare TEXT NOT NULL DEFAULT '',
  checklist TEXT NOT NULL DEFAULT '',
  parole TEXT NOT NULL DEFAULT '',
  stato TEXT NOT NULL DEFAULT 'attiva' CHECK (stato IN ('attiva', 'scartata')),
  origine TEXT NOT NULL DEFAULT 'automatica' CHECK (origine IN ('automatica', 'manuale')),
  usata_n INTEGER NOT NULL DEFAULT 0,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  aggiornato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS best_practice_progetto ON best_practice (progetto_id);
