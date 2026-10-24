-- Caselle di posta generiche (IMAP, es. Aruba) affidabili agli agenti: lettura e bozze, mai invio
CREATE TABLE IF NOT EXISTS caselle_posta (
  id SERIAL PRIMARY KEY,
  etichetta TEXT NOT NULL,
  email TEXT NOT NULL,
  host TEXT NOT NULL,
  porta INTEGER NOT NULL DEFAULT 993,
  utente TEXT NOT NULL,
  password_cifrata TEXT NOT NULL,
  stato TEXT NOT NULL DEFAULT 'da_provare' CHECK (stato IN ('da_provare', 'attiva', 'errore')),
  ultimo_errore TEXT,
  creata_il TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS agenti_caselle_posta (
  agente_id INTEGER PRIMARY KEY REFERENCES agenti(id) ON DELETE CASCADE,
  casella_id INTEGER NOT NULL REFERENCES caselle_posta(id) ON DELETE CASCADE
);
