# Mobile UI/UX Design Audit — Dashboard & 12-Condition Screener Signal Cards

**Date:** 2026-10-02  
**Auditor:** `fz-uidesigner` (Senior Product Designer & Design Director)  
**Target Focus:** Mobile Viewport (390×844 and 360×780) — Dashboard Page (`/`) & 12-Condition Screener Signal Cards (`#signals-grid`).  
**Visual Artifacts Captured:** 
- `mobile_dashboard_390.png` (Full viewport at 390px)
- `mobile_dashboard_signals_crop.png` (Dedicated crop of `#signals-grid` cards)
- `mobile_dashboard_scrolled_mid.png` (Mid-scroll view)
- `mobile_dashboard_scrolled_bottom.png` (Bottom-scroll stats tiles)

---

## 1. First Impression
On mobile, the Dashboard suffers from a critical informational and visual hierarchy inversion: while the top banner loudly proclaims *"Live Scanning"* and renders a massive 64px *"2 Signals Passing"* counter, the stock cards themselves commit the ultimate trading UI sin—**the Stock Price (Close/CMP) and Delivery % are 100% missing from the cards on mobile screens**. 

Visually, the signal cards feel lopsided, cramped, and unfinished: the left side collapses into a ragged 4-line vertical stair-step of wrapping pills with a stretched green dot, while the right 40% of the card is a barren void punctuated only by a lone turnover number and an inert, non-functional downward arrow.

---

## 2. Scores

| Area | Mobile | Desktop |
| :--- | :--- | :--- |
| **Whitespace** | 4 / 10 | 8 / 10 |
| **Hierarchy** | 3 / 10 | 7.5 / 10 |
| **Color** | 7 / 10 | 8 / 10 |
| **Typography** | 5 / 10 | 8 / 10 |
| **Buttons & Controls** | 5 / 10 | 7.5 / 10 |
| **Element Placement** | 3 / 10 | 8 / 10 |
| **Consistency** | 5 / 10 | 7.5 / 10 |
| **Modernity** | 4.5 / 10 | 8 / 10 |

---

## 3. Issues — Ranked by Severity

### 🔴 High

1. **Critical Missing Data — Stock Price (Close/CMP) is 100% Hidden on Mobile**
   - **Severity:** High
   - **What is wrong:** The stock close/CMP price does not render anywhere on the card on mobile viewports (< 768px).
   - **Where it is:** `dash_pages/dashboard.py:195` (`build_signal_rows`) inside `html.Div(className="hidden md:flex flex-1 max-w-[120px] ...")`.
   - **Which version:** Mobile
   - **Why it feels off:** In a quantitative trading app, a stock card without the stock price breaks the most fundamental law of financial UX hierarchy—traders cannot evaluate a setup or make decisions without seeing what the stock is trading at.

2. **Core Screener Proof Metric Omission — Delivery % Hidden on Mobile**
   - **Severity:** High
   - **What is wrong:** `DELIVERY %` is tagged with `hidden sm:flex` and does not render on mobile screens (< 640px).
   - **Where it is:** `dash_pages/dashboard.py:218` (`build_signal_rows`).
   - **Which version:** Mobile
   - **Why it feels off:** The entire premise of the "12-Condition Screener" is Wyckoffian accumulation and high delivery volume percentage (e.g. GNRL at 90.3% delivery); hiding this metric on mobile strips the screener of its core analytical justification.

3. **Ragged 4-Tier Vertical Pill Stair-Step & Horizontal Card Imbalance**
   - **Severity:** High
   - **What is wrong:** The ticker symbol (`GNRL`), exchange pill (`NSE`), market-cap class (`[S]`), and veto badge (`🚫 VETO: ...`) stack into 4 sequential vertical lines on the left side of the card, while the right 40% of the card is a dead empty void.
   - **Where it is:** `dash_pages/dashboard.py:180-192` (`build_signal_rows`).
   - **Which version:** Mobile
   - **Why it feels off:** Elements are piled into an unformatted vertical column rather than a balanced 2-column or structured 3-row layout, inflating card height to ~180px and wasting precious mobile screen estate.

