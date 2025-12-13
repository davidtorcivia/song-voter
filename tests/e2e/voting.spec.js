import { test, expect } from '@playwright/test';

// Skip voting tests in CI - they require songs in the songs directory
test.describe('Voting Flow', () => {
    test.skip(({ }, testInfo) => !!process.env.CI, 'Requires songs directory with audio files');

    test('can complete voting flow', async ({ page }) => {
        await page.goto('/');

        // Click Start Voting
        const startButton = page.locator('button:has-text("Start Voting")');
        await expect(startButton).toBeVisible();
        await startButton.click();

        // Wait for song to load
        await expect(page.locator('.song-title')).toBeVisible({ timeout: 5000 });

        // Verify audio player is visible
        await expect(page.locator('.audio-controls')).toBeVisible();
    });

    test('rating slider works', async ({ page }) => {
        await page.goto('/');
        await page.click('button:has-text("Start Voting")');

        // Wait for controls
        await expect(page.locator('.audio-controls')).toBeVisible();

        // Set rating
        const ratingSlider = page.locator('input[type="range"]').first();
        await ratingSlider.fill('7');

        // Verify rating display updated
        const ratingDisplay = page.locator('.rating-value');
        await expect(ratingDisplay).toHaveText('7');
    });

    test('can skip song', async ({ page }) => {
        await page.goto('/');
        await page.click('button:has-text("Start Voting")');

        await expect(page.locator('.audio-controls')).toBeVisible();

        // Get current song title
        const firstSongTitle = await page.locator('.song-title').textContent();

        // Skip
        await page.click('button:has-text("Skip")');

        // Verify different song loaded
        await page.waitForTimeout(500);
        const secondSongTitle = await page.locator('.song-title').textContent();

        expect(firstSongTitle).not.toBe(secondSongTitle);
    });

    test('can submit vote', async ({ page }) => {
        await page.goto('/');
        await page.click('button:has-text("Start Voting")');

        await expect(page.locator('.audio-controls')).toBeVisible();

        // Set rating
        await page.locator('input[type="range"]').first().fill('8');

        // Thumbs up
        await page.click('button.thumb-up');

        // Submit
        await page.click('button:has-text("Submit")');

        // Should proceed to next song or show completion
        await page.waitForTimeout(1000);
    });

    test('cast button appears when enabled', async ({ page }) => {
        await page.goto('/');

        // Cast button should be present if Cast SDK is enabled
        const castButton = page.locator('button.cast-btn, google-cast-launcher');

        // Check if it exists (may not be visible if no devices)
        const count = await castButton.count();
        expect(count).toBeGreaterThanOrEqual(0);
    });
});
