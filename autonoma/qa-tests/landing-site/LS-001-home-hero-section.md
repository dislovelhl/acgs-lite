---
title: Home page hero section displays correctly
description: Navigate to the landing page and verify the hero section with heading, buttons, and EU AI Act countdown
criticality: high
scenario: standard
flow: landing-site
category: happy-path
priority: High
---

# LS-001: Home page hero section displays correctly

## Setup

- Use skill: `navigate-landing-home`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/`
2. Wait for the page to finish loading
3. Verify the header navigation bar is visible with the "ACGS" logo on the left
4. Verify the hero section contains the large heading text `"HTTPS FOR AI"`
5. Verify the `"PIP INSTALL ACGS"` button is visible in the hero area
6. Verify the `"EXPLORE RESOURCES"` link is visible next to the install button
7. Verify the EU AI Act countdown badge is visible in the navigation bar, matching the pattern `"\d+ DAYS TO EU AI ACT"`
8. Verify the navigation bar contains links: FRAMEWORKS, HOW IT WORKS, PRICING, RESOURCES

## Expected Result

The home page loads with the full hero section, call-to-action buttons, and EU AI Act countdown visible. The 3D crystal animation renders in the background.

## Bug Description

If the hero section is missing or key elements are not visible, the landing page fails to communicate the product's core value proposition to visitors.
