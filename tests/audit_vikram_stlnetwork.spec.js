const { test, expect } = require('@playwright/test');

test.describe('Audit Vikram Fundamental Quality Gate for STLNETWORK', () => {
  test('Vikram responds with verified fundamentals instead of timeout', async ({ page }) => {
    test.setTimeout(120000);
    
    // 1. Navigate to localhost
    await page.goto('http://127.0.0.1:8050');
    await page.waitForSelector('#main-layout', { state: 'visible', timeout: 20000 });
    await page.waitForTimeout(1500);

    // 2. Open Vikram Panel
    const vw = page.viewportSize().width;
    if (vw < 768) {
      await page.locator('#mobile-vikram-fab, #mobile-vikram-tab').first().click();
    } else {
      await page.locator('#vikram-trigger').click();
    }
    
    const panel = page.locator('#vikram-panel');
    await expect(panel).toBeVisible();
    await page.waitForTimeout(500);

    // 3. Type question into vikram-input
    const input = page.locator('#vikram-input');
    await expect(input).toBeVisible();
    await input.fill('Analyze STLNETWORK');

    // 4. Click send
    const sendBtn = page.locator('#vikram-send');
    await sendBtn.click();

    // 5. Wait for the user bubble to appear (ack)
    console.log('Waiting for query acknowledgment...');
    await expect(page.locator('#vikram-chat')).toContainText('Analyze STLNETWORK', { timeout: 10000 });
    console.log('Query acknowledged, input disabled while Vikram thinks...');

    // 6. Now wait for the input to be re-enabled (meaning resolve_message completed)
    console.log('Waiting for Vikram response (screener + gemini)...');
    await expect(input).toBeEnabled({ timeout: 90000 });
    console.log('Vikram response arrived!');

    // 7. Inspect chat content
    const chat = page.locator('#vikram-chat');
    const chatText = await chat.innerText();
    console.log('--- Vikram Response Preview ---');
    console.log(chatText.slice(-1200));
    console.log('-------------------------------');

    // 8. Assertions:
    expect(chatText).toContain('STLNETWORK');
    expect(chatText).toContain('Fundamental Quality Gate');
    
    // Verify live fundamental timeout did NOT happen
    expect(chatText).not.toContain('Because live fundamental data feeds timed out');
    
    // Verify veto and key metrics are populated
    const hasVeto = chatText.includes('VETO') || chatText.includes('🚫');
    expect(hasVeto).toBeTruthy();

    const hasMetrics = chatText.includes('FCF') || chatText.includes('1,999') || chatText.includes('0.35');
    expect(hasMetrics).toBeTruthy();

    // 9. Screenshot
    await page.screenshot({ path: 'scratch/vikram_stlnetwork_audit.png', fullPage: true });
    console.log('Screenshot saved to scratch/vikram_stlnetwork_audit.png');
  });
});
