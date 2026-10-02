# UI/UX Design Audit — Trading Dashboard & Institutional Signals

**Date:** 2026-10-02  
**Auditor:** `fz-uidesigner` (Senior Product Designer & Design Director)  
**Target Routes:** Dashboard (`/`), Institutional Signals (`/institutional-signals` — all 4 engine tabs: SBIA Alpha, FlexGate, FlexGate 2.0, Corner Spike), and Global Mobile Shell (`dash_app_v2.py`).  
**Viewports Evaluated:** Mobile (390×844), Tablet (768×1024), Desktop (1440×900).  

---

## 1. First Impression
On desktop, Pro Spike delivers a striking, cybernetic quantitative trading experience with a confident high-contrast dark palette and well-structured bento panels. On mobile (390px), however, the interface deteriorates into a claustrophobic squeeze where desktop-density data tables and microscopic text (`8px`–`10px`) fight against thumbs, safe-area home indicators, and viewport letterboxing.

---

## 2. Scores

| Area | Mobile | Desktop |
| :--- | :--- | :--- |
| **Whitespace** | 3 / 10 | 8 / 10 |
| **Hierarchy** | 5 / 10 | 8 / 10 |
| **Color** | 7 / 10 | 8 / 10 |
| **Typography** | 2 / 10 | 7 / 10 |
| **Buttons & Controls** | 4 / 10 | 7 / 10 |
| **Element Placement** | 5 / 10 | 8 / 10 |
| **Consistency** | 5 / 10 | 7 / 10 |
| **Modernity** | 5 / 10 | 8 / 10 |

---

## 3. Issues — Ranked by Severity

### 🔴 High

1. **Micro-Typography Squint-Zone (`< 12px`)**
   - **Severity:** High
   - **What is wrong:** Pervasive reliance on sub-12px micro-fonts (`text-[8px]`, `text-[9px]`, `text-[10px]`, and `font-size: 8.5px`) across navigation, tables, and signal cards.
   - **Where it is:** `assets/style.css:207` (`.mobile-nav-item`), `dash_pages/dashboard.py:116, 123, 136, 188, 198, 220, 227`, `dash_pages/institutional_signals.py:121, 486, 827`, and `dash_pages/winner_archetypes.py:404, 411, 418`.
   - **Which version:** Mobile (and Desktop table headers)
   - **Why it feels off:** Body text under 14px and badge text under 11px violate accessibility standards and look like microscopic printing defects on OLED screens.

2. **Safe-Area Violation & Home Indicator Collision**
   - **Severity:** High
   - **What is wrong:** Fixed floating bottom navigation bar lacks `env(safe-area-inset-bottom)` anchoring.
   - **Where it is:** `assets/style.css:167-195` (`.mobile-bottom-nav`, `.page-content-mobile-pad`).
   - **Which version:** Mobile
   - **Why it feels off:** Navigation icons and text physically collide with the iOS home indicator bar and Android gesture pill, causing accidental app switching instead of tab navigation.

3. **Sub-44px Touch Targets ("Tap Anxiety")**
   - **Severity:** High
   - **What is wrong:** Multiple interactive controls, modal close buttons, and filter toggles have touch bounding boxes far below the 44×44px accessibility threshold.
   - **Where it is:** `dash_app_v2.py:310, 336` (`mobile-drawer-toggle` is 40×40px; `mobile-drawer-close` is 32×32px), `dash_pages/dashboard.py:331` (`#toggle` T2T hit container).
   - **Which version:** Mobile
   - **Why it feels off:** Forces users to carefully aim the tip of their thumb, creating friction and missed taps.

