from flask import Flask, jsonify, send_from_directory
import json
from pathlib import Path

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent


def load_json(filename):
    path = BASE_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/events")
def api_events():
    return jsonify(load_json("events.json"))


@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(load_json("watchlist.json"))


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "AI Market Radar"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
