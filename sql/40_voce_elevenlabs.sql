-- Voce ElevenLabs: nessuna tabella nuova, le impostazioni vivono in impostazioni_sistema (chiave cifrata, voce, garanzie dichiarate, vocale su Telegram)
INSERT INTO impostazioni_sistema (chiave, valore) VALUES ('elevenlabs_garanzie', '0'), ('elevenlabs_telegram_voce', '0'), ('elevenlabs_voce_id', '')
ON CONFLICT (chiave) DO NOTHING;
