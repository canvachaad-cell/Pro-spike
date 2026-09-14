"""ConvictionScorer — Layer 2 of the Vikram v3 architecture.

Pure scoring logic over the fundamentals dict from FundamentalFetcher.
Stock classes by MARKET CAP:
  S < ₹7,000 Cr · M ₹7,000–20,000 Cr · L ≥ ₹20,000 Cr

Small/Mid-Cap 6-Metric Stack Rank & Weights:
  - Operating Leverage: Score (31%)
  - RPT % of Revenue: Veto (26%) [Caution >10%, Veto >20%]
  - Promoter Pledge Trend: Veto (19%)
  - Interest Coverage Trend: Score (15%)
  - RoICE: Score (6%)
  - FCF/PAT Divergence: Score + Veto (3%)

Veto metrics NEVER renormalize out — missing data produces UNVERIFIED_VETO.
Score metrics renormalize over resolved metrics only with a Data Completeness Indicator.
"""
import math

PROVISIONAL_RPT_CAUTION_PCT = 10.0
PROVISIONAL_RPT_VETO_PCT = 20.0

METRIC_WEIGHTS = {
    "op_leverage": 0.31,
    "rpt_pct": 0.26,
    "pledge_trend": 0.19,
    "interest_coverage": 0.15,
    "roice": 0.06,
    "fcf_quality": 0.03,
}

