#!/usr/bin/env python3
"""Rilevatore lanci subnet: SOLO LETTURA, nessuna transazione, nessuna chiave.

Legge direttamente la blockchain Bittensor (la stessa fonte da cui leggono Taostats e Taosis)
e manda una notifica ntfy quando:
  1. una nuova subnet viene registrata (preavviso: scambi ancora chiusi);
  2. partono gli scambi del suo token, cioè il proprietario fa "start call"
     e il flag on-chain SubtokenEnabled diventa vero (prima di allora comprare/vendere è bloccato).

Niente Taosis/Taostats come fonte: Taosis blocca i server GitHub (403 Cloudflare) e Taostats vuole una chiave.
Solo libreria standard Python. Canale ntfy: variabile NTFY_TOPIC (segreto GitHub).
"""
import json, os, time, urllib.request, datetime as dt
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATE = DIR / "stato_lanci.json"
NODI = [  # nodi RPC pubblici, provati in ordine
    "https://entrypoint-finney.opentensor.ai",
    "https://lite.chain.opentensor.ai",
    "https://bittensor-finney.api.onfinality.io/public",
]
SECONDI_BLOCCO = 12

# chiavi di storage = twox128("SubtensorModule") + twox128(nome)
P = "0x658faa385070e074c85bf6b568cf0555"
ABILITATO = P + "e9348e9224ea06c9c2da12ce69e619c5"   # SubtokenEnabled: netuid -> bool (scambi aperti)
REGISTRATA = P + "271d29b9b717ce3d8c571f1cbc180fa2"  # NetworkRegisteredAt: netuid -> blocco
POOL_TAO = P + "7a57dce016211512d1700561066b85a3"    # SubnetTAO: netuid -> rao
POOL_ALPHA = P + "2ce12f7007574647d692ac7edf8b7a53"  # SubnetAlphaIn: netuid -> rao
IDENTITA = P + "c7cb9786b286b680ca204a6c0920ee52"    # SubnetIdentitiesV3: netuid -> struct (nome per primo)
SIMBOLO = P + "1d2b1576e38a35d8562cbcdfc8db1277"     # TokenSymbol: netuid -> bytes
RITARDO = P + "737faaeb5de580648bcd7d397e2b8c3d"     # StartCallDelay: blocchi dopo la registrazione


def log(msg):
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}", flush=True)


