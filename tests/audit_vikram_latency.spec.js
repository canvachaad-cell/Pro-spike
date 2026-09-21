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

    // Budget constants (seconds) — aligned with MAX_TOTAL_S=45 in _vikram_callback.py.
    // A general greeting should never need a screener.in fetch; expect fast.
    const BUDGET_GREETING_S  = 15;   // hi / hello — no fetch, no search
    const BUDGET_STOCK_S     = 50;   // Stock analysis — screener + possible model fallover
    const BUDGET_AUDIT_S     = 50;   // Engine audit — ledger read + model call
    // The UI must re-enable (loader gone) within this grace period regardless of content.
    const BUDGET_RECOVERY_S  = BUDGET_STOCK_S + 5;

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
      await expect(input).toBeEnabled({ timeout: BUDGET_RECOVERY_S * 1000 });
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

    // --- REAL ASSERTIONS (these must fail before the fix, pass after) ---
    console.log('\n========================================');
    console.log('LATENCY AUDIT — ENFORCED BUDGETS:');
    console.log(`  1. General Greeting:  ${t1}s  (budget: ${BUDGET_GREETING_S}s)`);
    console.log(`  2. Stock Analysis:    ${t2}s  (budget: ${BUDGET_STOCK_S}s)`);
    console.log(`  3. Engine Audit:      ${t3}s  (budget: ${BUDGET_AUDIT_S}s)`);
    console.log('========================================\n');

    expect(t1, `General greeting exceeded ${BUDGET_GREETING_S}s budget`).toBeLessThan(BUDGET_GREETING_S);
    expect(t2, `Stock analysis exceeded ${BUDGET_STOCK_S}s budget`).toBeLessThan(BUDGET_STOCK_S);
    expect(t3, `Engine audit exceeded ${BUDGET_AUDIT_S}s budget`).toBeLessThan(BUDGET_AUDIT_S);

    // Verify the input is re-enabled (loader is gone) — the most critical check.
    // toBeEnabled timeout matches our recovery budget.
    await expect(input, 'Vikram input must be re-enabled — UI must never permanently deadlock')
      .toBeEnabled({ timeout: BUDGET_RECOVERY_S * 1000 });

    // Verify that there is no active loader bubble still in the DOM.
    const loader = page.locator('.vikram-dots');
    await expect(loader, 'Vikram loader dots must be gone after response').toHaveCount(0);

    await page.screenshot({ path: 'scratch/vikram_latency_audit.png', fullPage: true });
  });
});
