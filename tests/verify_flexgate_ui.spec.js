const { test, expect } = require('@playwright/test');

test('Verify MOTHERSON and active trades on FlexGate Tab 3', async ({ page }) => {
  await page.goto('http://127.0.0.1:8050/institutional-signals');
  await page.waitForSelector('#engine-tab-content', { state: 'visible' });
  await page.waitForTimeout(1500);

  // Click on the FlexGate tab
  await page.locator('#engine-tabs .tab', { hasText: 'FlexGate' }).first().click();
  await page.waitForTimeout(2500);

  // Take screenshot of the FlexGate table
  await page.screenshot({ path: 'scratch/flexgate_tab3_screenshot.png', fullPage: false });

  // Verify MOTHERSON is present
  const content = await page.content();
  console.log('Is MOTHERSON in page content?', content.includes('MOTHERSON'));
  console.log('Is BRGIL in page content?', content.includes('BRGIL'));
  console.log('Is SINTERCOM in page content?', content.includes('SINTERCOM'));
  console.log('Is PAGEIND in page content?', content.includes('PAGEIND'));

  expect(content.includes('MOTHERSON')).toBeTruthy();
  expect(content.includes('BRGIL')).toBeTruthy();
});
