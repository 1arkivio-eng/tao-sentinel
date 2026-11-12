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

## Lanci di nuove subnet
`lanci.py` (workflow `lanci-subnet`, ora solo avvio a mano: il servizio automatico gira nel repo pubblico `tao-lanci`, minuti gratuiti) legge direttamente la blockchain Bittensor, la stessa fonte di Taostats e Taosis,
tramite i nodi RPC pubblici. Avvisa su ntfy:
- **Nuova subnet registrata** (priorità normale): scambi ancora chiusi, con la data più vicina in cui possono aprire.
- **LANCIO, scambi aperti** (priorità urgente): il proprietario ha fatto lo *start call* e il flag on-chain `SubtokenEnabled` è diventato vero.
  Prima di quel momento comprare o vendere il token è bloccato dalla catena. Il messaggio riporta prezzo e pool, con i link a Taostats e Taosis.

Non usa Taosis come fonte perché blocca i server di GitHub (403 Cloudflare). Avvio a mano con "prova" = notifica di test.
Stato in cache di Actions (`stato_lanci.json`); il primo giro memorizza la situazione senza avvisare.

## Sentinella stop (attiva)
`stop.py` ogni ~5 minuti legge i prezzi dalla chain Bittensor (SubnetTAO / SubnetAlphaIn, nodo pubblico Opentensor)
e avvisa su ntfy quando una posizione di `posizioni.json` è entro il 2% dallo stop, lo supera o raggiunge l'obiettivo.
Non usa Taosis (blocca GitHub). Il job non fallisce mai: niente email di errore.