def rpc(nodo, metodo, params):
    req = urllib.request.Request(nodo, json.dumps({"id": 1, "jsonrpc": "2.0", "method": metodo, "params": params}).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "tao-sentinel/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(f"{metodo}: {d['error']}")
    return d["result"]


def mappa(nodo, prefisso, blocco):
    """Tutte le voci di una mappa netuid -> valore (bytes). Il netuid sono gli ultimi 2 byte della chiave."""
    chiavi, ultima = [], None
    while True:
        pag = rpc(nodo, "state_getKeysPaged", [prefisso, 1000, ultima, blocco])
        chiavi += pag
        if len(pag) < 1000:
            break
        ultima = pag[-1]
    out = {}
    for i in range(0, len(chiavi), 200):
        for blocco_dati in rpc(nodo, "state_queryStorageAt", [chiavi[i:i + 200], blocco]):
            for k, v in blocco_dati["changes"]:
                if v is not None:
                    out[int.from_bytes(bytes.fromhex(k[-4:]), "little")] = bytes.fromhex(v[2:])
    return out


def intero(b):
    return int.from_bytes(b, "little") if b else 0


def testo_scale(b):
    """Primo Vec<u8> SCALE di un valore (lunghezza compatta + byte)."""
    if not b:
        return ""
    modo = b[0] & 3
    if modo == 0:
        n, s = b[0] >> 2, 1
    elif modo == 1:
        n, s = int.from_bytes(b[:2], "little") >> 2, 2
    elif modo == 2:
        n, s = int.from_bytes(b[:4], "little") >> 2, 4
    else:
        return ""
    return b[s:s + n].decode("utf-8", "replace").strip()


def push(topic, msg, titolo, prio="high", netuid=None):
    h = {"Title": titolo, "Priority": prio, "Tags": "rocket" if prio == "urgent" else "bell"}
    if netuid is not None:
        h["Click"] = f"https://taostats.io/subnets/{netuid}"
        h["Actions"] = f"view, Taostats, https://taostats.io/subnets/{netuid}; view, Taosis, https://taosis.com"
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", msg.encode(), h), timeout=30).read()
        log(f"push ok: {titolo} | {msg}")
    except Exception as e:
        log(f"push ERRORE {e!r}: {titolo} | {msg}")


def leggi_catena():
    ultimo = None
    for nodo in NODI:
        try:
            testa = rpc(nodo, "chain_getFinalizedHead", [])
            numero = int(rpc(nodo, "chain_getHeader", [testa])["number"], 16)
            d = {"nodo": nodo, "blocco": numero,
                 "abilitato": mappa(nodo, ABILITATO, testa), "registrata": mappa(nodo, REGISTRATA, testa)}
            if not d["registrata"]:
                raise RuntimeError("mappa NetworkRegisteredAt vuota: struttura della catena cambiata?")
            d["ritardo"] = intero(bytes.fromhex((rpc(nodo, "state_getStorage", [RITARDO, testa]) or "0x")[2:]))
            d["_testa"] = testa
            return d
        except Exception as e:
            ultimo = f"{nodo.split('/')[2]}: {e!r}"[:200]
            log(f"nodo non disponibile {ultimo}")
    raise RuntimeError(ultimo)


def dettagli(d, n):
    nodo, testa = d["nodo"], d["_testa"]
    def uno(prefisso):
        try:
            return mappa(nodo, prefisso, testa).get(n, b"")
        except Exception:
            return b""
    # nota: legge l'intera mappa (~130 voci); succede solo quando c'è un avviso
    nome = testo_scale(uno(IDENTITA)) or "(senza nome)"
    simbolo = testo_scale(uno(SIMBOLO))
    tao, alpha = intero(uno(POOL_TAO)), intero(uno(POOL_ALPHA))
    prezzo = tao / alpha if alpha else 0
    return nome, simbolo, prezzo, tao / 1e9


def quando(blocchi):
    if blocchi <= 0:
        return "già possibile"
    t = dt.datetime.now() + dt.timedelta(seconds=blocchi * SECONDI_BLOCCO)
    return f"dal {t:%d/%m %H:%M} circa"


def controlla(topic, st, d):
    """Un controllo: confronta la catena con lo stato e manda gli avvisi. Ritorna i netuid in finestra di lancio."""
    aperte = {str(n) for n, v in d["abilitato"].items() if v[:1] == b"\x01"}
    reg = {str(n): intero(v) for n, v in d["registrata"].items()}
    primo_giro = "reg" not in st
    if not primo_giro:
        vecchie_reg, vecchie_aperte = st["reg"], set(st["aperte"])
        for k, blocco_reg in sorted(reg.items(), key=lambda x: int(x[0])):
            n = int(k)
            if n == 0:
                continue
            nuova = vecchie_reg.get(k) != blocco_reg  # netuid nuovo o riusato (ri-registrato)
            if nuova:
                nome, simbolo, _, _ = dettagli(d, n)
                stato = "scambi GIÀ aperti" if k in aperte else f"scambi chiusi; apertura possibile {quando(blocco_reg + d['ritardo'] - d['blocco'])}, quando il proprietario fa lo start"
                push(topic, f"Nuova subnet registrata su SN{n}: {nome} {simbolo}. {stato}. Ti avviso quando partono gli scambi.",
                     f"Nuova subnet SN{n}", "default", n)
            if k in aperte and (nuova or k not in vecchie_aperte):
                nome, simbolo, prezzo, pool = dettagli(d, n)
                giorni = (d["blocco"] - blocco_reg) * SECONDI_BLOCCO / 86400
                push(topic, f"SN{n} {nome} {simbolo}: token scambiabile ora. Prezzo {prezzo:.5f} TAO, pool {pool:,.0f} TAO, "
                            f"registrata {giorni:.1f} giorni fa. Valuta l'entrata entro 6 ore (scrivi a Claude).",
                     f"LANCIO SN{n}: scambi aperti", "urgent", n)
            elif k not in aperte and d["blocco"] >= blocco_reg + d["ritardo"] and k not in st.get("pronte", []):
                nome, simbolo, _, _ = dettagli(d, n)
                push(topic, f"SN{n} {nome} {simbolo}: da ora il proprietario può aprire gli scambi in qualsiasi momento."
                            + (" Controllo rapido attivo." if float(os.environ.get("DURATA_MAX", "540")) > 0 else ""),
                     f"SN{n} pronta al lancio", "default", n)
    else:
        log("primo giro: memorizzo lo stato attuale, nessun avviso")
    attesa = [k for k in reg if k not in aperte and k != "0"]
    # finestra di lancio: start già possibile o possibile entro ~15 minuti
    finestra = [k for k in attesa if d["blocco"] >= reg[k] + d["ritardo"] - 75]
    st["reg"], st["aperte"] = reg, sorted(aperte, key=int)
    st["pronte"] = [k for k in attesa if d["blocco"] >= reg[k] + d["ritardo"]]
    log(f"blocco {d['blocco']}: {len(reg) - 1} subnet, in attesa {['SN' + k for k in attesa]}, in finestra {['SN' + k for k in finestra]}")
    return reg, aperte, attesa, finestra


def main():
    topic = os.environ["NTFY_TOPIC"].strip()
    durata = float(os.environ.get("DURATA_MAX", "540"))  # secondi di controllo rapido per giro, solo in finestra
    passo = float(os.environ.get("PASSO", "20"))
    inizio = time.time()
    try:
        st = json.loads(STATE.read_text())
    except Exception:
        st = {}
    while True:
        try:
            d = leggi_catena()
        except Exception as e:
            st["errori"] = st.get("errori", 0) + 1
            log(f"catena non leggibile ({st['errori']} di fila): {e}")
            if st["errori"] % 288 == 6:  # dopo ~30 minuti di giri falliti, poi ogni ~24 ore
                push(topic, f"Rilevatore lanci: nodi Bittensor non raggiungibili da {st['errori']} giri ({str(e)[:100]}). Controlli sospesi.", "Rilevatore lanci", "default")
            STATE.write_text(json.dumps(st)); raise SystemExit(1)
        if st.get("errori", 0) >= 6:
            push(topic, f"Rilevatore lanci: catena di nuovo leggibile dopo {st['errori']} giri falliti.", "Rilevatore lanci", "default")
        st["errori"] = 0
        reg, aperte, attesa, finestra = controlla(topic, st, d)
        STATE.write_text(json.dumps(st))
        # controllo rapido solo se una subnet può aprire a momenti: altrimenti un solo controllo e fine
        if not finestra or time.time() - inizio + passo > durata:
            break
        time.sleep(passo)

    if os.environ.get("PROVA") == "true":  # avvio a mano con "prova": simula il lancio della subnet aperta più di recente
        k = max((k for k in reg if k in aperte and k != "0"), key=lambda k: reg[k])
        nome, simbolo, prezzo, pool = dettagli(d, int(k))
        push(topic, f"PROVA (non è un lancio): ultima subnet aperta SN{k} {nome} {simbolo}, prezzo {prezzo:.5f} TAO, pool {pool:,.0f} TAO.",
             f"PROVA rilevatore lanci SN{k}", "urgent", int(k))
    oggi = dt.date.today().isoformat()
    if dt.datetime.now().hour >= 9 and st.get("vivo") != oggi:
        def cosa(k):
            b = reg[k] + d["ritardo"] - d["blocco"]
            return f"SN{k} " + ("pronta" if b <= 0 else quando(b).replace("dal ", "dal "))
        push(topic, f"Rilevatore lanci attivo: {len(reg) - 1} subnet, {len(attesa)} in attesa di aprire gli scambi"
                    + (f" ({'; '.join(cosa(k) for k in sorted(attesa, key=int))})" if attesa else "") + ".", "Rilevatore lanci ok", "low")
        st["vivo"] = oggi
    STATE.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