4. **1650px Desktop Table Sprawl on 390px Viewport**
   - **Severity:** High
   - **What is wrong:** All 4 Institutional Signals tabs (SBIA Alpha, FlexGate, FlexGate 2.0, Corner Spike) render 12–14 column desktop grids with `min_width=1140px` to `1650px` without mobile column prioritization or stacked card fallbacks.
   - **Where it is:** `dash_pages/institutional_signals.py:260, 387, 890, 1014` (`_grid_table`).
   - **Which version:** Mobile
   - **Why it feels off:** Users must drag horizontally across 1200px of screen space to read essential execution numbers (SL, TP, and Buy Thesis) that should be visible immediately.

5. **Fixed Chrome Squeeze / Viewport Letterboxing**
   - **Severity:** High
   - **What is wrong:** Sticky `h-14` (56px) top header combined with fixed `60px` floating bottom bar and sticky tab headers consumes over 160px of vertical space (> 20% of 844px height).
   - **Where it is:** `dash_app_v2.py:294, 288`, `dash_pages/institutional_signals.py:1110`.
   - **Which version:** Mobile
   - **Why it feels off:** Squeezes the scrollable reading area into an uncomfortable horizontal slot, making scanning data tables feel claustrophobic.

---

### 🟡 Medium

6. **Numeric Data Left-Alignment in Trading Tables**
   - **Severity:** Medium
   - **What is wrong:** Quantitative figures (entry price, stop loss, take profit, turnover, ATR%) in table rows are left-aligned instead of right-aligned with fixed-width figures.
   - **Where it is:** `dash_pages/institutional_signals.py:371-381, 453-456, 994-1006`.
   - **Which version:** Both
   - **Why it feels off:** In financial interfaces, left-aligned numbers prevent visual vertical alignment of decimal places, making comparative scanning visually ragged.

7. **Clashing Green Color Semantics**
   - **Severity:** Medium
   - **What is wrong:** Two competing shades of green represent positive gains: primary neon mint `#5af0b3` and standard emerald `#2ecc71` / `text-emerald-300`.
   - **Where it is:** `dash_pages/institutional_signals.py:353, 391, 941, 967`, `dash_pages/dashboard.py:128`.
   - **Which version:** Both
   - **Why it feels off:** Dual green hues create chromatic friction and muddy the distinction between brand accents and profit status.

8. **Drawer Internal Gutters Under-Padded (Mandatory Drawer Check)**
   - **Severity:** Medium
   - **What is wrong:** The mobile navigation drawer uses `p-5` (20px), falling short of the required `24px–32px` (`p-6 md:p-8`) internal breathing room.
   - **Where it is:** `dash_app_v2.py:320` (`#mobile-menu-drawer`).
   - **Which version:** Mobile
   - **Why it feels off:** Elements sit too close to the modal sheet perimeter rather than feeling comfortably inset.

9. **Outer Layout Padding Inflexibility**
   - **Severity:** Medium
   - **What is wrong:** Dashboard root container applies hardcoded `px-[24px]` on mobile, consuming 48px (over 12%) of a 390px screen purely on gutters.
   - **Where it is:** `dash_pages/dashboard.py:271`.
   - **Which version:** Mobile
   - **Why it feels off:** Steals critical horizontal room from cards and badges, forcing unnecessary multi-line text wraps.

10. **Details Summary Accordions Lack Clear Tap Envelope**
    - **Severity:** Medium
    - **What is wrong:** `<summary>` headers in strategy documentation accordions use `text-[11px]` with minimal vertical hit padding.
    - **Where it is:** `dash_pages/institutional_signals.py:1096, 481, 1033`.
    - **Which version:** Mobile
    - **Why it feels off:** Feels difficult to reliably target and toggle with one thumb on a moving train or handheld setting.

---

### 🟢 Low

11. **Sparkline Chart Completely Omitted on Mobile**
    - **Severity:** Low
    - **What is wrong:** 5-bar sparklines on signal cards are hidden (`hidden md:flex`) on mobile rather than adapted as compact inline mini-indicators.
    - **Where it is:** `dash_pages/dashboard.py:196`.
    - **Which version:** Mobile
    - **Why it feels off:** Mobile users lose immediate visual momentum context and must read raw numbers.

