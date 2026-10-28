-- 1.49.0: storico delle istruzioni di ogni agente (si salva prima di ogni riscrittura o modifica) per poter tornare indietro
CREATE TABLE IF NOT EXISTS agenti_istruzioni_storico (
  id BIGSERIAL PRIMARY KEY,
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  istruzioni TEXT NOT NULL,
  motivo TEXT NOT NULL DEFAULT 'modifica',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS agenti_istruzioni_storico_agente ON agenti_istruzioni_storico (agente_id, id DESC);
