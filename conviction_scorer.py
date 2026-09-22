"""ConvictionScorer — Layer 2 of the Vikram v3 architecture.

Pure scoring logic over the fundamentals dict from FundamentalFetcher.
Stock classes by MARKET CAP:
  S < ₹7,000 Cr · M ₹7,000–20,000 Cr · L ≥ ₹20,000 Cr

Small/Mid-Cap 5-Metric Vikram Quality Stack:
  - Operating Leverage: Score (30%)
  - Promoter Pledge Trend: Veto (25%) [Pledge >25% or rising = VETO]
  - FCF/PAT Divergence: Score + Veto (20%) [Ratio outside 0.33–3.0 = VETO]
  - Interest Coverage Trend: Score (20%)
  - RoICE: Score (5%)

Veto metrics NEVER renormalize out — missing data produces UNVERIFIED_VETO.
Score metrics renormalize over resolved metrics only with a Data Completeness Indicator.
"""
import math
from dataclasses import dataclass

@dataclass
class VetoResult:
    status: str
    reason: str

def check_pledge_veto(pledge_pct: float, pledge_direction: str) -> VetoResult:
    if pledge_pct is None or pledge_direction is None:
        return VetoResult(status="UNVERIFIED", reason="Promoter pledge trend data missing")
    if pledge_pct > 25:
        return VetoResult(status="VETO_TRIGGERED", reason=f"Promoter pledge at {pledge_pct:.1f}% exceeds 25% threshold")
    if pledge_direction == "rising" and pledge_pct >= 0.5:
        return VetoResult(status="VETO_TRIGGERED", reason="Promoter pledge rising QoQ")
    return VetoResult(status="CLEAR", reason=f"Pledge at {pledge_pct:.1f}%, within threshold")

def check_fcf_veto(ratio: float, is_financial: bool) -> VetoResult:
    if is_financial:
        return VetoResult(status="CLEAR", reason="Financial sector (FCF not applicable)")
    if ratio is None:
        return VetoResult(status="UNVERIFIED", reason="FCF/PAT ratio data missing")
    if not math.isclose(ratio, 0) and (ratio > 3.0 or ratio < 1 / 3.0):
        return VetoResult(status="VETO_TRIGGERED", reason=f"FCF/PAT 3yr cumulative divergence {ratio:.2f}x (outside [0.33, 3.0])")
    return VetoResult(status="CLEAR", reason=f"FCF/PAT ratio at {ratio:.2f}x, within threshold")

METRIC_WEIGHTS_VIKRAM = {
    "op_leverage": 0.30,
    "pledge_trend": 0.25,
    "fcf_quality": 0.20,
    "interest_coverage": 0.20,
    "roice": 0.05,
}

# Aliases for backward compatibility
METRIC_WEIGHTS_5 = METRIC_WEIGHTS_VIKRAM
METRIC_WEIGHTS = METRIC_WEIGHTS_VIKRAM


def classify(market_cap_cr):
    if market_cap_cr is None:
        return "U"
    if market_cap_cr >= 20000.0:
        return "L"
    if market_cap_cr >= 7000.0:
        return "M"
    return "S"


