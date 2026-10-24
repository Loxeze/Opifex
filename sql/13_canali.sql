-- Canali per parlare con il referente (Aurora): Telegram
CREATE TABLE IF NOT EXISTS canale_telegram (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  token_cifrato TEXT,
  bot_username TEXT,
  chat_id BIGINT,
  offset_aggiornamenti BIGINT NOT NULL DEFAULT 0,
  codice_hash TEXT,
  codice_scade TIMESTAMPTZ,
  codice_tentativi INTEGER NOT NULL DEFAULT 0,
  fascia_dati TEXT NOT NULL DEFAULT 'pubblico' CHECK (fascia_dati IN ('pubblico', 'interno', 'riservato')),
  ultimo_errore TEXT,
  collegato_il TIMESTAMPTZ
);
INSERT INTO canale_telegram (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