12. **Subtle Elevation Inconsistency Across Pages**
    - **Severity:** Low
    - **What is wrong:** Signal cards on Dashboard lift with shadow on hover (`-translate-y-1 hover:shadow-lg`), while table rows on Institutional Signals only change background tint (`hover:bg-white/5`).
    - **Where it is:** `dash_pages/dashboard.py:178` vs `dash_pages/institutional_signals.py:142`.
    - **Which version:** Desktop
    - **Why it feels off:** Inconsistent interaction texture across adjacent screens in the same product suite.

13. **LIVE Status Badge Typographic Fragmentation**
    - **Severity:** Low
    - **What is wrong:** Mobile header "LIVE" pill uses `text-[9px]`, while the dashboard status pill uses `text-[12px]`.
    - **Where it is:** `dash_app_v2.py:303` vs `dash_pages/dashboard.py:291`.
    - **Which version:** Both
    - **Why it feels off:** Minor inconsistency in uppercase system status indicator scales.

---

**Summary Count:** **5 High, 5 Medium, 3 Low** (Total: 13 issues)

---

## 4. Fixes

### Fix 1 (High): Eliminate Micro-Typography
- **Where:** `assets/style.css`, `dash_pages/dashboard.py`, `dash_pages/institutional_signals.py`.
- **Mobile Spec:**
  - `.mobile-nav-item`: Change `font-size` from `8.5px` to `11px` (`0.6875rem`), `font-weight: 600`.
  - Signal pills & badges: Change `text-[9px]` to `text-xs font-semibold` (`12px`) with `px-2 py-0.5` padding.
  - Table headers: Change `text-[10px]` to `text-xs font-bold font-mono tracking-wider` (`12px`).
- **Desktop Spec:** Table headers: `text-xs font-bold font-mono tracking-wider` (`12px`), row labels: `text-sm font-data-md` (`14px`).

### Fix 2 (High): Safe-Area Insets & Bottom Nav Ergonomics
- **Where:** `assets/style.css`.
- **Mobile Spec:**
  - `.mobile-bottom-nav`: Change `bottom: 12px; height: 60px;` to `bottom: calc(10px + env(safe-area-inset-bottom, 0px)); height: 64px; border-radius: 32px;`.
  - `.mobile-nav-item`: Add `min-height: 48px; gap: 3px; padding: 6px 2px;`.
  - `.page-content-mobile-pad`: Change `padding-bottom: 96px !important;` to `padding-bottom: calc(100px + env(safe-area-inset-bottom, 0px)) !important;`.
- **Desktop Spec:** No change (bottom nav hidden via `display: none`).

### Fix 3 (High): Enlarge Touch Targets to $\ge 44\text{px}$
- **Where:** `dash_app_v2.py`, `dash_pages/dashboard.py`.
- **Mobile Spec:**
  - `#mobile-drawer-toggle`: Change `w-10 h-10` to `w-11 h-11` (`44×44px`).
  - `#mobile-drawer-close`: Change `w-8 h-8` to `w-11 h-11` (`44×44px`) with `DashIconify(width=22, height=22)`.
  - `#toggle` (Hide T2T container): Wrap inside container with `min-h-[44px] min-w-[44px] flex items-center justify-end`.

### Fix 4 (High): Mobile Column Prioritization for 4 Engine Tables
- **Where:** `dash_pages/institutional_signals.py`.
- **Mobile Spec:**
  - In `_grid_table`, retain sticky frozen first column (`SYMBOL`) with opaque background `bg-[#0a0a0a]` and right shadow `shadow-[8px_0_12px_-8px_rgba(0,0,0,0.55)]`.
  - On viewports $< 768\text{px}$, adjust column width distribution so `SYMBOL` (`140px`), `CMP` (`125px`), and `SL_PROXIMITY` (`140px`) render seamlessly without horizontal clipping.
  - Add `-webkit-overflow-scrolling: touch; touch-action: pan-x;` to all table wrapper containers.

