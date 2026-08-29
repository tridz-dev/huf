---
title: "Supplier Scorecard"
source_url: "https://docs.frappe.io/erpnext/supplier-scorecard"
section: buying
---

# Supplier Scorecard

## Overview

A Supplier Scorecard serves as an assessment mechanism to gauge vendor performance metrics including quality, delivery timelines, and responsiveness over extended periods. This information supports procurement decision-making. Each supplier requires an individual scorecard, created manually within the system.

**Access path:** Home > Buying > Supplier Scorecard > Supplier Scorecard

## Prerequisites

Before establishing a Supplier Scorecard, ensure you have:
- A [Supplier](/erpnext/supplier) record already configured

## Creation Process

1. Navigate to the Supplier Scorecard list and select New
2. Choose the specific supplier to evaluate
3. Define the assessment interval (weekly, monthly, or yearly)
4. Configure the scoring methodology (see following sections)
5. Note: Each supplier receives one scorecard maximum

## Key Features

### Scoring Mechanics

The scorecard operates through defined evaluation periods that measure vendor performance. Scores from individual periods combine using a weighting formula—by default, this distributes weight linearly across the previous 12 periods, though customization is available.

**Supplier Standing Levels:** Performance classifications that enable quick vendor sorting. These standings can restrict supplier participation in Request for Quotations or Purchase Order issuance.

### Evaluation Criteria

Vendors face assessment across multiple dimensions—response speed on quotations, quality of delivered goods, and delivery punctuality. These weighted criteria combine to form the period score. Access criteria management through Buying > Supplier Scorecard > Supplier Scorecard Criteria.

*Important:* Criteria weights must total 100.

### Variable System

Pre-established variables calculate each criterion—including received item counts, accepted quantities, rejections, delivery frequency, and monetary totals. Custom variables require server-side modifications. The criteria formula adapts these variables to organizational standards.

### Formula Structure

Evaluation formulas employ these mathematical operations:
- Basic arithmetic: +, -, *, /
- Functions: min(), max()
- Conditionals: (x) if (formula) else (y)
- Comparisons: <, >
- Variable insertion: {variable_name}

**Critical consideration:** "It is crucial that the formula be solvable for all variable values." Always protect against division-by-zero scenarios.

### Period Generation & Analysis

Trigger scorecard period generation via the "Generate Missing Scorecard Periods" button. View current scores with visual performance trends over time, plus any restrictions affecting RFQ or PO activities.

## Related Documentation

- [Supplier](/erpnext/supplier)
- [Supplier Quotation](/erpnext/supplier-quotation)
