"""MomentumScorer — Standalone Tactical Breakout & Float Cornering Engine.

Pro-Spike Layer 3:
Combines:
  Sub-Part A (55%): Today's Float Mechanics
    - Delivery % (≥87%)
    - Delivery Turnover (₹3.5–5.0 Cr)
    - Float Absorbed % (>1.5%)
    - Intraday MAE (> -1.8%)
  Sub-Part B (45%): Empirical Fundamentals (Live Ledger Winner Weights)
    - FCF / PAT Quality: 30%
    - Promoter Pledge: 30%
    - Interest Coverage: 25%
    - Op Leverage: 10%
    - RoICE: 5%

If global hard veto is active, Momentum Scoring is strictly blocked.
"""
from typing import Dict, Any, Optional
from conviction_scorer import _gate_scores, check_pledge_veto, check_fcf_veto

MOMENTUM_WEIGHTS_B = {
    "fcf_quality": 0.30,
    "pledge_trend": 0.30,
    "interest_coverage": 0.25,
    "op_leverage": 0.10,
    "roice": 0.05,
}

PART_A_TOTAL_WEIGHT = 0.55
PART_B_TOTAL_WEIGHT = 0.45


def score_delivery_pct(deliv_pct: Optional[float]) -> int:
    """Score delivery % /10."""
    if deliv_pct is None:
        return 0
    if deliv_pct >= 95.0:
        return 10
    if deliv_pct >= 90.0:
        return 8
    if deliv_pct >= 87.0:
        return 6
    if deliv_pct >= 80.0:
        return 3
    return 0


def score_delivery_turnover(turnover_cr: Optional[float]) -> int:
    """Score delivery turnover (in ₹ Cr) /10. Sweet spot ₹3.5-5.0 Cr for small cap cornering."""
    if turnover_cr is None or turnover_cr <= 0:
        return 0
    if 3.5 <= turnover_cr <= 5.0:
        return 10
    if (2.5 <= turnover_cr < 3.5) or (5.0 < turnover_cr <= 7.5):
        return 7
    if (1.5 <= turnover_cr < 2.5) or (7.5 < turnover_cr <= 10.0):
        return 4
    return 1


def score_float_absorbed(absorbed_pct: Optional[float]) -> int:
    """Score % of free float absorbed in a single day /10."""
    if absorbed_pct is None or absorbed_pct <= 0:
        return 0
    if absorbed_pct >= 3.5:
        return 10
    if absorbed_pct >= 2.5:
        return 8
    if absorbed_pct >= 1.5:
        return 6
    if absorbed_pct >= 1.0:
        return 3
    return 0


def score_mae(mae_pct: Optional[float]) -> int:
    """Score intraday MAE (% dip from entry price) /10. Closer to 0% is better."""
    if mae_pct is None:
        return 5  # neutral if unknown
    if mae_pct >= 0.0:
        return 10
    if mae_pct >= -0.8:
        return 8
    if mae_pct >= -1.8:
        return 6
    if mae_pct >= -2.5:
        return 3
    return 0


