-- 2.23.0: domande degli agenti legate al progetto, cartelle del NAS per agente, avvisi di nuovi file indicizzati.
ALTER TABLE richieste_informazioni ADD COLUMN IF NOT EXISTS progetto_id INTEGER REFERENCES progetti(id) ON DELETE SET NULL;
UPDATE richieste_informazioni r SET progetto_id = COALESCE(
  (SELECT t.progetto_id FROM task t WHERE t.assegnato_agente_id = r.agente_id AND t.progetto_id IS NOT NULL AND t.stato <> 'completata' ORDER BY t.aggiornata_il DESC LIMIT 1),
  (SELECT CASE WHEN count(*) = 1 THEN min(pa.progetto_id) END FROM progetti_agenti pa JOIN progetti p ON p.id = pa.progetto_id WHERE pa.agente_id = r.agente_id AND NOT p.archiviato))
WHERE r.stato = 'aperta' AND r.progetto_id IS NULL;

CREATE TABLE IF NOT EXISTS archivio_cartelle_agenti (
  agente_id INTEGER NOT NULL REFERENCES agenti(id) ON DELETE CASCADE,
  cartella_id INTEGER NOT NULL REFERENCES archivio_cartelle(id) ON DELETE CASCADE,
  PRIMARY KEY (agente_id, cartella_id)
);

CREATE TABLE IF NOT EXISTS archivio_novita (
  id SERIAL PRIMARY KEY,
  cartella_id INTEGER NOT NULL REFERENCES archivio_cartelle(id) ON DELETE CASCADE,
  nuovi INTEGER NOT NULL,
  dal TIMESTAMPTZ NOT NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS archivio_novita_viste (
  utente_id INTEGER NOT NULL REFERENCES utenti(id) ON DELETE CASCADE,
  novita_id INTEGER NOT NULL REFERENCES archivio_novita(id) ON DELETE CASCADE,
  PRIMARY KEY (utente_id, novita_id)
);
