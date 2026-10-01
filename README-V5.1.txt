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

Research / historical validation
- Research endpoint is isolated from the live decision engine: /api/multi-radar-research
- Default research window: up to 220 sessions using 1-year Yahoo history.
- Repeated daily states are de-duplicated; state-entry research uses a 5-session cooldown.
- Immediate EARLY_ROTATION / ACCELERATING and raw leader handoffs did not show a robust standalone forward-return edge versus QQQ in the longer sample.
- The cross-sectional ranking test is more aligned with the engine's purpose.
- In the 220-session non-overlapping 5-session test, current rank #1 averaged +0.89% versus the last-ranked theme, Top 2 averaged +0.71% versus Bottom 2, and the current leader finished in the future top half 69.0% of the tested windows.
- These figures are research diagnostics only and may contain current-universe / survivorship bias. They are not used as a Buy Signal.

Theme → Stock Leader Bridge
- New on-demand endpoint: /api/theme-stock-leaders?theme=<key>
- Tapping a Multi-Radar theme loads Top 3 members for that theme only; the page does not preload every theme.
- Stock Leader Score is cross-sectional within the selected theme using relative 1D/5D/20D momentum, EMA20 and volume.
- Group Leader eligibility requires at least 4 of 5 confirmation checks: beats theme proxy 1D, 5D and 20D, above EMA20, and volume ratio >= 1.0.
- A higher raw momentum score with fewer than 4 confirmations cannot displace a qualified Group Leader.
- This bridge does not modify or bypass the existing AI Top Pick, Premarket Gate, Opening Confirmation, Final Decision or Position Engine.