class MomentumScorer:
    def score(self, signal_row: Dict[str, Any], fund: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates Momentum Score (0-100) combining float mechanics and empirical fundamentals."""
        # 1. Global Veto Check
        is_financial = fund.get("sector_type") == "financial"
        pledge = fund.get("pledge_trend") or []
        latest_pledge = pledge[-1] if pledge else None
        
        pledge_res = check_pledge_veto(latest_pledge, fund.get("pledge_direction"))
        fcf_res = check_fcf_veto(fund.get("fcf_pat_ratio"), is_financial)

        veto_reasons = []
        if pledge_res.status == "VETO_TRIGGERED":
            veto_reasons.append(pledge_res.reason)
        if fcf_res.status == "VETO_TRIGGERED":
            veto_reasons.append(fcf_res.reason)


        # 2. Sub-Part A: Today's Float Mechanics (55% Weight)
        deliv_per = None
        for k in ("DELIV_PER", "Delivery_Percent", "DELIV_PCT"):
            if k in signal_row and signal_row[k] is not None:
                try:
                    deliv_per = float(signal_row[k])
                    break
                except (ValueError, TypeError):
                    pass

        # Delivery Turnover in ₹ Cr
        turnover_cr = None
        for k in ("DELIVERY_TURNOVER_CR", "delivery_turnover_cr"):
            if k in signal_row and signal_row[k] is not None:
                try:
                    turnover_cr = float(signal_row[k])
                    break
                except (ValueError, TypeError):
                    pass
        if turnover_cr is None:
            # Maybe raw turnover in INR
            for k in ("DELIVERY_TURNOVER", "delivery_turnover"):
                if k in signal_row and signal_row[k] is not None:
                    try:
                        turnover_cr = float(signal_row[k]) / 10000000.0
                        break
                    except (ValueError, TypeError):
                        pass

        # Float Absorbed %
        float_abs_pct = None
        if "FLOAT_ABSORBED_PCT" in signal_row and signal_row["FLOAT_ABSORBED_PCT"] is not None:
            try:
                float_abs_pct = float(signal_row["FLOAT_ABSORBED_PCT"])
            except (ValueError, TypeError):
                pass
        elif turnover_cr is not None and fund.get("free_float_cr"):
            try:
                ff_cr = float(fund["free_float_cr"])
                if ff_cr > 0:
                    float_abs_pct = (turnover_cr / ff_cr) * 100.0
            except (ValueError, TypeError):
                pass

        # Intraday MAE
        mae_pct = None
        for k in ("MAE", "MAE_PCT", "INTRADAY_MAE"):
            if k in signal_row and signal_row[k] is not None:
                try:
                    mae_pct = float(signal_row[k])
                    break
                except (ValueError, TypeError):
                    pass
        if mae_pct is None:
            # Try computing from LOW and ENTRY_PRICE / OPEN
            try:
                low = float(signal_row.get("LOW") or signal_row.get("Low"))
                entry = float(signal_row.get("ENTRY_PRICE") or signal_row.get("OPEN") or signal_row.get("Open") or signal_row.get("CLOSE"))
                if entry > 0:
                    mae_pct = ((low - entry) / entry) * 100.0
            except (ValueError, TypeError):
                pass

        s_deliv = score_delivery_pct(deliv_per)
        s_turn = score_delivery_turnover(turnover_cr)
        s_float = score_float_absorbed(float_abs_pct)
        s_mae = score_mae(mae_pct)

        # 4 metrics, equally weighted in Part A (25% each of Part A)
        part_a_pct = ((s_deliv + s_turn + s_float + s_mae) / 40.0) * 100.0
        part_a_contrib = (part_a_pct / 100.0) * 55.0

        part_a_breakdown = {
            "delivery_pct": {
                "raw": deliv_per,
                "label": f"{deliv_per:.1f}%" if deliv_per is not None else "N/A",
                "gate_score": s_deliv,
                "threshold": "≥ 87%",
                "pts": round((s_deliv / 40.0) * 55.0, 2),
            },
            "delivery_turnover": {
                "raw": turnover_cr,
                "label": f"₹{turnover_cr:.2f} Cr" if turnover_cr is not None else "N/A",
                "gate_score": s_turn,
                "threshold": "₹3.5–5.0 Cr",
                "pts": round((s_turn / 40.0) * 55.0, 2),
            },
            "float_absorbed": {
                "raw": float_abs_pct,
                "label": f"{float_abs_pct:.2f}%" if float_abs_pct is not None else "N/A",
                "gate_score": s_float,
                "threshold": "> 1.5%",
                "pts": round((s_float / 40.0) * 55.0, 2),
            },
            "intraday_mae": {
                "raw": mae_pct,
                "label": f"{mae_pct:.2f}%" if mae_pct is not None else "N/A",
                "gate_score": s_mae,
                "threshold": "> -1.8%",
                "pts": round((s_mae / 40.0) * 55.0, 2),
            },
        }

        # 3. Sub-Part B: Empirical Fundamentals (45% Weight)
        gate = _gate_scores(fund)
        part_b_weighted_sum = 0.0
        part_b_resolved_weights = 0.0
        part_b_breakdown = {}

        for metric, w in MOMENTUM_WEIGHTS_B.items():
            g_score = gate.get(metric)
            if g_score is not None:
                part_b_resolved_weights += w
                part_b_weighted_sum += (g_score * 10) * w
                part_b_breakdown[metric] = {
                    "gate_score": g_score,
                    "weight_pct": int(w * 100),
                    "pts": round((g_score / 10.0) * (w * 45.0), 2),
                }
            else:
                part_b_breakdown[metric] = {
                    "gate_score": None,
                    "weight_pct": int(w * 100),
                    "pts": 0.0,
                }

        if part_b_resolved_weights > 0:
            part_b_pct = (part_b_weighted_sum / part_b_resolved_weights)
        else:
            part_b_pct = 50.0

        part_b_contrib = (part_b_pct / 100.0) * 45.0

        # 4. Final Composite Momentum Score
        final_momentum_score = round(part_a_contrib + part_b_contrib)
        final_momentum_score = max(0, min(100, final_momentum_score))

        if final_momentum_score >= 85:
            tier = "ELITE"
            verdict = "🟢 ELITE — Float cornering in progress + clean balance sheet. Prime entry."
        elif final_momentum_score >= 70:
            tier = "HIGH"
            verdict = "🔵 HIGH — Strong institutional accumulation setup. Standard execution."
        elif final_momentum_score >= 55:
            tier = "MODERATE"
            verdict = "🟡 MODERATE — Marginal float mechanics or fundamentals. Reduced sizing."
        else:
            tier = "WEAK"
            verdict = "🔴 WEAK — Insufficient float absorption or weak metrics. Skip."

        if veto_reasons:
            return {
                "blocked_by_veto": True,
                "veto_reasons": veto_reasons,
                "momentum_score": 0,
                "momentum_tier": "BLOCKED",
                "part_a_score": 0.0,
                "part_a_contrib": 0.0,
                "part_b_score": 0.0,
                "part_b_contrib": 0.0,
                "part_a_breakdown": part_a_breakdown,
                "part_b_breakdown": part_b_breakdown,
                "verdict": "🚫 BLOCKED BY VETO GATE — Execution Forbidden",
            }

        return {
            "blocked_by_veto": False,
            "veto_reasons": [],
            "momentum_score": final_momentum_score,
            "momentum_tier": tier,
            "part_a_score": round(part_a_pct, 1),
            "part_a_contrib": round(part_a_contrib, 1),
            "part_b_score": round(part_b_pct, 1),
            "part_b_contrib": round(part_b_contrib, 1),
            "part_a_breakdown": part_a_breakdown,
            "part_b_breakdown": part_b_breakdown,
            "verdict": verdict,
        }
