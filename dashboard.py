import os
import json
import subprocess
import sys
from flask import Flask, jsonify, render_template, Response, stream_with_context

app = Flask(__name__)
BASE = os.path.dirname(__file__)


def load_env():
    env_path = os.path.join(BASE, ".env")
    cfg = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    cfg = load_env()

    history = []
    json_path = os.path.join(BASE, "price_data.json")
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            history = json.load(f)

    prices = [e["price_rs"] for e in history]
    current = prices[-1] if prices else None
    threshold = float(cfg.get("PRICE_THRESHOLD", 30000))

    return jsonify({
        "product": "OnePlus Nord 6 — 256 GB Pitch Black",
        "flipkart_url": "https://www.flipkart.com/oneplus-nord-6-pitch-black-256-gb/p/itmc49f71cdc4080?pid=MOBHMBXBMGCDHP55&marketplace=FLIPKART",
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{cfg.get('SPREADSHEET_ID', '')}",
        "threshold": threshold,
        "whatsapp_to": cfg.get("WHATSAPP_TO", "").replace("whatsapp:", ""),
        "current_price": current,
        "lowest": min(prices) if prices else None,
        "highest": max(prices) if prices else None,
        "average": round(sum(prices) / len(prices)) if prices else None,
        "total_checks": len(prices),
        "below_count": sum(1 for p in prices if p < threshold),
        "history": history,
    })


@app.route("/api/run")
def api_run():
    script = os.path.join(BASE, "check_price.py")

    def generate():
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=BASE,
        )
        for line in iter(proc.stdout.readline, b""):
            yield line.decode("utf-8", errors="replace")
        proc.stdout.close()
        proc.wait()
        yield f"\n__EXIT_CODE__{proc.returncode}__\n"

    return Response(stream_with_context(generate()), mimetype="text/plain")


if __name__ == "__main__":
    print("PriceSpy Dashboard running at http://127.0.0.1:5050")
    app.run(debug=False, port=5050)
