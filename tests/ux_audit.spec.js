const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.describe('Automated UI/UX and Accessibility Audit', () => {
  test('Audit Dashboard Layout and Constraints', async ({ page }) => {
    // Navigate to the local Dash app
    await page.goto('/');

    // Wait for the main Dash layout to render
    await page.waitForSelector('#main-layout', { state: 'visible' });
    
    // Give it a second for any Dash callback animations to settle
    await page.waitForTimeout(1000);

    console.log(`\n=== Running Axe-Core Audit on: ${page.url()} ===\n`);

    // Run the audit
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
      .analyze();

    if (results.violations.length > 0) {
      console.log(`Found ${results.violations.length} violations:`);
      results.violations.forEach(v => {
        console.log(`- [${v.id}] ${v.help} (Impact: ${v.impact})`);
        v.nodes.forEach(n => console.log(`    -> Target: ${n.target}`));
      });
    } else {
      console.log('✅ ZERO violations found! UI/UX and A11y are perfect.');
    }

    console.log('\n=== Audit Complete ===\n');
  });
});
