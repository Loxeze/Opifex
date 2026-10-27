-- 1.40.0: avatar degli agenti (opere antiche di pubblico dominio da Wikimedia Commons, scelte da Lorenzo, con attribuzione)
CREATE TABLE IF NOT EXISTS agenti_avatar (
  agente_id INTEGER PRIMARY KEY REFERENCES agenti(id) ON DELETE CASCADE,
  immagine BYTEA NOT NULL,
  mime TEXT NOT NULL,
  byte INTEGER NOT NULL,
  opera TEXT NOT NULL DEFAULT '',
  autore TEXT NOT NULL DEFAULT '',
  licenza TEXT NOT NULL DEFAULT '',
  file_commons TEXT NOT NULL,
  fonte_url TEXT NOT NULL,
  scelto_da_utente_id INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
  scelto_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
