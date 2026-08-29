---
title: "Manage Tree Structure Masters"
source_url: "https://docs.frappe.io/erpnext/managing-tree-structure-masters"
section: data-model
---

# Manage Tree Structure Masters

Some of the administrative records in ERPNext utilize a hierarchical arrangement. This structural approach enables you to establish parent-level records with subordinate child records, facilitating the generation of analytical reports and enabling you to monitor advancement at various tiers of the organization.

## Masters Using Tree Structure

The following represents a partial compilation of records organized hierarchically:

* Chart of Accounts
* Chart of Cost Centers
* Customer Group
* Territory
* Sales Person
* Item Group

## Steps for Managing Tree-Structured Records

The procedure for establishing and maintaining hierarchical records follows this approach, using Territory as an illustrative example:

### Step 1: Access the Master

Navigate to: `Selling > Setup > Territory`

### Step 2: Parent Territory

Upon selecting the parent territory option, you'll discover functionality to add subordinate territories. All default Territory collections are organized beneath a primary grouping identified as "All Territories." You may establish supplementary parent or child Territory collections within this framework.

### Step 3: Add New Territory

Selecting "Add Child" activates a form containing two required fields:

**Territory Group Name**

The designation you enter here becomes the saved Territory identifier.

**Group Node**

Designating this as "Yes" establishes the Territory as a parent-level entity, permitting creation of nested territories beneath it. Selecting "No" classifies it as a child Territory, making it available for selection in related records and business processes.

Only child Territory collections qualify for selection in other administrative records and operational activities.

Following this methodology, you may similarly administer additional hierarchical records throughout ERPNext.
