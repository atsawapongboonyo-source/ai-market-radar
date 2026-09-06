from flask import Flask, render_template, jsonify
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR))

def load_json(name):
    with (BASE_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/")
def home():
    return render_template("index.html", events=load_json("events.json"), watchlist=load_json("watchlist.json"))

@app.route("/api/events")
def api_events():
    return jsonify(load_json("events.json"))

@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(load_json("watchlist.json"))

@app.route("/health")
def health():
    return jsonify({"status":"ok","service":"AI Market Radar","version":"2.0"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
