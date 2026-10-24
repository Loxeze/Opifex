-- Un dipartimento puo' servire piu' aziende (es. Marketing per Castello di Montarrenti e Renovatio)
CREATE TABLE IF NOT EXISTS divisioni_aziende (
  divisione_id INTEGER NOT NULL REFERENCES divisioni(id) ON DELETE CASCADE,
  azienda_id INTEGER NOT NULL REFERENCES aziende(id) ON DELETE CASCADE,
  PRIMARY KEY (divisione_id, azienda_id)
);
INSERT INTO divisioni_aziende (divisione_id, azienda_id)
SELECT id, azienda_id FROM divisioni WHERE azienda_id IS NOT NULL ON CONFLICT DO NOTHING;
