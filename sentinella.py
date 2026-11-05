#!/usr/bin/env python3
"""Sentinella wallet TAO per Mac: SOLO LETTURA, nessuna transazione, nessuna chiave.
Ogni 5 minuti (launchd) legge i prezzi pubblici Taosis e manda una notifica ntfy
SOLO quando serve un tuo intervento: stop vicino/superato, obiettivo, stop mobile piante, nuovo lancio.
Posizioni e livelli: posizioni.json (accanto a questo file). Canale ntfy: variabile NTFY_TOPIC (segreto GitHub) o file ntfy_topic.txt (non versionato).
"""
import json, os, subprocess, time, datetime as dt
from pathlib import Path

DIR = Path(__file__).resolve().parent
STATE = DIR / "stato.json"
LOG = DIR / "sentinella.log"
URL = "https://taosis.com/api/backend/markets/subnets?spark=false"
RIPETI = 6 * 3600   # stesso avviso al massimo ogni 6 ore
VICINO = 0.02       # avviso entro il 2% dallo stop
TRAIL = 0.35        # piante: stop mobile = massimo x (1 - 35%)


def log(msg):
    with LOG.open("a") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}\n")


def curl(args):
    return subprocess.run(["curl", "-sS", "-m", "30"] + args, capture_output=True, text=True)


def push(topic, msg, titolo="AZIONE wallet TAO", prio="high"):
    r = curl(["-H", f"Title: {titolo}", "-H", f"Priority: {prio}", "-d", msg, f"https://ntfy.sh/{topic}"])
    log(f"push {'ok' if r.returncode == 0 else 'ERRORE ' + r.stderr.strip()}: {msg}")


def main():
    topic = os.environ.get("NTFY_TOPIC") or (DIR / "ntfy_topic.txt").read_text().strip()
    pos = json.loads((DIR / "posizioni.json").read_text())
    try:
        st = json.loads(STATE.read_text())
    except Exception:
        st = {}
    st.setdefault("inviati", {}); st.setdefault("massimi", {})
    r = curl(["-A", "tao-sentinel/1.0", URL])
    try:
        d = json.loads(r.stdout)
        d = d.get("data", d) if isinstance(d, dict) else d
        m = {int(x["netuid"]): x for x in d}
    except Exception:
        st["errori"] = st.get("errori", 0) + 1
        log(f"dati non disponibili ({st['errori']} di fila)")
        if st["errori"] == 6:  # ~30 minuti senza dati
            push(topic, "Sentinella: Taosis non risponde da ~30 minuti, controlli sospesi finché non torna.", "Sentinella", "default")
        STATE.write_text(json.dumps(st)); return
    st["errori"] = 0
    ora = time.time()
    avvisi = []

    def avvisa(chiave, testo):
        if ora - st["inviati"].get(chiave, 0) > RIPETI:
            avvisi.append(testo); st["inviati"][chiave] = ora

    for k, p in pos["posizioni"].items():
        n = int(k); x = m.get(n)
        if not x or not x.get("price_tao"):
            continue
        prezzo = float(x["price_tao"]); stop = float(p["stop"]); nome = p["nome"]
        if p.get("pianta"):
            mx = max(float(st["massimi"].get(k, p.get("massimo", 0))), prezzo)
            st["massimi"][k] = mx
            stop = max(stop, mx * (1 - TRAIL))
        if prezzo <= stop:
            avvisa(f"s{k}", f"{nome}: {prezzo:.6f} SOTTO lo stop {stop:.6f} -> VENDI tutto")
        elif prezzo <= stop * (1 + VICINO):
            avvisa(f"v{k}", f"{nome}: {prezzo:.6f} a meno del 2% dallo stop {stop:.6f} -> preparati a vendere")
        if p.get("obiettivo") and prezzo >= float(p["obiettivo"]):
            avvisa(f"o{k}", f"{nome}: {prezzo:.6f} OBIETTIVO {p['obiettivo']} raggiunto -> {p.get('azione_obiettivo', 'vendi metà')}")

    # lanci: subnet senza scambi (o appena ri-registrate) che iniziano a scambiare
    attesa = set(st.get("attesa", []))
    reg = st.get("registrazioni", {})
    for n, x in m.items():
        if n == 0:
            continue
        vol = float(x.get("volume_24h_tao") or 0)
        rb = str(x.get("registered_block"))
        if reg.get(str(n)) not in (None, rb) and vol == 0:
            attesa.add(n)
        if vol == 0 and str(n) not in reg:
            attesa.add(n)
        reg[str(n)] = rb
        if n in attesa and vol > 0:
            avvisa(f"l{n}{rb}", f"LANCIO SN{n} {x.get('name')}: scambi partiti, prezzo {float(x['price_tao']):.5f}, pool {float(x.get('tao_reserve') or 0):.0f} TAO -> valuta entrata entro 6 ore (scrivi a Claude)")
            attesa.discard(n)
    for n, x in m.items():
        if float(x.get("volume_24h_tao") or 0) == 0 and n != 0:
            attesa.add(n)
    st["attesa"] = sorted(attesa); st["registrazioni"] = reg

    for a in avvisi:
        push(topic, a)
    oggi = dt.date.today().isoformat()
    if dt.datetime.now().hour >= 9 and st.get("vivo") != oggi:
        push(topic, f"Sentinella attiva: {len(pos['posizioni'])} posizioni sotto controllo (avviso giornaliero di funzionamento).", "Sentinella ok", "low")
        st["vivo"] = oggi
    STATE.write_text(json.dumps(st))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERRORE {e!r}")
