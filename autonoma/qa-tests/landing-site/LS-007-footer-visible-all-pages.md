---
title: Footer is visible on all pages with correct content
description: Verify the footer appears on every page with PyPI link, constitutional hash, and live clock
criticality: mid
scenario: standard
flow: landing-site
category: navigation
priority: Medium
---

# LS-007: Footer is visible on all pages with correct content

## Setup

- Use skill: `navigate-landing-home`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/` and scroll to the bottom
2. Verify the footer contains a large banner linking to PyPI with text `"pip install acgs"`
3. Verify the footer shows `"CONSTITUTIONAL HASH"` followed by a hash value
4. Verify the footer contains links to PyPI and GitHub
5. Verify the footer shows `"LOCAL TIME"` with a live clock
6. Navigate to `/pricing` and scroll to the bottom
7. Verify the same footer elements are present
8. Navigate to `/resources` and scroll to the bottom
9. Verify the same footer elements are present

## Expected Result

The footer is consistently rendered on all pages with the PyPI link, constitutional hash, external links, and live clock.

## Bug Description

If the footer is missing or inconsistent across pages, the site lacks a consistent navigation and branding experience.
