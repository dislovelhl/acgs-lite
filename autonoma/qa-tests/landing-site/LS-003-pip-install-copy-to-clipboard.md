---
title: PIP INSTALL ACGS button copies to clipboard
description: Click the PIP INSTALL ACGS button and verify it copies the pip install command to clipboard
criticality: mid
scenario: standard
flow: landing-site
category: happy-path
priority: Medium
---

# LS-003: PIP INSTALL ACGS button copies to clipboard

## Setup

- Use skill: `navigate-landing-home`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/`
2. Locate the `"PIP INSTALL ACGS"` button in the hero section
3. Click the button
4. Verify the clipboard contains the text `pip install acgs`

## Expected Result

Clicking the button copies the installation command to the user's clipboard, enabling one-click developer onboarding.

## Bug Description

If the clipboard copy fails, developers must manually type the installation command, adding friction to the onboarding flow.
