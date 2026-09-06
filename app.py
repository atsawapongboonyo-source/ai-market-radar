from flask import Flask, render_template, jsonify
import json
from pathlib import Path

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def load_json(name):
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/")
def home():
    events = load_json("events.json")
    watchlist = load_json("watchlist.json")
    return render_template("index.html", events=events, watchlist=watchlist)


@app.route("/api/events")
def api_events():
    return jsonify(load_json("events.json"))


@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(load_json("watchlist.json"))


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