### Fix 5 (High): Reduce Fixed Chrome Height
- **Where:** `dash_app_v2.py`.
- **Mobile Spec:**
  - Keep `mobile_top_header` slim at `h-13` (52px).
  - Ensure sticky tab headers in Institutional Signals use compact `py-1.5` on mobile with `scroll-snap-type: x mandatory`.

### Fix 6 (Medium): Right-Align Numeric Financial Data
- **Where:** `dash_pages/institutional_signals.py`.
- **Spec (Both):**
  - Add `text-right font-mono tabular-nums` to columns: `CMP`, `ENTRY_PRICE`, `EXIT_PRICE`, `STOP_LOSS`, `TAKE_PROFIT`, `ATR14`, `TURNOVER`, `ATW`.
  - Header titles for numeric columns should align right accordingly.

### Fix 7 (Medium): Consolidate Profit / Positive Color Semantics
- **Where:** `dash_pages/institutional_signals.py`, `dash_pages/dashboard.py`.
- **Spec (Both):**
  - Establish `#5af0b3` (neon mint) exclusively as brand/system primary accent.
  - Establish `#2ecc71` (standard green) strictly for positive trade returns / PnL / TP hit badges across all screens.

### Fix 8 (Medium): Elevate Drawer Gutter Padding
- **Where:** `dash_app_v2.py`.
- **Mobile Spec:**
  - Change `#mobile-menu-drawer` className from `p-5` to `p-6 md:p-8` (24px padding on mobile, 32px on tablet).
  - Ensure bottom links have at least `16px` clearance from sheet boundary.

### Fix 9 (Medium): Responsive Layout Margin Gutters
- **Where:** `dash_pages/dashboard.py`.
- **Mobile Spec:** Replace `px-[24px] py-[24px]` with `px-3 sm:px-6 py-4 sm:py-6`.
- **Desktop Spec:** Retain `max-w-[1600px] mx-auto`.

### Fix 10 (Medium): Strategy Accordion Tap Envelope
- **Where:** `dash_pages/institutional_signals.py`.
- **Mobile Spec:**
  - Change `text-[11px]` to `text-xs font-semibold`.
  - Add `min-h-[44px] flex items-center px-4 py-2.5` to `<summary>`.

---

## 5. Quick Wins

1. **Mass Replace Micro-Fonts:** Upgrade all `text-[8px]`, `text-[9px]`, and `text-[10px]` classes to `text-xs` (12px) across cards, badges, and table headers.
2. **Safe-Area Inset Injection:** Add `bottom: calc(10px + env(safe-area-inset-bottom, 0px));` to `.mobile-bottom-nav` and dynamic padding to `.page-content-mobile-pad` in `assets/style.css`.
3. **Right-Align Numbers:** Add `text-right font-mono tabular-nums` to price and return columns in Institutional Signals to immediately establish institutional terminal polish.

---

## 6. Theme Note

The application employs an intentional, cybernetic dark theme utilizing high-contrast zinc/carbon backgrounds (`#0a0a0a`, `#0f1117`) and translucent glassmorphism (`backdrop-blur-xl`). 
- **Dark Theme Verdict:** Highly appropriate for an institutional quantitative trading product. Once optical bleeding on micro-fonts is resolved by font size expansion, the dark theme delivers high visual authority.
- **Light Theme Verdict:** Not currently implemented. A high-contrast light mode is not recommended at this stage because quantitative traders overwhelmingly prefer dark terminals for multi-hour market monitoring, and maintaining dual-theme color token parity across complex SVG sparklines and trading tables would dilute engineering focus.

---

## 7. No Code Changes

*In accordance with the `fz-uidesigner` audit protocol, this report presents visual design evaluations and concrete recommendations only. No production files or stylesheets were modified.*
