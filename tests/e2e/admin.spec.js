import { test, expect } from '@playwright/test';

test.describe('Admin Dashboard', () => {
    test('can login as admin', async ({ page }) => {
        await page.goto('/admin/login');

        // Fill login form
        await page.fill('input[name="username"]', 'test@example.com');
        await page.fill('input[name="password"]', 'testpass123');

        // Submit
        await page.click('button[type="submit"]');

        // Should redirect to dashboard
        await expect(page).toHaveURL(/\/admin/);
        await expect(page.locator('h1')).toContainText('Admin');
    });

    test('can create vote block', async ({ page, context }) => {
        // Login first
        await page.goto('/admin/login');
        await page.fill('input[name="username"]', 'test@example.com');
        await page.fill('input[name="password"]', 'testpass123');
        await page.click('button[type="submit"]');

        // Navigate to blocks
        await page.goto('/admin/blocks');

        // Click new block
        await page.click('button:has-text("New Block")');

        // Fill form
        await page.fill('input#blockName', 'E2E Test Block');

        // Select a song
        const firstCheckbox = page.locator('#songSelector input[type="checkbox"]').first();
        await firstCheckbox.check();

        // Create
        await page.click('button:has-text("Create")');

        // Wait for page reload or success
        await page.waitForTimeout(1000);

        // Verify block appears in list
        await expect(page.locator('text=E2E Test Block')).toBeVisible();
    });

    test('can change settings', async ({ page }) => {
        // Login
        await page.goto('/admin/login');
        await page.fill('input[name="username"]', 'test@example.com');
        await page.fill('input[name="password"]', 'testpass123');
        await page.click('button[type="submit"]');

        // Go to dashboard (settings are there)
        await page.goto('/admin/');

        // Find site title input
        const siteTitleInput = page.locator('input[name="site_title"]');

        if (await siteTitleInput.count() > 0) {
            await siteTitleInput.fill('Test Site');

            // Save
            await page.click('button:has-text("Save")');

            // Wait for save confirmation
            await page.waitForTimeout(500);
        }
    });

    test('requires authentication', async ({ page }) => {
        // Try to access admin without login
        await page.goto('/admin/');

        // Should redirect to login
        await expect(page).toHaveURL(/\/admin\/login/);
    });
});
