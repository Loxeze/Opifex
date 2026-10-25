-- Brief brevi dei manager di dipartimento, allegati a ciascun briefing
CREATE TABLE IF NOT EXISTS briefing_manager (
  id SERIAL PRIMARY KEY,
  briefing_id INTEGER NOT NULL REFERENCES briefing(id) ON DELETE CASCADE,
  agente_id INTEGER REFERENCES agenti(id) ON DELETE SET NULL,
  contenuto TEXT NOT NULL,
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS briefing_manager_briefing ON briefing_manager(briefing_id);
