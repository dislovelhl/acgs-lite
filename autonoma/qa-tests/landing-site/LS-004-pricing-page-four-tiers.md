---
title: Pricing page displays four tiers with correct details
description: Navigate to the pricing page and verify all four pricing tiers are displayed with correct prices and features
criticality: high
scenario: standard
flow: landing-site
category: happy-path
priority: High
---

# LS-004: Pricing page displays four tiers with correct details

## Setup

- Use skill: `navigate-landing-pricing`
- The Propriety AI landing site is running

## Steps

1. Navigate to `/pricing`
2. Verify the heading `"The Engine Is Free Forever"` is visible
3. Verify exactly **4** pricing tier cards are displayed
4. Verify the Community tier shows price `"Free"` with `"forever"` label and button text `"pip install acgs"`
5. Verify the Pro tier shows price `"$299"` with `"/month"` label, a blue accent border, and a `"POPULAR"` badge
6. Verify the Team tier shows price `"$999"` with `"/month"` label
7. Verify the Enterprise tier shows price `"Custom"` with button text `"Contact sales"`
8. Verify the text `"All prices in USD. Annual billing: save 15%."` is visible below the cards

## Expected Result

All four pricing tiers are displayed with correct pricing, features, and visual hierarchy. The Pro tier is visually highlighted as the popular choice.

## Bug Description

If pricing is missing or incorrect, visitors cannot evaluate the product's value proposition, directly impacting conversion rates.
