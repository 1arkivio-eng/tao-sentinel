#!/usr/bin/env python3
"""Sentinella stop: prezzi letti DIRETTAMENTE dalla chain Bittensor (non Taosis, che blocca GitHub).
Solo lettura, nessuna chiave. Prezzo = SubnetTAO / SubnetAlphaIn (TAO per alpha), come Taostats.
Per ogni posizione in posizioni.json avvisa su ntfy: stop vicino (2%), stop superato, obiettivo raggiunto.
Lo stesso avviso non si ripete prima di 6 ore. Un messaggio di funzionamento al giorno dopo le 9.
"""
import json, os, subprocess, time, datetime as dt
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATO = DIR / "stato_stop.json"
NODI = ("https://entrypoint-finney.opentensor.ai", "https://archive.chain.opentensor.ai")
P = "0x658faa385070e074c85bf6b568cf0555"
TAO, ALPHA = P + "7a57dce016211512d1700561066b85a3", P + "2ce12f7007574647d692ac7edf8b7a53"
RIPETI, VICINO = 6 * 3600, 0.02


def le(h):
    return None if h is None else int.from_bytes(bytes.fromhex(h[2:]), "little")


def prezzi(netuids):
    chiavi = [pref + n.to_bytes(2, "little").hex() for n in netuids for pref in (TAO, ALPHA)]
    corpo = json.dumps({"id": 1, "jsonrpc": "2.0", "method": "state_queryStorageAt", "params": [chiavi]})
    errore = None
    for url in NODI:
        try:
            r = subprocess.run(["curl", "-sS", "-m", "60", "--retry", "2", "-H", "Content-Type: application/json",
                                "-d", corpo, url], capture_output=True, text=True)
            val = dict(json.loads(r.stdout)["result"][0]["changes"])
            out = {}
            for n in netuids:
                s = n.to_bytes(2, "little").hex()
                t, a = le(val.get(TAO + s)), le(val.get(ALPHA + s))
                if t and a:
                    out[n] = t / a
            return out
        except Exception as e:
            errore = f"{url}: {e!r}"[:150]
    raise RuntimeError(errore)


def push(topic, msg, titolo="AZIONE wallet TAO", prio="high"):
    if topic:
        subprocess.run(["curl", "-sS", "-m", "20", "-H", f"Title: {titolo}", "-H", f"Priority: {prio}", "-d", msg,
                        f"https://ntfy.sh/{topic}"], capture_output=True)
    print("PUSH:", msg)


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    pos = json.loads((DIR / "posizioni.json").read_text())["posizioni"]
    try:
        st = json.loads(STATO.read_text())
    except Exception:
        st = {}
    inviati = st.setdefault("inviati", {})
    try:
        px = prezzi([int(k) for k in pos])
    except Exception as e:
        st["errori"] = st.get("errori", 0) + 1
        print("CHAIN NON RAGGIUNGIBILE:", e)
        if st["errori"] % 144 == 6:
            push(topic, f"Sentinella stop: chain non raggiungibile da ~30 min. Controlla gli avvisi dell'app.", "Sentinella", "default")
        STATO.write_text(json.dumps(st)); return
    st["errori"] = 0
    ora = time.time()

    def avvisa(chiave, testo):
        if ora - inviati.get(chiave, 0) > RIPETI:
            push(topic, testo); inviati[chiave] = ora

    for k, p in pos.items():
        prezzo = px.get(int(k))
        if prezzo is None:
            continue
        stop, nome = float(p["stop"]), p["nome"]
        if prezzo <= stop:
            avvisa(f"s{k}", f"{nome}: {prezzo:.5f} SOTTO lo stop {stop} -> VENDI")
        elif prezzo <= stop * (1 + VICINO):
            avvisa(f"v{k}", f"{nome}: {prezzo:.5f} a meno del 2% dallo stop {stop} -> preparati a vendere")
        if p.get("obiettivo") and prezzo >= float(p["obiettivo"]):
            avvisa(f"o{k}", f"{nome}: {prezzo:.5f} OBIETTIVO {p['obiettivo']} -> {p.get('azione', 'vendi metà')}")
    oggi = dt.datetime.now().strftime("%Y-%m-%d")
    if dt.datetime.now().hour >= 9 and st.get("vivo") != oggi:
        righe = ", ".join(f"{pos[str(n)]['nome'].split()[-1]} {v:.5f}" for n, v in px.items())
        push(topic, f"Sentinella stop attiva su {len(px)} posizioni: {righe}"[:400], "Sentinella ok", "low")
        st["vivo"] = oggi
    print("prezzi:", {n: round(v, 6) for n, v in px.items()})
    STATO.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
