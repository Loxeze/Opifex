-- 1.76.0: sfondo con opere d'arte da Wikimedia Commons (una ogni 10 minuti), conservate qui per non richiederle di continuo
CREATE TABLE IF NOT EXISTS sfondi_arte (
  slot BIGINT PRIMARY KEY,
  titolo TEXT NOT NULL,
  autore TEXT NOT NULL DEFAULT '',
  licenza TEXT NOT NULL DEFAULT '',
  pagina TEXT NOT NULL DEFAULT '',
  mime TEXT NOT NULL,
  immagine BYTEA NOT NULL,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