METRIC_WEIGHTS_5 = {
    "op_leverage": 0.38,
    "pledge_trend": 0.25,
    "fcf_quality": 0.20,
    "interest_coverage": 0.09,
    "roice": 0.08,
}


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

    # 1. Operating Leverage (31%)
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

    # 2. RPT % of Revenue (26%)
    rpt_pct = fund.get("rpt_pct")
    rpt_status = fund.get("rpt_status")
    if rpt_status == "OK" and rpt_pct is not None:
        if rpt_pct > PROVISIONAL_RPT_VETO_PCT:
            gate["rpt_pct"] = 0
        elif rpt_pct > PROVISIONAL_RPT_CAUTION_PCT:
            gate["rpt_pct"] = 5
        else:
            gate["rpt_pct"] = 10

    # 3. Promoter Pledge Trend (19%)
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

    # 4. Interest Coverage Trend (15%)
    cov = fund.get("interest_coverage_trend")
    if cov is not None:
        gate["interest_coverage"] = {"improving": 10, "stable": 4, "deteriorating": 2}.get(cov, 4)

    # 5. RoICE (6%)
    roice = fund.get("roice_pct")
    if roice is not None:
        if roice > 30:
            gate["roice"] = 10
        elif roice >= 20:
            gate["roice"] = 8
        elif roice >= 10:
            gate["roice"] = 6
        elif roice >= 0:
            gate["roice"] = 3
        else:
            gate["roice"] = 0

    # 6. FCF/PAT Divergence (3%)
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
    if fund.get("pledge_direction") == "rising" and (pledge[-1] if pledge else 0) >= 0.5:
        veto_reasons.append("Promoter pledge rising QoQ")

    ratio = fund.get("fcf_pat_ratio")
    if fund.get("sector_type") != "financial" and ratio is not None and not math.isclose(ratio, 0) and (ratio > 3.0 or ratio < 1 / 3.0):
        veto_reasons.append(f"FCF/PAT 3yr cumulative divergence ({ratio:.2f}x)")

    rpt_pct = fund.get("rpt_pct")
    if fund.get("rpt_status") == "OK" and rpt_pct is not None and rpt_pct > PROVISIONAL_RPT_VETO_PCT:
        veto_reasons.append(f"RPT % of Revenue exceeds veto threshold ({rpt_pct:.1f}% > {PROVISIONAL_RPT_VETO_PCT}%)")

    if veto_reasons:
        return {}, 0, "VETO", veto_reasons

    gate = _gate_scores(fund)
    avail = [v for v in gate.values() if v is not None]
    if len(avail) < 2:
        return gate, None, "INSUFFICIENT_DATA", []
    score = round(sum(avail) / len(avail) * 10)
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
            "data_completeness": {"resolved_count": 0, "total_count": 6, "label": "0/6 metrics resolved"},
            "not_applicable_metrics": [],
            "rpt_data_missing": False,
        }

        # Large-cap disclaimer handling
        if stock_class == "L":
            gate, fs_score, fs_rating, veto_reasons = fundamental_strength(fund)
            
            # Check for Unverified Vetoes (missing data)
            unv = []
            rpt_status_lc = fund.get("rpt_status", "NOT_SCRAPED")
            if rpt_status_lc in ("NOT_FOUND", "NOT_SCRAPED") or fund.get("rpt_pct") is None:
                base["not_applicable_metrics"].append("rpt_pct")
                base["rpt_data_missing"] = True
                base["rpt_fetch_status"] = rpt_status_lc
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
            return base

        # Veto & Unverified Veto Checks (Small & Mid Cap)
        veto_reasons = []
        unverified_veto_reasons = []

        # Veto 1: RPT %
        rpt_status = fund.get("rpt_status", "NOT_SCRAPED")
        rpt_pct = fund.get("rpt_pct")
        if rpt_status in ("NOT_FOUND", "NOT_SCRAPED") or rpt_pct is None:
            # NOT_FOUND  → scraper ran and found nothing (Reg23 PDF absent on BSE)
            # NOT_SCRAPED → symbol never ran through the offline scraper
            # Both result in the metric being excluded from the score, but
            # we flag them differently so Vikram can display ⏳ vs — N/A.
            base["not_applicable_metrics"].append("rpt_pct")
            base["rpt_data_missing"] = True
            base["rpt_fetch_status"] = rpt_status
        elif rpt_pct > PROVISIONAL_RPT_VETO_PCT:
            veto_reasons.append(f"RPT % of Revenue exceeds veto threshold ({rpt_pct:.1f}% > {PROVISIONAL_RPT_VETO_PCT}%)")

        # Veto 2: Promoter Pledge
        pledge_dir = fund.get("pledge_direction")
        pledge = fund.get("pledge_trend") or []
        if pledge_dir is None:
            unverified_veto_reasons.append("Promoter pledge trend data missing")
        elif pledge_dir == "rising" and (pledge[-1] if pledge else 0) >= 0.5:
            veto_reasons.append(f"Promoter pledge rising QoQ ({pledge})")

        # Veto 3: FCF/PAT Divergence
        is_financial = fund.get("sector_type") == "financial"
        ratio = fund.get("fcf_pat_ratio")
        if is_financial:
            base["not_applicable_metrics"].append("fcf_quality")
        elif ratio is None:
            unverified_veto_reasons.append("FCF/PAT ratio data missing")
        elif not math.isclose(ratio, 0) and (ratio > 3.0 or ratio < 1 / 3.0):
            veto_reasons.append(f"FCF/PAT 3yr cumulative divergence {ratio:.2f}x (outside [0.33, 3.0])")

        # Handle hard Vetoes
        if veto_reasons:
            base["veto"] = True
            base["veto_reasons"] = veto_reasons
            base["score"] = 0
            base["rating"] = "VETO"
            base["display_badge"] = f"🚫 VETO: {veto_reasons[0]}"
            return base

        # Handle Unverified Veto (missing mandatory veto metrics block clean pass)
        if unverified_veto_reasons:
            base["unverified_veto"] = True
            base["veto_reasons"] = unverified_veto_reasons
            base["rating"] = "UNVERIFIED_VETO"

        # Calculate Score Metrics Renormalization
        gate = _gate_scores(fund)
        boosters, drags = [], []

        resolved_weights = 0.0
        weighted_score_sum = 0.0
        resolved_count = 0

        active_weights = METRIC_WEIGHTS_5 if base["rpt_data_missing"] else METRIC_WEIGHTS

        for metric, w in active_weights.items():
            if metric in base["not_applicable_metrics"]:
                continue
            val = gate.get(metric)
            if val is not None:
                resolved_count += 1
                resolved_weights += w
                weighted_score_sum += (val * 10) * w

        total_applicable = 6 - len(base["not_applicable_metrics"])
        mode_label = "5-Metric Mode" if base["rpt_data_missing"] else "6-Metric Mode"
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
            boosters.append(f"Strong Operating Leverage (31% weight, +{gate['op_leverage']*10}/100)")
        elif gate.get("op_leverage") and gate["op_leverage"] <= 2:
            drags.append(f"Weak Operating Leverage (31% weight, -{100 - gate['op_leverage']*10}/100)")

        if rpt_pct is not None and rpt_pct > PROVISIONAL_RPT_CAUTION_PCT:
            drags.append(f"RPT % of Revenue in caution zone ({rpt_pct:.1f}%)")

        if gate.get("interest_coverage") and gate["interest_coverage"] >= 8:
            boosters.append("Interest coverage improving (+15% weight)")
        elif gate.get("interest_coverage") and gate["interest_coverage"] <= 2:
            drags.append("Interest coverage deteriorating (-15% weight)")

        if base["unverified_veto"]:
            badge = f"⚠️ {final_score} | Unverified — manual check required ({unverified_veto_reasons[0]})"
            rating = "UNVERIFIED_VETO"
        elif final_score >= 75:
            rating = "HIGH_CONVICTION"
            badge = f"⚡ {final_score} | ✅ Clean Pass ({base['data_completeness']['label']})"
        elif final_score >= 45:
            rating = "MODERATE"
            badge = f"✅ {final_score} | ({base['data_completeness']['label']})"
        else:
            rating = "LOW"
            badge = f"⚠️ {final_score} | Weak fundamentals ({base['data_completeness']['label']})"

        base["rating"] = rating
        base["boosters"] = boosters
        base["drags"] = drags
        base["display_badge"] = badge
        return base