4. **Deceptive Interactive Affordance — Inert `arrow_drop_down` Chevron**
   - **Severity:** High
   - **What is wrong:** Every card renders a downward chevron icon (`arrow_drop_down`) with `cursor-pointer`, but tapping or clicking the card does nothing because there is no expansion callback or detail drawer.
   - **Where it is:** `dash_pages/dashboard.py:231` (`build_signal_rows`).
   - **Which version:** Both (most damaging on Mobile where users repeatedly tap it expecting an accordion)
   - **Why it feels off:** An accordion arrow creates an explicit promise of expandable details; rendering a dead icon frustrates users and destroys confidence in the UI.

---

### 🟡 Medium

5. **Deformed Status Dot — Vertically Stretched Floating Green Pill**
   - **Severity:** Medium
   - **What is wrong:** The `w-2.5 h-2.5` pulse dot on the left is vertically aligned to a tall multi-line text block via flex `items-center`, causing it to float awkwardly in the vertical center of the card like a detached pill artifact.
   - **Where it is:** `dash_pages/dashboard.py:184` (`build_signal_rows`).
   - **Which version:** Mobile
   - **Why it feels off:** A status dot must be optically anchored directly to the title it qualifies (the stock Symbol), not floating halfway down the card.

6. **Excessive Vertical Chrome Eating Above-the-Fold Viewport ("Live Scanning" Banner)**
   - **Severity:** Medium
   - **What is wrong:** The "Live Scanning: Phase 1 MVP" pill stretches across 100% width of the mobile screen, inserting 52px of empty decorative padding directly between the page title and the first signal card.
   - **Where it is:** `dash_pages/dashboard.py:287-293` (`layout`).
   - **Which version:** Mobile
   - **Why it feels off:** Above-the-fold mobile space is sacred; pushing the actionable signal cards down for a static status pill forces unnecessary scrolling before any data is seen.

7. **Optical Collision & Friction Between Counter and Filter (`Signals Passing` vs. `Hide T2T`)**
   - **Severity:** Medium
   - **What is wrong:** In the card header, the giant 64px number, "Signals Passing" text, and the "Hide T2T" toggle are pushed to opposite edges with `items-end justify-between`, creating an optical collision where subtext lines wrap awkwardly on narrow (360px) devices.
   - **Where it is:** `dash_pages/dashboard.py:310-341` (`layout`).
   - **Which version:** Mobile
   - **Why it feels off:** The primary metric header lacks cohesive hierarchy, forcing the eye to zigzag between a giant green numeral and a tiny toggle switch.

8. **Non-Tabular Typography in Turnover Metric**
   - **Severity:** Medium
   - **What is wrong:** The turnover number (`₹ 5.82Cr`) uses variable-width `font-data-md` without `tabular-nums` or explicit monospace alignment.
   - **Where it is:** `dash_pages/dashboard.py:228` (`build_signal_rows`).
   - **Which version:** Both
   - **Why it feels off:** Financial numbers in trading applications must use `font-mono tabular-nums` to enable optical comparison and alignment across cards.

---

### 🟢 Low

9. **Secondary Stats Tiles Ordering Below Signals on Mobile**
   - **Severity:** Low
   - **What is wrong:** Total Scanned (4,266), NSE Stocks (2,291), and BSE Stocks (1,975) appear below all signal cards at the bottom of the page, where they get buried under 1,800px of scrolling if there are 10 signals.
   - **Where it is:** `dash_pages/dashboard.py:354-410` (`layout`).
   - **Which version:** Mobile
   - **Why it feels off:** Macro market context is useful context for the screener and should be available as a compact top overview or quick metric strip rather than buried at the bottom.

10. **System Health Card Redundancy on Mobile**
    - **Severity:** Low
    - **What is wrong:** The "System Health" tile takes up 140px of vertical space at the very bottom of the page displaying static checkmarks ("Real-time data stream optimal", "ML inference engine idle").
    - **Where it is:** `dash_pages/dashboard.py:389-408` (`layout`).
    - **Which version:** Mobile
    - **Why it feels off:** Diagnostic cards with static checkmarks add visual noise and drag down mobile density without offering actionable value to a trader on a phone.

---

**Summary:** 4 High, 4 Medium, 2 Low (Total: 10 Issues).

---

## 4. Fixes (Design Specifications)

### A. Overhaul the 12-Condition Signal Card Structure (`dash_pages/dashboard.py:177-235`)
Replace the unstructured flex-wrap layout with a crisp, 3-row structured financial card:

