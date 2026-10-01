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

Focus Queue
- On-demand endpoint: /api/focus-queue
- Purpose: rank what to inspect first, not what to buy.
- Slot 1 always shows the current Multi-Radar leader, even when that leader is Cooling.
- Slot 2 prefers a confirmed EARLY_ROTATION / ACCELERATING theme when available.
- Slot 3 uses the next highest-ranked non-duplicate theme.
- Each selected theme is paired with its Stock Leader Bridge result.
- Focus Queue loads only selected themes and is cached for 5 minutes; it does not preload every theme on page open.
- Tapping a Focus Queue row opens the selected theme's Top 3 stock leaders.
- It does not modify or bypass the existing AI Top Pick, Premarket Gate, Opening Confirmation, Final Decision or Position Engine.

Focus Queue historical validation
- Added research-only replay using the same historical Theme Rotation + Stock Leader formulas.
- Production endpoint: /api/focus-queue-research, intentionally capped at 220 sessions (~1 year) so Render is not asked to run heavy 2-3 year stress tests.
- 1Y non-overlapping 5-session sample: Focus #1 Theme vs QQQ avg +0.72%, median +1.43%, positive 64.3% (n=42). Focus #1 stock vs QQQ avg +2.95%, median +1.65%. Qualified Focus #1 stock (Confirm >=4/5) avg +3.93%, median +2.30% (n=38).
- 2Y stress: Focus #1 Theme avg +0.33%, median +1.02%, positive 61.6% (n=86). Qualified Focus #1 stock avg +2.49%, median +2.05% (n=78).
- ~3Y stress using a 5Y data pull / last 660 sessions: Focus #1 Theme avg +0.47%, median +0.67%, positive 58.5% (n=130). Qualified Focus #1 stock avg +3.29%, median +2.30%, positive 61.5% (n=122).
- Secondary #2/#3 reorder tests did not show a strong enough robust difference to justify changing live selection/order. Existing Focus Queue logic is therefore preserved.
- Rotation Watch vs Next Ranked occasionally differs materially at the stock level, but paired differing samples remain small and volatile; no live rule change is made from that diagnostic.
- Current-universe / survivorship bias remains an important limitation. Results validate attention ranking only, not a trading strategy with entries, exits, slippage or risk controls.

Pre-merge hardening
- Fresh local benchmark: Multi-Radar ~3.19s, Focus Queue ~3.74s, cached Focus Queue ~0.001s, Theme Stock Leader ~0.37s, /scanner ~0.027s.
- Focus Queue now degrades per-theme: if one Stock Leader data request fails, the remaining queue still renders and only that theme reports Stock Leader data unavailable.
- Focus Validation is on-demand and production-capped to 220 sessions; longer 2-3 year stress tests remain offline research only.
- Focus #1 is presented as PRIMARY FOCUS; #2 and #3 are SECONDARY WATCH. This is attention priority, not a buy recommendation.

Focus Queue priority policy after long-window validation
- Priority #1 remains CURRENT_LEADER.
- Priority #2 is now NEXT_RANKED by Multi-Radar rank; Rotation state alone no longer jumps ahead of rank #2.
- Priority #3 is ROTATION_MONITOR when a distinct EARLY_ROTATION / ACCELERATING theme exists; otherwise it is RANK_BACKUP.
- A rank #2 theme that is itself in a rotation state remains Priority #2 and is annotated as such; it is not duplicated in Priority #3.
- In the 5-year stress sample using non-overlapping 5-session windows, CURRENT_LEADER remained the strongest attention bucket: theme excess versus QQQ averaged +0.28%, selected stock excess averaged +1.96%, and qualified stock leaders averaged +2.34%.
- Rotation states remain useful as monitoring context, but the longer sample did not justify automatically promoting Rotation Watch above the next-ranked theme.
- These are research diagnostics with current-universe / survivorship limitations, not trading-performance guarantees.

Release-candidate runtime audit
- Local cold latency: /scanner ~0.03s, Multi-Radar ~3.2s, Theme Stock Leader ~0.38s, Focus Queue ~3.73s.
- Cached live endpoints returned effectively immediately in the local test.
- Research-only cold latency at 220 sessions: Multi-Radar Research ~13.9s and Focus Queue Research ~17.9s; cached calls returned effectively immediately.
- Research endpoints remain manual/on-demand and are not part of page boot.
- render.yaml keeps the existing service plan and entrypoint but adds gunicorn --timeout 60 as safety margin for research requests; live decision logic is unchanged.
