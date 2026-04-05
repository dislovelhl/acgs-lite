---
title: Demo page shows launch button linking to Playwright demo
description: Navigate to the demo page and verify the launch button links to the Playwright demo
criticality: mid
scenario: standard
flow: landing-site
category: happy-path
priority: Medium
---

# LS-006: Demo page shows launch button linking to Playwright demo

## Setup

- Use skill: `navigate-landing-demo`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/demo`
2. Verify the heading `"Interactive Demo"` is visible
3. Verify the `"LAUNCH PLAYWRIGHT DEMO"` button is visible
4. Verify the button links to `/demo/playwright`
5. Click the button
6. Verify the page navigates to `/demo/playwright`
7. Verify the heading `"Playwright E2E"` is visible on the destination page
8. Verify the subtitle `"Automated Verification Suite"` is visible

## Expected Result

The demo page provides a clear entry point to the Playwright demo suite. The button navigates correctly to the demo page.

## Bug Description

If the demo button is missing or links to the wrong page, visitors cannot access the interactive demonstration.
