# Strategy Specification — All-Era Residual × Sweep (Sniper-Only)

## Name
`all_era_residual_sweep_sniper`

## Selection
Chosen from 421 configs by **hard multi-era gates** on 2018–2025 H4 (see `FINAL_REPORT.md`). Not optimized on a single window.

## Entry (confluence)
1. **Residual momentum** vs equal-weight majors basket (β=60)
   - Long mom sum 8 bars, short mom sum 4 bars
   - Enter long if resid_z ≥ 1.0; short if resid_z_short ≤ −1.0
2. **Liquidity sweep** — pierce swing extreme + reclaim wick (≥0.1 ATR)
   - Long swing 18 · Short swing 24 · same-bar only
3. **ADX > 12** and DI agrees
4. Skip if \|ATR z\| > 10 (effectively off for this lock)

## Risk / exits
- Sniper-only (100% capital)
- Risk 1.0% per trade
- Stop beyond sweep wick (cap 2.5 ATR)
- Take profit 4.0 ATR × vol regime (0.75 / 1.25)
- Max 3 sniper trades / pair / month
- Soft DD 15% (risk ×0.5) · Hard halt 20%

## Data
Dukascopy freeserv 4H · **2018-01-01 → 2025-12-31** · no 2026
