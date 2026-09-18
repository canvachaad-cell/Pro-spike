const { test, expect } = require('@playwright/test');

test.describe('Vikram Latency & Thinking Audit', () => {
  test('audit latency for multiple query archetypes', async ({ page }) => {
    test.setTimeout(180000);

    const logs = [];
    page.on('console', msg => logs.push(`[CONSOLE ${msg.type()}] ${msg.text()}`));
    page.on('pageerror', err => logs.push(`[PAGEERROR] ${err.message}`));

    console.log('Navigating to http://127.0.0.1:8050 ...');
    await page.goto('http://127.0.0.1:8050');
    await page.waitForSelector('#main-layout', { state: 'visible', timeout: 20000 });
    await page.waitForTimeout(1000);

    // Open panel
    await page.locator('#vikram-trigger').click();
    const panel = page.locator('#vikram-panel');
    await expect(panel).toBeVisible();
    await page.waitForTimeout(500);

    const input = page.locator('#vikram-input');
    const sendBtn = page.locator('#vikram-send');

    async function measureQuery(label, question) {
      console.log(`\n=== Testing: [${label}] "${question}" ===`);
      await input.fill(question);
      const t0 = Date.now();
      await sendBtn.click();

      // Wait for input to be disabled (ack)
      try {
        await expect(input).toBeDisabled({ timeout: 4000 });
        const ackTime = ((Date.now() - t0) / 1000).toFixed(2);
        console.log(`  -> Acknowledged in ${ackTime}s (loader visible, input disabled)`);
      } catch (e) {
        console.log(`  -> Warning: ack disable check timed out or was instantaneous`);
      }

      // Wait for input to be re-enabled (response arrived)
      await expect(input).toBeEnabled({ timeout: 90000 });
      const totalTime = ((Date.now() - t0) / 1000).toFixed(2);
      console.log(`  -> Response rendered in ${totalTime}s`);

      // Grab last model bubble
      const bubbles = page.locator('#vikram-chat .vikram-markdown');
      const count = await bubbles.count();
      if (count > 0) {
        const text = await bubbles.nth(count - 1).innerText();
        console.log(`  -> First 150 chars: ${text.replace(/\n/g, ' ').slice(0, 150)}...`);
      }
      return parseFloat(totalTime);
    }

    const t1 = await measureQuery('General Greeting', 'hi');
    await page.waitForTimeout(1500);

    const t2 = await measureQuery('Stock Analysis (Cached Veto)', 'STLNETWORK');
    await page.waitForTimeout(1500);

    const t3 = await measureQuery('Engine Audit', 'audit alpha leaks');
    await page.waitForTimeout(1500);

    console.log('\n========================================');
    console.log('LATENCY AUDIT SUMMARY:');
    console.log(`  1. General Greeting:     ${t1}s`);
    console.log(`  2. Stock Analysis:       ${t2}s`);
    console.log(`  3. Engine Audit:         ${t3}s`);
    console.log('========================================\n');

    await page.screenshot({ path: 'scratch/vikram_latency_audit.png', fullPage: true });
  });
});
