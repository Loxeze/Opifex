#!/bin/bash
# Costruisce la release X.Y.Z: pacchetto per l'aggiornamento automatico + impronta + installatore completo.
# uso: bash rilascia.sh 0.9.1
set -euo pipefail
VER="${1:?versione, es. 0.9.1}"
[[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "versione non valida"; exit 1; }
SP="$(cd "$(dirname "$0")" && pwd)"
OUT="$SP/rilascio-$VER"; rm -rf "$OUT"; mkdir -p "$OUT"
cd "$SP/pacchetto"
echo "$VER" > VERSIONE
find . -name __pycache__ -type d -prune -exec rm -rf {} +
# 1) pacchetto per gli aggiornamenti (solo cio' che lo script di root accetta)
tar czf "$OUT/opifex-$VER.tgz" app sql requirements.txt VERSIONE crea_titolare.py crea_briefing.py .env.example
( cd "$OUT" && sha256sum "opifex-$VER.tgz" | cut -d' ' -f1 > "opifex-$VER.tgz.sha256" )
# 2) installatore completo (prima installazione): payload = pacchetto + cartella installer
tar czf "$OUT/payload.tgz" app sql installer requirements.txt VERSIONE crea_titolare.py crea_briefing.py .env.example
cp "$SP/testa.sh" "$OUT/installa-opifex.sh"
base64 -w0 "$OUT/payload.tgz" >> "$OUT/installa-opifex.sh"
rm "$OUT/payload.tgz"
echo "Creati in $OUT:"; ls -la "$OUT"
