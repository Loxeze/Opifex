-- Accessi ai siti con login (credenziali cifrate: la chiave sta solo nel file .env del server)
CREATE TABLE IF NOT EXISTS accessi_siti (
  connessione_id INTEGER PRIMARY KEY REFERENCES connessioni(id) ON DELETE CASCADE,
  dominio TEXT NOT NULL,
  url_login TEXT NOT NULL,
  utente_cifrato TEXT NOT NULL,
  password_cifrata TEXT NOT NULL,
  fascia_contenuto TEXT NOT NULL DEFAULT 'interno' CHECK (fascia_contenuto IN ('pubblico', 'interno', 'riservato')),
  max_pagine INTEGER NOT NULL DEFAULT 12 CHECK (max_pagine BETWEEN 1 AND 40),
  aggiornato_il TIMESTAMPTZ DEFAULT NOW()
);