1. **Row 1 — Identity & Price Bar (`flex items-center justify-between pb-2 border-b border-white/5`):**
   - **Left:** Symbol `GNRL` in `text-[17px] font-bold text-on-surface tracking-tight` (`#f8fafc`), with an inline `8px` pulse dot (`#5af0b3`), followed immediately by Exchange tag (`NSE` in `px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#38bdf8]/15 text-[#38bdf8] border border-[#38bdf8]/30`), and Market-Cap Class pill (`[S]` in `px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-[#e74c3c]/15 text-[#ff6b6b] border border-[#e74c3c]/30`).
   - **Right:** Price display: `text-[18px] font-mono font-bold text-on-surface tabular-nums` (e.g. `₹97.18`).
2. **Row 2 — Conviction & Veto Badges (`py-2`):**
   - If Vetoed: Full-width or inline rounded-lg badge: `bg-[#e74c3c]/15 text-[#ff6b6b] border border-[#e74c3c]/30 text-xs font-semibold px-2.5 py-1 flex items-center gap-1.5`.
   - If High Conviction: `bg-[#2ecc71]/10 text-[#2ecc71] border border-[#2ecc71]/30 text-xs font-semibold px-2.5 py-1`.
3. **Row 3 — High-Density Metric Strip (`grid grid-cols-2 gap-3 pt-2 bg-surface-container-high/40 rounded-lg p-2.5 mt-1`):**
   - **Metric 1 (Delivery %):** Label `DELIVERY %` in `text-[10px] font-mono text-outline uppercase font-semibold tracking-wider`, Value `90.3%` in `text-[15px] font-mono font-bold text-[#2ecc71] tabular-nums`.
   - **Metric 2 (Turnover):** Label `TURNOVER` in `text-[10px] font-mono text-outline uppercase font-semibold tracking-wider`, Value `₹ 5.82Cr` in `text-[15px] font-mono font-bold text-on-surface tabular-nums`.
4. **Remove `arrow_drop_down`:** Eliminate the inert chevron icon completely.

### B. Header & "Live Scanning" Space Optimization (`dash_pages/dashboard.py:274-295`)
- Instead of a standalone full-width pill that pushes the content down by 52px, integrate the live scanning badge into the main header row alongside the "Pro Spike" logo:
  - `html.Div(className="flex items-center justify-between mb-4", children=[TitleBlock, CompactLiveChip])`.
  - Reduce vertical margin from `mb-8` to `mb-4`.

### C. Signals Header & Counter Calibration (`dash_pages/dashboard.py:310-341`)
- Reduce the counter font size on mobile from `text-[64px]` down to `text-[36px] sm:text-[48px]`.
- Group the number and label cleanly: `Span("2", className="text-[36px] font-bold text-primary font-mono")` + `Span("SIGNALS TODAY", className="text-xs font-mono font-bold text-outline")`.
- Align `Hide T2T` toggle cleanly on the right with a dedicated `44×44px` touch container.

---

## 5. Quick Wins
1. **Un-hide Close Price & Delivery % on Mobile:** Decouple `CLOSE` from the desktop sparkline div and remove `hidden sm:flex` from `DELIVERY %` so the card actually provides actionable trading data.
2. **Eliminate Inert `arrow_drop_down` Icon:** Delete line 231 to stop promising a non-existent expansion interaction.
3. **Consolidate Header Tags into a Single Line:** Put `Symbol + Exchange + Class` on the same horizontal row with `Price` on the right, instantly killing the 4-tier vertical stair-step and reducing card height by 35%.

---

## 6. Theme Note
- The dark mode foundation (`#10141a` background, `#1d212a` container, `#5af0b3` emerald accent) is cybernetic, cohesive, and easy on the eyes during prolonged market hours.
- Veto badges currently use `#e74c3c/20` with a slightly muddy `#ff6b6b` text. Using a crisper crimson `#f43f5e` with `rgba(244, 63, 94, 0.12)` background will improve contrast while fitting the modern 2026 dark fintech aesthetic.
- A light mode is not recommended; professional quantitative terminals perform best in calibrated dark mode.

---

## 7. Report Saved
- Saved report to: `design-audits/design-audit-2026-10-02-dashboard-cards.md`
- Referenced visual artifacts: `mobile_dashboard_390.png`, `mobile_dashboard_signals_crop.png`.

---

## 8. No Code Changes
*Per the `fz-uidesigner` audit protocol, no application code or stylesheet has been modified. All fixes outlined above are design recommendations.*
