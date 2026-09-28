const { test, expect } = require('@playwright/test');

test.describe('FULL_TEST End-to-End QA Suite', () => {

  test('1 & 7. Cross-Page Navigation & Sanity Sweep', async ({ page }) => {
    const consoleErrors = [];
    const pageErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', err => pageErrors.push(err.message));

    const routes = [
      { path: '/', expectedSelector: '#main-layout' },
      { path: '/institutional-signals', expectedSelector: '#engine-tab-content' },
      { path: '/watchlist', expectedSelector: '#watchlist-live-radar-container' },
      { path: '/winner-archetypes', expectedSelector: '#archetype-cards-grid, .grid' },
      { path: '/notifications', expectedSelector: '#notifications-container, .glass-panel' },
    ];

    for (const r of routes) {
      console.log(`Navigating to route: ${r.path}`);
      const resp = await page.goto(r.path, { waitUntil: 'domcontentloaded' });
      expect(resp.status()).toBe(200);
      await page.locator(r.expectedSelector).first().waitFor({ state: 'visible', timeout: 15000 });
      const isVisible = await page.locator(r.expectedSelector).first().isVisible();
      expect(isVisible).toBe(true);
    }

    // Filter out minor benign warnings
    const fatalErrors = pageErrors.filter(e => !e.includes('ResizeObserver') && !e.includes('favicon'));
    expect(fatalErrors.length).toBe(0);
  });

  test('2, 3 & 4. Institutional Signals & Data Integrity (FlexGate & Alpha)', async ({ page }) => {
    await page.goto('/institutional-signals');
    await page.waitForSelector('#engine-tab-content', { state: 'visible' });
    await page.waitForTimeout(1500);

    // 1. SBIA Alpha tab (default) - verify GROWW is present
    await page.locator('#engine-tab-content').getByText('GROWW').first().waitFor({ state: 'visible', timeout: 15000 });
    expect(await page.locator('#engine-tab-content').getByText('GROWW').count()).toBeGreaterThan(0);

    // 2. Switch to FlexGate Tab
    const flexTab = page.locator('#engine-tabs .tab', { hasText: 'FlexGate' }).first();
    await flexTab.scrollIntoViewIfNeeded();
    await flexTab.click();

    // Verify active trades are synced and rendered
    await page.locator('#engine-tab-content').getByText('MOTHERSON').first().waitFor({ state: 'visible', timeout: 15000 });
    expect(await page.locator('#engine-tab-content').getByText('MOTHERSON').count()).toBeGreaterThan(0);
    expect(await page.locator('#engine-tab-content').getByText('PAGEIND').count()).toBeGreaterThan(0);
    expect(await page.locator('#engine-tab-content').getByText('INDUSTOWER').count()).toBeGreaterThan(0);
  });

  test('4 & 8. Watchlist Live Risk Radar & Quote Refresh Contract', async ({ page }) => {
    await page.goto('/watchlist');
    await page.waitForSelector('#watchlist-live-radar-container', { state: 'visible' });
    await page.waitForTimeout(1500);

    const radarContent = await page.locator('#watchlist-live-radar-container').innerText();
    // Verify INDUSTOWER deduplication and multi-tranche badge
    expect(radarContent).toContain('INDUSTOWER');
    expect(radarContent).toContain('[2 tranches]');

    // Click Refresh Live Quotes button to verify Frontend-Backend contract
    const refreshBtn = page.locator('#btn-refresh-live-quotes');
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(2000);
      const refreshedContent = await page.locator('#watchlist-live-radar-container').innerText();
      expect(refreshedContent).toContain('LIVE PORTFOLIO RISK');
    }
  });

  test('5. Responsive Bounds (Mobile vs Desktop Layout)', async ({ page }) => {
    const vw = page.viewportSize().width;
    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });

    if (vw < 768) {
      // Mobile Viewport
      const mobileNav = page.locator('#mobile-bottom-nav, nav.fixed');
      expect(await mobileNav.first().isVisible()).toBe(true);
    } else {
      // Desktop Viewport
      const desktopSidebar = page.locator('aside, #desktop-sidebar, nav');
      expect(await desktopSidebar.first().isVisible()).toBe(true);
    }
  });

  test('6. Vikram AI Query Negative-Path Inputs', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    // Open Vikram panel
    const vw = page.viewportSize().width;
    if (vw < 768) {
      await page.locator('#mobile-vikram-fab, #mobile-vikram-tab').first().click();
    } else {
      await page.locator('#vikram-trigger').click();
    }
    await page.waitForTimeout(1000);

    const input = page.locator('#vikram-input');
    const sendBtn = page.locator('#vikram-send');

    if (await input.isVisible()) {
      // Test 1: Empty input
      await sendBtn.click();
      await page.waitForTimeout(500);

      // Test 2: Garbage/Special characters
      await input.fill('$$$###@@@%%%!!!');
      await sendBtn.click();
      await page.waitForTimeout(1500);

      // Confirm UI did not crash and input is still functional
      expect(await input.isVisible()).toBe(true);
    }
  });

});
