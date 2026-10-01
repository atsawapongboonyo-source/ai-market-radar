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

Rotation confirmation filter
- EARLY ROTATION now requires group-level confirmation, not score/rank recovery alone.
- Confirmation checks: breadth >= 50%, EMA20 participation >= 50%, member median 20D relative strength >= 0, proxy 5D relative strength >= 0, median volume ratio >= 0.90.
- Breadth + EMA20 + member relative strength are mandatory core checks.
- At least 4 of 5 checks must pass for confirmed EARLY ROTATION.
- Unconfirmed rebound is classified as RECOVERING and shown separately from the main Transition Watch.

Rotation structure
- Tracks leader handoffs across the recent 15-session history.
- Exposes current leader streak, total handoffs, and the most recent handoff.
- Keeps current leadership separate from confirmed Early Rotation and unconfirmed Recovery Watch.
