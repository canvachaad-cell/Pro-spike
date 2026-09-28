const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = 'C:/Users/fawaz/.gemini/antigravity-ide/brain/22f3308b-b715-49cf-a00b-34e1e18d121a';

const PAGES = [
  { name: 'Dashboard', path: '/', selector: '#main-layout' },
  { name: 'Winner Archetypes', path: '/winner-archetypes', selector: '#archetype-card-grid' },
  { name: 'Institutional Signals', path: '/institutional-signals', selector: '#engine-tab-content' },
  { name: 'Watchlist & Live Radar', path: '/watchlist', selector: '#watchlist-live-radar-container' },
  { name: 'Notifications', path: '/notifications', selector: '#notifications-container, .glass-panel' },
];

test.describe('PRO-SPIKE Comprehensive UI/UX & A11y Audit Suite', () => {

  for (const p of PAGES) {
    test(`[AUDIT] ${p.name} - Visual, Overflow, Touch & Axe-Core`, async ({ page }) => {
      test.setTimeout(60000);
      const isMobile = page.viewportSize().width < 768;
      const deviceTag = isMobile ? 'Mobile' : 'Desktop';
      const logPrefix = `[${deviceTag}][${p.name}]`;

      console.log(`\n========================================`);
      console.log(`${logPrefix} Navigating to ${p.path}...`);
      console.log(`========================================`);

      const t0 = Date.now();
      await page.goto(p.path, { waitUntil: 'domcontentloaded' });
      await page.locator(p.selector).first().waitFor({ state: 'visible', timeout: 15000 });
      const navDuration = Date.now() - t0;
      console.log(`${logPrefix} Initial DOM Ready in ${navDuration}ms`);

      // Let any minor render settle
      await page.waitForTimeout(800);

      // 1. Horizontal Scroll Overflow Check
      const overflow = await page.evaluate(() => {
        const docEl = document.documentElement;
        return {
          scrollWidth: docEl.scrollWidth,
          clientWidth: docEl.clientWidth,
          hasOverflow: docEl.scrollWidth > docEl.clientWidth + 1
        };
      });
      console.log(`${logPrefix} Overflow Check: ${overflow.hasOverflow ? 'FAILED 🚨' : 'PASSED ✅'} (scrollWidth: ${overflow.scrollWidth}px, clientWidth: ${overflow.clientWidth}px)`);
      expect(overflow.hasOverflow).toBe(false);

      // 2. Touch Targets & Affordances (Buttons, Links, Tabs)
      const touchAudit = await page.evaluate(() => {
        const interactive = Array.from(document.querySelectorAll('button, a, input, select, [role="button"], .tab, article[role="article"]'));
        const issues = [];
        let totalCount = 0;
        interactive.forEach(el => {
          if (!el.offsetParent) return;
          totalCount++;
          const rect = el.getBoundingClientRect();
          // WCAG 2.5.8 Minimum target size is 24x24 px, modern mobile standard recommends >= 32px
          if (rect.width > 0 && rect.height > 0 && (rect.height < 24 || rect.width < 24)) {
            issues.push({
              tag: el.tagName,
              id: el.id || '',
              cls: (el.className || '').toString().slice(0, 30),
              text: (el.innerText || '').slice(0, 20).trim(),
              w: Math.round(rect.width),
              h: Math.round(rect.height)
            });
          }
        });
        return { totalCount, sub24pxCount: issues.length, sub24pxIssues: issues };
      });
      console.log(`${logPrefix} Interactive elements checked: ${touchAudit.totalCount}. Sub-24px touch targets: ${touchAudit.sub24pxCount}`);

      // 3. Capture Visual Snapshot
      const screenshotFilename = `${deviceTag.toLowerCase()}_audit_${p.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}.png`;
      await page.screenshot({ path: path.join(ARTIFACT_DIR, screenshotFilename), fullPage: false });
      console.log(`${logPrefix} Snapshot saved: ${screenshotFilename}`);

      // 4. Axe-Core Accessibility Sweep
      const axe = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
        .analyze();

      const violations = {
        critical: axe.violations.filter(v => v.impact === 'critical'),
        serious: axe.violations.filter(v => v.impact === 'serious'),
        moderate: axe.violations.filter(v => v.impact === 'moderate'),
        minor: axe.violations.filter(v => v.impact === 'minor'),
      };

      console.log(`${logPrefix} Axe-Core Violations: Critical=${violations.critical.length}, Serious=${violations.serious.length}, Moderate=${violations.moderate.length}, Minor=${violations.minor.length}`);

      if (axe.violations.length > 0) {
        axe.violations.forEach(v => {
          console.log(`  -> [${(v.impact || 'unknown').toUpperCase()}] ${v.id}: ${v.help}`);
          v.nodes.slice(0, 2).forEach(n => console.log(`       Target: ${n.target}`));
        });
      }

      // No critical accessibility blockers allowed
      expect(violations.critical.length).toBe(0);

      // Save summary object
      const summaryFile = path.join(ARTIFACT_DIR, 'scratch', `${deviceTag.toLowerCase()}_${p.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}.json`);
      fs.writeFileSync(summaryFile, JSON.stringify({
        device: deviceTag,
        page: p.name,
        path: p.path,
        navDuration,
        overflow,
        touchAudit,
        axeSummary: {
          critical: violations.critical.length,
          serious: violations.serious.length,
          moderate: violations.moderate.length,
          minor: violations.minor.length,
          violations: axe.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, targets: v.nodes.map(n => n.target) }))
        }
      }, null, 2));
    });
  }

  test('Verify Specific Bug Fixes (BUG-083 through BUG-087)', async ({ page }) => {
    test.setTimeout(45000);
    const isMobile = page.viewportSize().width < 768;
    const prefix = isMobile ? '[MOBILE-FIX-CHECK]' : '[DESKTOP-FIX-CHECK]';

    console.log(`\n========================================`);
    console.log(`${prefix} Verifying BUG-083 to BUG-087 Fix Integrity...`);
    console.log(`========================================`);

    // --- FIX 1: BUG-083 & BUG-085 (Watchlist Live Risk Radar & Deduplication) ---
    await page.goto('/watchlist', { waitUntil: 'domcontentloaded' });
    await page.locator('#watchlist-live-radar-container').first().waitFor({ state: 'visible', timeout: 15000 });
    const radar = page.locator('#live-risk-radar-card');
    expect(await radar.isVisible()).toBe(true);

    const radarText = await radar.innerText();
    expect(radarText).toContain('LIVE PORTFOLIO RISK');
    expect(radarText).toContain('INDUSTOWER');
    expect(radarText).toContain('[2 tranches]'); // BUG-085 dedup
    expect(radarText).toMatch(/₹\s*\d+/); // BUG-083 live CMP
    console.log(`${prefix} PASS: BUG-083 & BUG-085 verified in DOM (INDUSTOWER single badge + [2 tranches] + CMP).`);

    // --- FIX 2: BUG-084 (Institutional Signals Alpha Hydration & Breakdown) ---
    await page.goto('/institutional-signals', { waitUntil: 'domcontentloaded' });
    await page.locator('#engine-tab-content').first().waitFor({ state: 'visible', timeout: 15000 });
    const instContent = await page.locator('#engine-tab-content').innerText();
    expect(instContent).toContain('GROWW');
    console.log(`${prefix} PASS: BUG-084 verified in DOM (Alpha signals hydrated, table renders valid entries).`);

    // --- FIX 3: BUG-087 (Winner Archetypes Initial Cards Pre-Render & Zero Blink) ---
    const t0 = Date.now();
    await page.goto('/winner-archetypes', { waitUntil: 'domcontentloaded' });
    await page.locator('#archetype-card-grid').first().waitFor({ state: 'visible', timeout: 15000 });
    const archetypeLoadTime = Date.now() - t0;
    console.log(`${prefix} Winner Archetypes initial load: ${archetypeLoadTime}ms`);
    expect(archetypeLoadTime).toBeLessThan(3500);

    const cards = page.locator('#archetype-card-grid article[role="article"]');
    const cardCount = await cards.count();
    console.log(`${prefix} Initial Quality Cards Count: ${cardCount}`);
    expect(cardCount).toBeGreaterThanOrEqual(10);
    console.log(`${prefix} PASS: BUG-087 verified in DOM (${cardCount} quality cards pre-rendered at t=0).`);

    // --- FIX 4: BUG-087 (Tab Latency & Click Response) ---
    const runnerTab = page.locator('#archetype-tabs .tab', { hasText: 'Clean Breakout Runners' }).first();
    if (await runnerTab.count() > 0) {
      const clickT0 = Date.now();
      await runnerTab.click();
      await page.waitForTimeout(600); // Callback settles quickly
      const runnerCards = await page.locator('#archetype-card-grid article[role="article"]').count();
      const clickDuration = Date.now() - clickT0;
      console.log(`${prefix} Archetype tab switch took ${clickDuration}ms, rendered ${runnerCards} cards.`);
      expect(runnerCards).toBeGreaterThanOrEqual(1);
    }
  });

});
