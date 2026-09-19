# Decision Log — Fundamental Veto System Review

## Date
September 2026

## Question Investigated
Should the fundamental veto system (RPT, Pledge, FCF/PAT) shift from blocking trade entry outright to instead governing position sizing / hold duration — triggered by observing individual vetoed stocks (ALGOQUANT, SPICELOUNG) moving strongly higher after being flagged.

## Process
1. Initial pooled statistical test across 119 and 189 closed trades, using real OHLC price paths to compute MAE (max adverse excursion) and MFE (max favorable excursion) — not just entry/exit returns.
2. Pooled result appeared to support loosening the veto: vetoed trades showed a higher win rate (43.5% vs 34.6%) and higher mean return (+2.26% vs +1.27%) than clean trades.
3. Cross-checked against the report's own market-cap tier breakdown table — found the pooled result was being driven by an underpowered Mid-Cap vetoed subgroup (N=6), while Small-Cap (the tier this investigation was actually about) showed the opposite pattern.
4. Re-ran all tests stratified by market cap tier specifically. Confirmed: within Small Cap (N=13 clean, N=27 vetoed), clean fundamentals significantly outperform vetoed on peak upside (MFE: +14.83% vs +7.22%, p=0.0456 Welch's t-test, p=0.0376 Mann-Whitney U). Mean return also favored clean (+8.15% vs +1.37%) though this specific comparison did not clear statistical significance (p=0.12).
5. Confirmed stable across three independent datasets (119-trade, SBIA-only N=43, all-189) and across a chronological (July vs Aug-Sep) split.

## Decision
**No change to `conviction_scorer.py` veto logic.** FCF/PAT divergence and Promoter Pledge remain hard entry-blocking vetoes, as originally designed.

## Reasoning
The initial pooled result was a Simpson's Paradox — an aggregate trend that reverses once the data is properly split by the variable that actually matters (market cap tier). Once corrected, the data supports keeping the veto system exactly as it was: dropping or loosening it would directly reduce small-cap expectancy, since clean-fundamental small-caps are the trades generating the strongest upside in this system.

Individual anecdotes that prompted this investigation (Algoquant, Spicelounge running after being vetoed) remain real and unexplained by fundamentals — but they represent the minority case the aggregate statistics predict, not evidence the veto system is broken.

## Caveats / Limits of this Finding
- N=13 clean small-caps is still a modest sample. The point estimate (+8.15% mean return) carries real uncertainty (CI wide enough that mean-return difference alone wasn't statistically significant — MFE was the metric that cleared significance).
- Should be re-tested at larger sample size once more small-cap trades accumulate, to confirm the edge holds rather than narrows.

## Re-open this Decision If
- A future stratified re-test (larger N) shows the small-cap clean-vs-vetoed gap narrowing or reversing.
- A specific veto metric (e.g. FCF/PAT) starts showing a materially different pattern in new trade data than what was found here.

---

## Statistical Reference Appendix (Stratified Small Cap Results)

### Small Cap ($< ₹7,000\text{ Cr}$) in 119-Trade Backtest:
- **Clean ($N=13$):** Win Rate = **61.5%**, Mean Return = **+8.15%**, Median Return = **+8.82%**, MFE = **+14.83%**, MAE = **-5.25%**, Std Dev = **14.13%**.
- **Vetoed ($N=27$):** Win Rate = **40.7%**, Mean Return = **+1.37%**, Median Return = **+0.76%**, MFE = **+7.22%**, MAE = **-4.71%**, Std Dev = **7.52%**.
- **Statistical Tests:**
  - MFE Edge: Welch's $t$-test $p = 0.0456^*$, Mann-Whitney U $p = 0.0376^*$ (Statistically significant clean advantage).
  - Return Edge: Welch's $t$-test $p = 0.1247$, Mann-Whitney U $p = 0.1122$.
  - Downside Drawdown (MAE): Mann-Whitney U $p = 0.6234$ (No worse tail drawdown in vetoed names).
- **Specific Trigger Lethality in Small Caps:**
  - `PROMOTER_PLEDGE` ($N=5$): Win Rate = **0.0%** ($0/5$), Mean Return = **-1.03%** (Lethal red flag).
  - `FCF_PAT_DIVERGENCE` ($N=22$): Win Rate = **50.0%**, Mean Return = **+1.91%**, MFE = **+7.31%** (Halves peak upside compared to Clean $+14.83\%$).