def _gate_scores(fund):
    """Per-metric /10 fundamental-gate scores. Returns {metric: (score/10 or None)}."""
    gate = {}

    # 1. Operating Leverage (30%)
    ol = fund.get("op_lev_ratio")
    if fund.get("op_lev_inflecting"):
        gate["op_leverage"] = 10 if ol and ol > 3 else 8
    elif ol is not None:
        if ol > 3:
            gate["op_leverage"] = 10
        elif ol >= 2:
            gate["op_leverage"] = 8
        elif ol > 1:
            gate["op_leverage"] = 5
        else:
            gate["op_leverage"] = 2

    # 2. Promoter Pledge Trend (25%)
    direction = fund.get("pledge_direction")
    pledge = fund.get("pledge_trend") or []
    if direction is not None:
        if direction == "falling" and len(pledge) >= 2:
            gate["pledge_trend"] = 10
        elif direction == "falling":
            gate["pledge_trend"] = 8
        elif direction == "flat":
            # Zero absolute pledge + flat direction = near-perfect governance
            # (promoter never pledged; no risk to fall). Score 9.
            # Non-zero pledge + flat = existing pledge not growing. Score 7.
            latest_pledge = pledge[-1] if pledge else None
            if latest_pledge is not None and latest_pledge == 0:
                gate["pledge_trend"] = 9
            else:
                gate["pledge_trend"] = 7
        else:
            gate["pledge_trend"] = 3 if (pledge[-1] or 0) < 2 else 0

    # 3. Interest Coverage Trend (20%)
    cov = fund.get("interest_coverage_trend")
    if cov is not None:
        gate["interest_coverage"] = {"improving": 10, "stable": 4, "deteriorating": 2}.get(cov, 4)

    # 4. RoICE (5%)
    roice_delta = fund.get("roice_pct")
    roce_abs = fund.get("roce_abs_pct")

    def _score_delta(v):
        if v > 30: return 10
        if v >= 20: return 8
        if v >= 10: return 6
        if v >= 0: return 3
        return 0

    def _score_abs(v):
        if v >= 25: return 10
        if v >= 18: return 8
        if v >= 12: return 6
        if v >= 6: return 4
        if v >= 0: return 2
        return 0

    if roice_delta is not None and roce_abs is not None:
        gate["roice"] = round(0.6 * _score_delta(roice_delta) + 0.4 * _score_abs(roce_abs))
    elif roice_delta is not None:
        gate["roice"] = _score_delta(roice_delta)
    elif roce_abs is not None:
        gate["roice"] = _score_abs(roce_abs)

    # 5. FCF/PAT Divergence (20%)
    ratio = fund.get("fcf_pat_ratio")
    if fund.get("sector_type") == "financial":
        pass  # Financials: OCF structurally negative
    elif ratio is not None:
        if ratio > 3.0 or ratio < 1 / 3.0:
            gate["fcf_quality"] = 0
        elif ratio > 0.95:
            gate["fcf_quality"] = 10
        elif ratio >= 0.80:
            gate["fcf_quality"] = 8
        elif ratio >= 0.50:
            gate["fcf_quality"] = 5
        else:
            gate["fcf_quality"] = 2

    return gate


def fundamental_strength(fund):
    """Fundamentals 0-100 score from available gate metrics."""
    veto_reasons = []

    # Check Veto metrics
    pledge = fund.get("pledge_trend") or []
    latest_pledge = pledge[-1] if pledge else None
    pledge_res = check_pledge_veto(latest_pledge, fund.get("pledge_direction"))
    
    fcf_res = check_fcf_veto(fund.get("fcf_pat_ratio"), fund.get("sector_type") == "financial")
    
    active_vetos = [pledge_res, fcf_res]
    
    for v in active_vetos:
        if v.status == "VETO_TRIGGERED":
            veto_reasons.append(v.reason)

    if veto_reasons:
        return {}, 0, "VETO", veto_reasons

    gate = _gate_scores(fund)
    resolved_weights = 0.0
    weighted_score_sum = 0.0

    for metric, w in METRIC_WEIGHTS_VIKRAM.items():
        val = gate.get(metric)
        if val is not None:
            resolved_weights += w
            weighted_score_sum += val * w

    if resolved_weights < 0.15:
        return gate, None, "INSUFFICIENT_DATA", []

    score = round((weighted_score_sum / resolved_weights) * 10)
    rating = "STRONG" if score >= 75 else ("MODERATE" if score >= 45 else "WEAK")
    return gate, score, rating, []


