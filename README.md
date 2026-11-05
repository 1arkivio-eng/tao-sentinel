# tao-sentinel

Sentinella del wallet TAO: **solo lettura**, nessuna transazione, nessuna chiave.
Ogni ~5 minuti (GitHub Actions) legge i prezzi pubblici Taosis e manda una notifica ntfy solo quando serve un intervento:
stop vicino/superato, obiettivo raggiunto, stop mobile delle piante, nuovo lancio di subnet.

- Livelli: `posizioni.json` (stop, obiettivo; `pianta` = stop mobile al 35% sotto il massimo).
- Canale ntfy: segreto del repository `NTFY_TOPIC` (mai nel codice).
- Stato (massimi, avvisi già inviati): cache di Actions, non versionato.

## Archivio flussi
Ogni 15 minuti `raccogli.py` salva una fotografia di tutte le subnet (dati pubblici Taosis: prezzo, pool, flussi,
compratori/venditori, vendite dei proprietari, prune rank) nel ramo `dati`, in `dati/AAAA-MM-GG/HHMM.csv.gz`.
Serve a testare regole sui flussi, che Taosis fornisce solo in tempo reale.
