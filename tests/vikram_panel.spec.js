const { test, expect } = require('@playwright/test');

test.describe('BUG-032 Vikram mobile bottom-sheet + backdrop', () => {
  test('mobile: bottom-sheet geometry, backdrop open/close', async ({ page }) => {
    const vw = page.viewportSize().width;
    const vh = page.viewportSize().height;
    test.skip(vw >= 768, 'mobile-only assertions');

    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    const panel = page.locator('#vikram-panel');
    const backdrop = page.locator('#vikram-backdrop');

    let box = await panel.boundingBox();
    expect(Math.abs(box.y - vh)).toBeLessThan(30);

    await page.locator('#mobile-vikram-tab').click();
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(box.height).toBeLessThanOrEqual(0.85 * vh);
    expect(box.height).toBeGreaterThanOrEqual(0.5 * vh);
    expect(Math.abs((box.y + box.height) - vh)).toBeLessThan(30);
    const cls = (await backdrop.getAttribute('class')) || '';
    expect(cls).toContain('open');
    const op = parseFloat(await backdrop.evaluate((el) => getComputedStyle(el).opacity));
    expect(op).toBeGreaterThan(0.9);

    await page.mouse.click(10, 10);
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(Math.abs(box.y - vh)).toBeLessThan(30);
    const cls2 = (await backdrop.getAttribute('class')) || '';
    expect(cls2).not.toContain('open');
  });

  test('desktop: 400px right sheet preserved', async ({ page }) => {
    const vw = page.viewportSize().width;
    test.skip(vw < 768, 'desktop-only assertions');

    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    const panel = page.locator('#vikram-panel');
    let box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(vw - 2);

    await page.locator('#vikram-trigger').click();
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(box.width).toBe(400);
    expect(Math.abs(box.x - (vw - 400))).toBeLessThan(5);

    await page.locator('#vikram-close').click();
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(vw - 2);
  });

  test('desktop: Cmd+K / Ctrl+K keyboard shortcut opens panel and Escape closes it', async ({ page }) => {
    const vw = page.viewportSize().width;
    test.skip(vw < 768, 'desktop-only assertions');

    await page.goto('/');
    await page.waitForSelector('#main-layout', { state: 'visible' });
    await page.waitForTimeout(1000);

    const panel = page.locator('#vikram-panel');
    let box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(vw - 2);

    // Press Control+k (or Meta+k)
    await page.keyboard.press('Control+k');
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(box.width).toBe(400);
    expect(Math.abs(box.x - (vw - 400))).toBeLessThan(5);

    // Press Escape to dismiss
    await page.keyboard.press('Escape');
    await page.waitForTimeout(1200);
    box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(vw - 2);
  });
});