class ConvictionScorer:
    def score(self, fund):
        """fund: dict from FundamentalFetcher.fetch(). Returns scoring dict."""
        if not fund or fund.get("error") or fund.get("confidence") in ["PARSED_LOW_CONFIDENCE"]:
            err_msg = fund.get("error", "no data") if fund else "no data"
            badge = f"❓ Fundamentals unavailable ({err_msg})"

            return {
                "stock_class": "U",
                "veto": False,
                "unverified_veto": False,
                "veto_reasons": [],
                "score": None,
                "rating": "FUNDAMENTALS_UNAVAILABLE",
                "boosters": [],
                "drags": [],
                "display_badge": badge,
                "data_completeness": {"resolved_count": 0, "total_count": 6, "label": "0/6 metrics resolved"},
                "not_applicable_metrics": [],
                "rpt_data_missing": False,
            }

        mcap = fund.get("market_cap_cr")
        stock_class = classify(mcap)

        base = {
            "stock_class": stock_class,
            "market_cap_cr": mcap,
            "veto": False,
            "unverified_veto": False,
            "veto_reasons": [],
            "score": None,
            "rating": None,
            "boosters": [],
            "drags": [],
            "display_badge": None,
            "data_completeness": {"resolved_count": 0, "total_count": 5, "label": "0/5 metrics resolved"},
            "not_applicable_metrics": [],
            "rpt_data_missing": False,
            "rpt_fetch_status": "NOT_APPLICABLE",
            "veto_status_table_row": "| 🚫 Veto Status | ⏳ UNVERIFIED | ⏳ |",
        }

        # Large-cap disclaimer handling
        if stock_class == "L":
            gate, fs_score, fs_rating, veto_reasons = fundamental_strength(fund)
            
            # Check for Unverified Vetoes (missing data)
            unv = []
            if fund.get("pledge_direction") is None:
                unv.append("Promoter pledge trend data missing")
            if fund.get("sector_type") != "financial" and fund.get("fcf_pat_ratio") is None:
                unv.append("FCF/PAT ratio data missing")
                
            base["rating"] = "LARGE_CAP_DISCLAIMER"
            base["fundamental_score"] = fs_score
            base["fundamental_rating"] = fs_rating
            base["gate"] = gate
            base["veto"] = len(veto_reasons) > 0
            
            if unv:
                base["unverified_veto"] = True
                base["veto_reasons"] = veto_reasons + unv
            else:
                base["veto_reasons"] = veto_reasons
                
            if fs_score is not None:
                base["display_badge"] = f"⚠️ Large-cap (≥ ₹20,000 Cr) · Fundamentals {fs_score}/100 ({fs_rating}) — rebalancing noise; verify separately"
            else:
                base["display_badge"] = "⚠️ Large-cap signal — likely rebalancing noise; verify separately"
            if base["veto"]:
                base["veto_status_table_row"] = "| 🚫 Veto Status | 🚫 VETO_TRIGGERED | 🚫 |"
            elif base["unverified_veto"]:
                base["veto_status_table_row"] = "| 🚫 Veto Status | ⏳ UNVERIFIED | ⏳ |"
            else:
                base["veto_status_table_row"] = "| 🚫 Veto Status | CLEAR | ✅ |"
                
            return base

        if fund.get("sector_type") == "financial":
            base["rating"] = "NOT_SCORED_FINANCIAL_BIZ"
            base["display_badge"] = "⚠️ Financial/Trading Business — Standard scorer not calibrated for this model. Manual review required."
            base["score"] = None
            base["veto_status_table_row"] = "| 🚫 Veto Status | CLEAR | ✅ |"
            return base

        if fund.get("business_model_changed"):
            base["multi_year_trend_warning"] = "LOW_CONFIDENCE — business model changed <5yr ago. Multi-year trend metrics (RoICE, FCF/PAT trend) straddle two unrelated businesses."

        # Veto & Unverified Veto Checks (Small & Mid Cap)
        veto_reasons = []
        unverified_veto_reasons = []
        veto_checks_passed = []

        # Active Veto State Machine (Pledge, FCF)
        pledge = fund.get("pledge_trend") or []
        latest_pledge = pledge[-1] if pledge else None
        pledge_res = check_pledge_veto(latest_pledge, fund.get("pledge_direction"))
        
        is_financial = fund.get("sector_type") == "financial"
        if is_financial:
            base["not_applicable_metrics"].append("fcf_quality")
            
        fcf_res = check_fcf_veto(fund.get("fcf_pat_ratio"), is_financial)
        
        active_vetos = [pledge_res, fcf_res]
        
        for v in active_vetos:
            if v.status == "VETO_TRIGGERED":
                veto_reasons.append(v.reason)
            elif v.status == "UNVERIFIED":
                unverified_veto_reasons.append(v.reason)
            elif v.status == "CLEAR":
                veto_checks_passed.append("CLEAR")

        # Handle hard Vetoes
        if veto_reasons:
            base["veto"] = True
            base["veto_reasons"] = veto_reasons
            base["score"] = 0
            base["rating"] = "VETO"
            base["display_badge"] = f"🚫 VETO: {veto_reasons[0]}"
            base["veto_status_table_row"] = "| 🚫 Veto Status | 🚫 VETO_TRIGGERED | 🚫 |"
            base["gate"] = _gate_scores(fund)
            return base

        # Handle Unverified Veto (missing mandatory veto metrics block clean pass)
        if unverified_veto_reasons:
            base["unverified_veto"] = True
            base["veto_reasons"] = unverified_veto_reasons
            base["rating"] = "UNVERIFIED_VETO"
            base["veto_status_table_row"] = "| 🚫 Veto Status | ⏳ UNVERIFIED | ⏳ |"
        else:
            base["veto_status_table_row"] = "| 🚫 Veto Status | CLEAR | ✅ |"

        # Calculate Score Metrics Renormalization
        gate = _gate_scores(fund)
        boosters, drags = [], []

        resolved_weights = 0.0
        weighted_score_sum = 0.0
        resolved_count = 0

        active_weights = METRIC_WEIGHTS_VIKRAM

        for metric, w in active_weights.items():
            if metric in base["not_applicable_metrics"]:
                continue
            val = gate.get(metric)
            if val is not None:
                resolved_count += 1
                resolved_weights += w
                weighted_score_sum += (val * 10) * w

        total_applicable = 5 - len(base["not_applicable_metrics"])
        mode_label = "5-Metric Vikram"
        base["data_completeness"] = {
            "resolved_count": resolved_count,
            "total_count": total_applicable,
            "label": f"{mode_label} ({resolved_count}/{total_applicable} metrics resolved)"
        }

        if resolved_weights > 0:
            final_score = round(weighted_score_sum / resolved_weights)
        else:
            final_score = 50

        final_score = max(0, min(100, final_score))
        base["score"] = final_score

        # Boosters & Drags logging
        if gate.get("op_leverage") and gate["op_leverage"] >= 8:
            boosters.append(f"Strong Operating Leverage (30% weight, +{gate['op_leverage']*10}/100)")
        elif gate.get("op_leverage") and gate["op_leverage"] <= 2:
            drags.append(f"Weak Operating Leverage (30% weight, -{100 - gate['op_leverage']*10}/100)")

        if gate.get("interest_coverage") and gate["interest_coverage"] >= 8:
            boosters.append("Interest coverage improving (+20% weight)")
        elif gate.get("interest_coverage") and gate["interest_coverage"] <= 2:
            drags.append("Interest coverage deteriorating (-20% weight)")

        if base["unverified_veto"]:
            badge = f"⚠️ {final_score} | Unverified — manual check required ({unverified_veto_reasons[0]})"
            rating = "UNVERIFIED_VETO"
        elif final_score >= 75:
            if len(veto_checks_passed) >= 1:
                rating = "HIGH_CONVICTION"
                badge = f"⚡ {final_score} | ✅ Clean Pass ({base['data_completeness']['label']})"
            else:
                rating = "UNVERIFIED_VETO"
                badge = f"⚠️ {final_score} | No veto checks resolved — manual review required"
        elif final_score >= 45:
            if len(veto_checks_passed) >= 1:
                rating = "MODERATE"
                badge = f"✅ {final_score} | ({base['data_completeness']['label']})"
            else:
                rating = "UNVERIFIED_VETO"
                badge = f"⚠️ {final_score} | No veto checks resolved — manual review required"
        else:
            rating = "LOW"
            badge = f"⚠️ {final_score} | Weak fundamentals ({base['data_completeness']['label']})"

        base["rating"] = rating
        base["boosters"] = boosters
        base["drags"] = drags
        base["display_badge"] = badge
        return base
