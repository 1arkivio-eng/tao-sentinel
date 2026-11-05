#!/usr/bin/env python3
"""Archivio flussi: salva una fotografia di tutte le subnet (dati pubblici Taosis) in dati/AAAA-MM-GG/HHMM.csv.gz.
Solo lettura. Serve a testare regole su flussi, compratori/venditori, vendite dei proprietari."""
import csv, gzip, io, json, subprocess, datetime as dt
from pathlib import Path

URL = "https://taosis.com/api/backend/markets/subnets?spark=false"
CAMPI = ["netuid", "name", "price_tao", "moving_price", "tao_reserve", "alpha_in", "alpha_out",
         "volume_24h_tao", "buy_count_24h", "sell_count_24h", "unique_buyers_24h", "unique_sellers_24h",
         "net_flow_24h", "net_flow_7d", "inflow_24h_tao", "outflow_24h_tao", "emission_pct", "prune_rank",
         "registered_block", "owner_alpha_held", "owner_net_alpha_sold_7d", "owner_net_tao_sold_7d",
         "holders", "top10_share", "change_1h", "change_24h", "change_7d"]

r = subprocess.run(["curl", "-sS", "-m", "60", "--retry", "3", "-A", "tao-sentinel/1.0", URL], capture_output=True, text=True)
d = json.loads(r.stdout)
d = d.get("data", d) if isinstance(d, dict) else d
now = dt.datetime.now(dt.timezone.utc)
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["ts_utc"] + CAMPI)
for x in d:
    w.writerow([now.strftime("%Y-%m-%dT%H:%M:%SZ")] + [x.get(k, "") for k in CAMPI])
out = Path("dati") / now.strftime("%Y-%m-%d") / (now.strftime("%H%M") + ".csv.gz")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(gzip.compress(buf.getvalue().encode(), mtime=0))
print(f"{out}: {len(d)} subnet")
