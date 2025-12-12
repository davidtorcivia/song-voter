import { test, expect } from '@playwright/test';

test.describe('Vote Blocks', () => {
    test('clicking start voting button works', async ({ page }) => {
        // This test catches the bug we just fixed!

        // Visit a vote block page (assumes one exists from setup)
        await page.goto('/vote/block/test-block');

        // Click "Start Voting" button
        const startButton = page.locator('button:has-text("Start Voting")');
        await expect(startButton).toBeVisible();

        // This would have thrown "can't access property 'value', this.modeSelect is null"
        // before our fix
        await startButton.click();

        // Verify audio controls appeared
        await expect(page.locator('.audio-controls')).toBeVisible({ timeout: 5000 });
    });

    test('password-protected block shows auth page', async ({ page }) => {
        await page.goto('/vote/block/protected-block');

        // Should show password input
        await expect(page.locator('input[type="password"]')).toBeVisible();
    });

    test('can vote within a vote block', async ({ page }) => {
        await page.goto('/vote/block/test-block');

        // Start voting
        await page.click('button:has-text("Start Voting")');

        // Wait for audio controls
        await expect(page.locator('.audio-controls')).toBeVisible();

        // Set rating
        const ratingSlider = page.locator('input[type="range"]').first();
        await ratingSlider.fill('8');

        // Click thumbs up
        await page.click('button.thumb-up');

        // Submit vote
        await page.click('button:has-text("Submit")');

        // Should show next song or completion
        await expect(page.locator('.vote-status')).toBeVisible({ timeout: 5000 });
    });
});
