---
title: Navigation bar links route to correct pages
description: Verify all navigation bar links route to the correct destinations
criticality: high
scenario: standard
flow: landing-site
category: navigation
priority: High
---

# LS-008: Navigation bar links route to correct pages

## Setup

- Use skill: `navigate-landing-home`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/`
2. Verify the navigation bar is visible
3. Click the `"PRICING"` link in the navigation bar
4. Verify the browser navigates to `/pricing`
5. Verify the heading `"The Engine Is Free Forever"` is visible
6. Click the `"RESOURCES"` link in the navigation bar
7. Verify the browser navigates to `/resources`
8. Verify the heading `"Technical Arsenal"` is visible
9. Click the ACGS logo in the navigation bar
10. Verify the browser navigates back to `/`
11. Verify the hero heading `"HTTPS FOR AI"` is visible

## Expected Result

All navigation bar links route to their correct destinations. The ACGS logo links back to the home page.

## Bug Description

If navigation links are broken or route to wrong pages, visitors cannot explore the site, leading to immediate bounce.
