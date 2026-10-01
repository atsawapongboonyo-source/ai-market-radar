AI Market Radar V5.1 — Multi-Radar Rotation Engine

Scope
- Adds cross-theme rotation above the existing AI-only Theme Rotation.
- Keeps V4.10 execution logic, Premarket Gate, Opening Confirmation, Final Decision and Position Engine unchanged.

Top-level themes
- AI Infrastructure
- Space
- Quantum
- Nuclear / SMR
- Robotics
- Defense / Drone
- Cybersecurity

Method
- Theme ETF proxy relative momentum versus QQQ (5D and 20D)
- Member median 20D relative strength
- Member breadth versus QQQ
- Participation above EMA20
- Median volume confirmation
- 15-session rotation history

Important
- Rotation Score is a ranking signal only, not a buy signal.
- Individual stocks still require the existing Premarket + Opening + Final Decision flow.
- Universe is isolated in multi_radar_universe.json so the existing 32-stock AI watchlist is not modified.

Runtime
- Render entrypoint remains: gunicorn scanner:app
- scanner.py now loads scanner_v510.py
- API: /api/multi-radar
