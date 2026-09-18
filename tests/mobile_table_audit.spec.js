const { test, expect } = require('@playwright/test');

test.describe('Mobile View QA - Institutional Signals Table', () => {
  test('Verify Mobile Sticky Symbol & Column Order across Tabs', async ({ page }) => {
    // Navigate to local Dash app institutional signals page
    await page.goto('/institutional-signals');
    await page.waitForSelector('#engine-tab-content', { state: 'visible' });
    await page.waitForTimeout(2000);

    const tabs = [
      { name: 'Legacy', expectedCol0: 'SYMBOL', expectedCol1: 'AI_SCORE' },
      { name: 'SBIA Alpha', expectedCol0: 'SYMBOL', expectedCol1: 'AI_WIN_PROBABILITY' },
      { name: 'FlexGate', expectedCol0: 'SYMBOL', expectedCol1: 'AI_STATUS' },
      { name: 'FlexGate 2.0', expectedCol0: 'SYMBOL', expectedCol1: 'AI_STATUS' },
    ];

    for (const tab of tabs) {
      console.log(`\nTesting tab: ${tab.name}`);
      if (tab.name !== 'Legacy') {
        const tabLocator = page.locator('#engine-tabs .tab', { hasText: tab.name }).first();
        if (await tabLocator.count() > 0) {
          await tabLocator.click();
          await page.waitForTimeout(2000);
        }
      }

      // Check if table exists in active tab
      const tableWrapper = page.locator('#engine-tab-content .glass-panel.overflow-x-auto').first();
      if (await tableWrapper.count() === 0) {
        console.log(`  No table present (empty state) for ${tab.name}`);
        continue;
      }

      // 1. Verify Header Column 0 & Column 1
      const headerCells = tableWrapper.locator('.font-label-caps > div');
      const count = await headerCells.count();
      if (count > 0) {
        const col0Text = (await headerCells.nth(0).innerText()).trim();
        const col1Text = count > 1 ? (await headerCells.nth(1).innerText()).trim() : '';
        console.log(`  Header Col 0: "${col0Text}", Col 1: "${col1Text}"`);

        expect(col0Text).toBe(tab.expectedCol0);
        if (tab.expectedCol1) {
          expect(col1Text).toBe(tab.expectedCol1);
        }

        // 2. Verify Col 0 is sticky with left 0 and dark background
        const col0Classes = await headerCells.nth(0).getAttribute('class');
        expect(col0Classes).toContain('sticky');
        expect(col0Classes).toContain('left-0');
        expect(col0Classes).toContain('bg-[#0a0a0a]');

        // 3. Test horizontal scroll on mobile viewport
        const initialBox = await headerCells.nth(0).boundingBox();
        console.log(`  Initial Col 0 Bounding Box: x=${initialBox.x}`);

        // Scroll the table wrapper horizontally to the right
        await tableWrapper.evaluate(el => el.scrollLeft = 300);
        await page.waitForTimeout(500);

        const scrolledBox = await headerCells.nth(0).boundingBox();
        console.log(`  Scrolled Col 0 Bounding Box: x=${scrolledBox.x}`);
        // col 0 bounding box x should remain virtually identical because it is sticky left-0!
        expect(Math.abs(scrolledBox.x - initialBox.x)).toBeLessThan(5);

        // Reset scroll
        await tableWrapper.evaluate(el => el.scrollLeft = 0);
      }
    }

    // Capture mobile screenshot
    await page.screenshot({ path: 'scratch_mobile_table.png', fullPage: false });
    console.log('\n✅ Mobile View Table QA Test Passed Successfully!');
  });
});
