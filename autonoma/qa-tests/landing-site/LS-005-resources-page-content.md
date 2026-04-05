---
title: Resources page shows videos and presentations
description: Navigate to the resources page and verify all resource cards are displayed
criticality: mid
scenario: standard
flow: landing-site
category: happy-path
priority: Medium
---

# LS-005: Resources page shows videos and presentations

## Setup

- Use skill: `navigate-landing-resources`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/resources`
2. Verify the heading `"Technical Arsenal"` is visible
3. Verify the Videos section contains exactly **2** video cards: "Compiling the Law" and "Architecting Constraints"
4. Verify each video card has an embedded video player and a "Download High Quality" button
5. Verify the Presentations section contains exactly **2** presentation cards: "ACGS Cryptographic Infrastructure" and "Architecting Machine Trust"
6. Verify each presentation card has a "Download Resource" button
7. Verify the total resource count is **4** cards

## Expected Result

The resources page displays all 4 resource cards (2 videos, 2 presentations) with correct titles and download buttons.

## Bug Description

If resources are missing or download buttons are broken, technical buyers cannot access deep-dive materials, reducing engagement.
