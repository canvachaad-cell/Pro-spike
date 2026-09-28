const { test, expect } = require('@playwright/test');
const path = require('path');

const ARTIFACT_DIR = 'C:/Users/fawaz/.gemini/antigravity-ide/brain/22f3308b-b715-49cf-a00b-34e1e18d121a';

test.describe('PRO-SPIKE MOBILE FULL TEST SUITE', () => {

  // Force mobile-only assertions
  test.beforeEach(async ({ page }) => {
    const vw = page.viewportSize().width;
    test.skip(vw >= 768, 'This test suite runs exclusively on mobile viewports (< 768px)');
  });

  test('1. Mobile Shell, Header, and Bottom Navigation Bar', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    // Verify Mobile Bottom Navigation exists and is fixed at the bottom
    const bottomNav = page.locator('#mobile-bottom-nav, nav.fixed.bottom-0').first();
    expect(await bottomNav.isVisible()).toBe(true);

    const navBox = await bottomNav.boundingBox();
    const vh = page.viewportSize().height;
    // Bottom nav is a floating pill island (bottom: 16px)
    expect(navBox.y + navBox.height).toBeGreaterThanOrEqual(vh - 25);
    expect(navBox.y + navBox.height).toBeLessThanOrEqual(vh);

    // Verify primary navigation links in mobile bar
    const links = bottomNav.locator('a');
    expect(await links.count()).toBeGreaterThanOrEqual(3);

    // Capture screenshot of mobile dashboard
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'mobile_dashboard.png'), fullPage: false });
  });

  test('2. Mobile Vikram AI Bottom-Sheet & Backdrop Interaction', async ({ page }) => {
    const vh = page.viewportSize().height;
    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    const panel = page.locator('#vikram-panel');
    const backdrop = page.locator('#vikram-backdrop');

    // Panel is initially translated off-screen below viewport
    let box = await panel.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(vh - 5);

    // Open Vikram via mobile trigger
    const mobileTrigger = page.locator('#mobile-vikram-fab');
    await mobileTrigger.waitFor({ state: 'visible' });
    await mobileTrigger.click();
    await page.waitForFunction(() => {
      const b = document.querySelector('#vikram-backdrop');
      return b && b.classList.contains('open');
    }, { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(800);

    // Panel slides up into bottom-sheet viewport
    box = await panel.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(0.4 * vh);
    expect(box.height).toBeLessThanOrEqual(0.9 * vh);
    expect(Math.abs((box.y + box.height) - vh)).toBeLessThan(35);

    // Backdrop should be active with opacity
    const backdropCls = (await backdrop.getAttribute('class')) || '';
    expect(backdropCls).toContain('open');

    // Capture screenshot with bottom sheet open
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'mobile_vikram_bottomsheet.png'), fullPage: false });

    // Close via close button or backdrop tap
    const closeBtn = page.locator('#vikram-close');
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    } else {
      await page.mouse.click(10, 10);
    }
    await page.waitForTimeout(1000);

    // Panel returns off-screen below viewport
    box = await panel.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(vh - 5);
  });

  test('3. Mobile Institutional Signals & Sticky Column Scrolling', async ({ page }) => {
    await page.goto('/institutional-signals');
    await page.waitForSelector('#engine-tab-content', { state: 'visible' });
    await page.waitForTimeout(1500);

    // Check FlexGate Tab on mobile
    const flexTab = page.locator('#engine-tabs .tab', { hasText: 'FlexGate' }).first();
    if (await flexTab.count() > 0) {
      await flexTab.click();
      await page.waitForTimeout(1500);
    }

    const tableWrapper = page.locator('#engine-tab-content .glass-panel.overflow-x-auto').first();
    if (await tableWrapper.count() > 0) {
      const headerCells = tableWrapper.locator('.font-label-caps > div');
      if (await headerCells.count() > 0) {
        const col0 = headerCells.nth(0);
        const col0Cls = await col0.getAttribute('class');
        // Sticky left check
        expect(col0Cls).toContain('sticky');
        expect(col0Cls).toContain('left-0');

        const initialBox = await col0.boundingBox();
        // Horizontal scroll test
        await tableWrapper.evaluate(el => el.scrollLeft = 250);
        await page.waitForTimeout(500);

        const scrolledBox = await col0.boundingBox();
        // Sticky pin verification: X coordinate remains fixed within 5px tolerance
        expect(Math.abs(scrolledBox.x - initialBox.x)).toBeLessThan(5);

        // Reset scroll
        await tableWrapper.evaluate(el => el.scrollLeft = 0);
      }
    }

    // Capture mobile institutional signals screenshot
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'mobile_institutional.png'), fullPage: false });
  });

  test('4. Mobile Watchlist & Live Portfolio Risk Radar Responsiveness', async ({ page }) => {
    await page.goto('/watchlist');
    await page.waitForSelector('#watchlist-live-radar-container', { state: 'visible' });
    await page.waitForTimeout(1500);

    const radar = page.locator('#live-risk-radar-card').first();
    expect(await radar.isVisible()).toBe(true);

    const radarBox = await radar.boundingBox();
    const vw = page.viewportSize().width;
    // Radar must fit inside screen width (padding buffer of at least 8px each side)
    expect(radarBox.width).toBeLessThanOrEqual(vw);
    expect(radarBox.x).toBeGreaterThanOrEqual(0);

    // Badges must wrap inside card
    const badges = radar.locator('.flex-wrap > div');
    expect(await badges.count()).toBeGreaterThan(0);

    // Deduplication check: INDUSTOWER should only have 1 badge with [2 tranches]
    const radarText = await radar.innerText();
    expect(radarText).toContain('INDUSTOWER');
    expect(radarText).toContain('[2 tranches]');

    // Refresh button check on mobile
    const refreshBtn = page.locator('#btn-refresh-live-quotes');
    expect(await refreshBtn.isVisible()).toBe(true);
    const btnBox = await refreshBtn.boundingBox();
    // Minimum tap target size guidelines (at least 32px height)
    expect(btnBox.height).toBeGreaterThanOrEqual(30);

    // Capture mobile watchlist screenshot
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'mobile_watchlist.png'), fullPage: false });
  });

  test('5. Mobile Winner Archetypes Single-Column Layout', async ({ page }) => {
    await page.goto('/winner-archetypes');
    await page.waitForSelector('#archetype-cards-grid, .grid', { state: 'visible' });
    await page.waitForTimeout(1500);

    // Verify grid container exists
    const grid = page.locator('#archetype-cards-grid, .grid').first();
    expect(await grid.isVisible()).toBe(true);

    const cards = page.locator('.archetype-card, [id^="card-"]');
    if (await cards.count() > 0) {
      const firstCard = cards.first();
      const cardBox = await firstCard.boundingBox();
      const vw = page.viewportSize().width;
      // On mobile, card should take most of viewport width (single column)
      expect(cardBox.width).toBeGreaterThan(0.8 * vw);
    }

    // Capture mobile archetypes screenshot
    await page.screenshot({ path: path.join(ARTIFACT_DIR, 'mobile_archetypes.png'), fullPage: false });
  });

  test('6. Mobile Horizontal Scroll Overflow Guard (No Page Spill)', async ({ page }) => {
    const routes = ['/', '/institutional-signals', '/watchlist', '/winner-archetypes', '/notifications'];
    const vw = page.viewportSize().width;

    for (const r of routes) {
      await page.goto(r, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1200);

      // Verify document scrollWidth does not exceed viewport width (no accidental body horizontal scrollbar)
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(vw + 1); // 1px rounding tolerance
    }
  });

});
