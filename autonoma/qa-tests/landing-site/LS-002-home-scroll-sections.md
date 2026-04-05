---
title: Home page scroll sections appear in correct order
description: Scroll down the home page and verify all sections appear in the documented order
criticality: mid
scenario: standard
flow: landing-site
category: happy-path
priority: Medium
---

# LS-002: Home page scroll sections appear in correct order

## Setup

- Use skill: `navigate-landing-home`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/`
2. Scroll down past the hero section
3. Verify "The Missing Layer" problem statement section is visible
4. Continue scrolling and verify "Five Lines of Code" section with three code examples appears
5. Verify "The Compliance Receipt" section shows four statistics: Validation (560ns), Frameworks (9), Tests (3,133), Checklist (72/125)
6. Verify "Nine Frameworks, One Library" table is visible showing 9 regulatory frameworks
7. Verify "Constitutional Guarantees" feature cards section is visible with cards for: MACI Separation of Powers, Tamper-Evident Audit Chain, Zero Performance Impact, Pass Your Next Audit
8. Verify "The Engine Is Free Forever" pricing teaser is visible with a "View pricing" link

## Expected Result

All home page sections render in the correct order as the user scrolls. Scroll animations trigger as sections enter the viewport.

## Bug Description

If sections are missing or out of order, the landing page's narrative flow is broken, reducing conversion effectiveness.
