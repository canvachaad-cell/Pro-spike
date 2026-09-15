const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.describe('Automated UI/UX and Accessibility Audit - Mobile Inst Signals', () => {
  test('Audit Institutional Signals 4 Tabs', async ({ page }) => {
    // Navigate to the local Dash app institutional signals page
    await page.goto('/institutional-signals');
    await page.waitForSelector('#engine-tab-content', { state: 'visible' });
    await page.waitForTimeout(1500); // Wait for initial render and callbacks

    const tabs = [
      { name: 'Legacy Screener', text: 'Legacy Screener' },
      { name: 'SBIA Alpha Engine', text: 'SBIA Alpha Engine' },
      { name: 'SBIA FlexGate Engine', text: 'SBIA FlexGate Engine' },
      { name: 'FlexGate 2.0', text: 'FlexGate 2.0' }
    ];

    console.log(`\n=== Running Axe-Core Mobile Audit on: ${page.url()} ===\n`);

    for (const tab of tabs) {
      console.log(`\n--- Auditing Tab: ${tab.name} ---`);
      
      // Click the tab if it's not the first one
      if (tab.name !== 'Legacy Screener') {
        // Dash tabs usually contain the text
        await page.locator(`text=${tab.text}`).click();
        await page.waitForTimeout(2000); // let the dash callback finish rendering
      }

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
        .analyze();

      if (results.violations.length > 0) {
        console.log(`Found ${results.violations.length} violations for ${tab.name}:`);
        results.violations.forEach(v => {
          console.log(`- [${v.id}] ${v.help} (Impact: ${v.impact})`);
          v.nodes.forEach(n => console.log(`    -> Target: ${n.target}`));
        });
      } else {
        console.log(`✅ ZERO violations found for ${tab.name}!`);
      }
    }
    console.log('\n=== Audit Complete ===\n');
  });
});
