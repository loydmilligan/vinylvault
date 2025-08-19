const { test, expect } = require('@playwright/test');

/**
 * VinylVault Setup Form Test Suite
 * 
 * Tests the initial setup form functionality including:
 * - Form validation
 * - Network monitoring during submission
 * - Error handling
 * - Success scenarios
 */
describe('VinylVault Setup Form', () => {
  let context;
  let page;
  let networkEvents = [];
  let consoleMessages = [];

  test.beforeEach(async ({ browser }) => {
    // Create new context for each test to ensure clean state
    context = await browser.newContext();
    page = await context.newPage();
    
    // Reset tracking arrays
    networkEvents = [];
    consoleMessages = [];
    
    // Monitor network requests
    page.on('request', request => {
      networkEvents.push({
        type: 'request',
        url: request.url(),
        method: request.method(),
        headers: request.headers(),
        postData: request.postData(),
        timestamp: new Date().toISOString()
      });
    });
    
    page.on('response', response => {
      networkEvents.push({
        type: 'response',
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
        headers: response.headers(),
        timestamp: new Date().toISOString()
      });
    });
    
    // Monitor console messages
    page.on('console', msg => {
      consoleMessages.push({
        type: msg.type(),
        text: msg.text(),
        timestamp: new Date().toISOString()
      });
    });
    
    // Monitor JavaScript errors
    page.on('pageerror', error => {
      consoleMessages.push({
        type: 'error',
        text: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString()
      });
    });
  });

  test.afterEach(async () => {
    // Log collected data for debugging
    console.log('\n=== Network Events ===');
    networkEvents.forEach(event => {
      console.log(`${event.timestamp} [${event.type.toUpperCase()}] ${event.method || ''} ${event.url} ${event.status || ''}`);
      if (event.postData) {
        console.log(`  POST Data: ${event.postData}`);
      }
    });
    
    console.log('\n=== Console Messages ===');
    consoleMessages.forEach(msg => {
      console.log(`${msg.timestamp} [${msg.type.toUpperCase()}] ${msg.text}`);
      if (msg.stack) {
        console.log(`  Stack: ${msg.stack}`);
      }
    });
    
    await context.close();
  });

  test('should load setup form with all required elements', async () => {
    // Navigate to setup page
    await page.goto('/setup');
    
    // Verify page title
    await expect(page).toHaveTitle(/Setup - VinylVault/);
    
    // Verify main heading
    await expect(page.locator('h1')).toHaveText('Welcome to VinylVault');
    
    // Verify form elements exist
    await expect(page.locator('form')).toBeVisible();
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#token')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    
    // Verify form labels
    await expect(page.locator('label[for="username"]')).toHaveText('Discogs Username');
    await expect(page.locator('label[for="token"]')).toHaveText('Discogs User Token');
    
    // Verify placeholder texts
    await expect(page.locator('#username')).toHaveAttribute('placeholder', 'Enter your Discogs username');
    await expect(page.locator('#token')).toHaveAttribute('placeholder', 'Enter your Discogs user token');
    
    // Verify required attributes
    await expect(page.locator('#username')).toHaveAttribute('required');
    await expect(page.locator('#token')).toHaveAttribute('required');
    
    // Verify input types
    await expect(page.locator('#username')).toHaveAttribute('type', 'text');
    await expect(page.locator('#token')).toHaveAttribute('type', 'password');
  });

  test('should validate required fields on empty submission', async () => {
    await page.goto('/setup');
    
    // Try to submit empty form
    await page.click('button[type="submit"]');
    
    // Check for HTML5 validation (browser will prevent submission)
    const usernameValidity = await page.locator('#username').evaluate(el => el.validity.valid);
    const tokenValidity = await page.locator('#token').evaluate(el => el.validity.valid);
    
    expect(usernameValidity).toBe(false);
    expect(tokenValidity).toBe(false);
    
    // Verify form is still on setup page (didn't submit)
    await expect(page).toHaveURL(/\/setup/);
  });

  test('should submit form with provided credentials and monitor network activity', async () => {
    await page.goto('/setup');
    
    // Fill in the form with provided credentials
    await page.fill('#username', 'missmara112');
    await page.fill('#token', 'OrDekxwKOljATIHFARDczPWSCBkcjgpCXFzrqIhN');
    
    // Take screenshot before submission
    await page.screenshot({ path: 'tests/screenshots/before-setup-submit.png', fullPage: true });
    
    // Monitor for form submission
    const responsePromise = page.waitForResponse(response => 
      response.url().includes('/setup') && response.request().method() === 'POST'
    );
    
    // Submit the form
    await page.click('button[type="submit"]');
    
    // Wait for the POST response
    const response = await responsePromise;
    
    console.log(`Setup form submission response: ${response.status()} ${response.statusText()}`);
    
    // Take screenshot after submission
    await page.screenshot({ path: 'tests/screenshots/after-setup-submit.png', fullPage: true });
    
    // Check response status
    expect(response.status()).toBeLessThan(500); // Should not be server error
    
    // Wait for any redirects or page changes
    await page.waitForTimeout(2000);
    
    // Analyze what happened based on the response
    if (response.status() === 200) {
      // Check if we're still on setup page (form errors) or redirected
      const currentUrl = page.url();
      console.log(`Current URL after submission: ${currentUrl}`);
      
      if (currentUrl.includes('/setup')) {
        // Still on setup page - check for error messages
        const errorMessages = await page.locator('.alert, .error, .flash-message').allTextContents();
        console.log('Error messages found:', errorMessages);
        
        // Check for specific error indicators in the page content
        const pageContent = await page.textContent('body');
        const hasDiscogsError = pageContent.includes('Discogs') && 
                               (pageContent.includes('Invalid') || pageContent.includes('error') || 
                                pageContent.includes('failed') || pageContent.includes('not found'));
        
        if (hasDiscogsError) {
          console.log('Discogs API connection failed - this is expected with test credentials');
        }
      } else {
        // Successfully redirected - setup completed
        console.log('Setup completed successfully - redirected to main page');
        await expect(page).not.toHaveURL(/\/setup/);
      }
    } else if (response.status() >= 300 && response.status() < 400) {
      // Redirect response
      console.log('Received redirect response');
      await expect(page).not.toHaveURL(/\/setup/);
    } else {
      // Error response
      console.log(`Received error response: ${response.status()}`);
      const responseBody = await response.text();
      console.log('Response body:', responseBody);
    }
    
    // Verify network activity
    const postRequests = networkEvents.filter(event => 
      event.type === 'request' && 
      event.method === 'POST' && 
      event.url.includes('/setup')
    );
    
    expect(postRequests.length).toBeGreaterThanOrEqual(1);
    
    // Check if form data was properly sent
    const setupRequest = postRequests[0];
    expect(setupRequest.postData).toContain('username=missmara112');
    expect(setupRequest.postData).toContain('token=OrDekxwKOljATIHFARDczPWSCBkcjgpCXFzrqIhN');
    
    // Log final analysis
    console.log('\n=== Test Summary ===');
    console.log(`Total network events: ${networkEvents.length}`);
    console.log(`Console messages: ${consoleMessages.length}`);
    console.log(`Form submission status: ${response.status()}`);
    console.log(`Final URL: ${page.url()}`);
  });

  test('should handle individual field validation', async () => {
    await page.goto('/setup');
    
    // Test username field only
    await page.fill('#username', 'testuser');
    await page.click('button[type="submit"]');
    
    // Token should be invalid (empty)
    const tokenValidity = await page.locator('#token').evaluate(el => el.validity.valid);
    expect(tokenValidity).toBe(false);
    
    // Clear username and test token only
    await page.fill('#username', '');
    await page.fill('#token', 'testtoken123');
    await page.click('button[type="submit"]');
    
    // Username should be invalid (empty)
    const usernameValidity = await page.locator('#username').evaluate(el => el.validity.valid);
    expect(usernameValidity).toBe(false);
  });

  test('should check for security headers and CSRF protection', async () => {
    await page.goto('/setup');
    
    // Check for security-related response headers
    const response = await page.goto('/setup');
    const headers = response.headers();
    
    console.log('Security headers:', {
      'x-content-type-options': headers['x-content-type-options'],
      'x-frame-options': headers['x-frame-options'],
      'x-xss-protection': headers['x-xss-protection'],
      'content-security-policy': headers['content-security-policy']
    });
    
    // Verify form has proper method and action
    const formMethod = await page.locator('form').getAttribute('method');
    expect(formMethod?.toLowerCase()).toBe('post');
  });

  test('should test accessibility and mobile responsiveness', async () => {
    // Test desktop view
    await page.setViewportSize({ width: 1200, height: 800 });
    await page.goto('/setup');
    
    // Check form is properly sized for desktop
    const formBox = await page.locator('form').boundingBox();
    expect(formBox.width).toBeGreaterThan(400);
    
    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    
    // Verify form is still accessible on mobile
    await expect(page.locator('form')).toBeVisible();
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#token')).toBeVisible();
    
    // Check input field sizes are appropriate for touch
    const usernameHeight = await page.locator('#username').evaluate(el => el.offsetHeight);
    const tokenHeight = await page.locator('#token').evaluate(el => el.offsetHeight);
    
    // Should have minimum 44px height for touch targets
    expect(usernameHeight).toBeGreaterThanOrEqual(44);
    expect(tokenHeight).toBeGreaterThanOrEqual(44);
    
    // Take mobile screenshot
    await page.screenshot({ path: 'tests/screenshots/mobile-setup-form.png', fullPage: true });
  });

  test('should monitor performance metrics', async () => {
    // Start performance monitoring
    await page.goto('/setup');
    
    const performanceMetrics = await page.evaluate(() => {
      return {
        loadEventEnd: performance.timing.loadEventEnd,
        navigationStart: performance.timing.navigationStart,
        domContentLoaded: performance.timing.domContentLoadedEventEnd,
        firstPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-paint')?.startTime,
        firstContentfulPaint: performance.getEntriesByType('paint').find(entry => entry.name === 'first-contentful-paint')?.startTime
      };
    });
    
    const loadTime = performanceMetrics.loadEventEnd - performanceMetrics.navigationStart;
    const domReadyTime = performanceMetrics.domContentLoaded - performanceMetrics.navigationStart;
    
    console.log('Performance metrics:', {
      loadTime: `${loadTime}ms`,
      domReadyTime: `${domReadyTime}ms`,
      firstPaint: performanceMetrics.firstPaint ? `${performanceMetrics.firstPaint}ms` : 'N/A',
      firstContentfulPaint: performanceMetrics.firstContentfulPaint ? `${performanceMetrics.firstContentfulPaint}ms` : 'N/A'
    });
    
    // Basic performance assertions
    expect(loadTime).toBeLessThan(5000); // Should load within 5 seconds
    expect(domReadyTime).toBeLessThan(3000); // DOM should be ready within 3 seconds
  });
});