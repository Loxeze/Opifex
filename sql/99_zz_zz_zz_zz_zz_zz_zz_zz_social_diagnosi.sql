-- Social: registro degli eventi di collegamento (per il resoconto scaricabile). Mai token o segreti: solo esiti e messaggi delle reti.
CREATE TABLE IF NOT EXISTS social_eventi (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL DEFAULT '',
  evento TEXT NOT NULL,
  dettaglio TEXT NOT NULL DEFAULT '',
  creato_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS social_eventi_quando ON social_eventi (creato_il DESC);
