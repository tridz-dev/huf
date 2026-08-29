---
title: "FIFO & Moving Average Valuation Methods"
source_url: "https://docs.frappe.io/erpnext/fifo-and-moving-average"
section: stock
---

# FIFO & Moving Average Valuation Methods

## 1. Overview

ERPNext values stock **perpetually**: every stock movement (receipt, issue, transfer, manufacture) updates the item's quantity *and* its monetary value in real time through the **Stock Ledger**. The **Valuation Method** decides *how the value of each outgoing unit is calculated* and therefore what your remaining inventory is worth and what your Cost of Goods Sold (COGS) becomes.

ERPNext supports three valuation methods:

- **FIFO** (First In, First Out)
- **Moving Average**
- **Standard Cost** *(covered in a separate guide)*

This guide explains **FIFO** and **Moving Average** — how each works, the accounting they produce, their behavior with backdated entries and reposting, and the pros and cons of each so you can choose the right one per item.

> **Where to set it:** Valuation Method can be set per **Item** (Item master → *Valuation Method*), or defaulted at the **Company** level, or globally in **Stock Settings**. The most specific setting wins (Item → Company → Stock Settings).

---

## 2. FIFO (First In, First Out)

### 2.1 How it works

FIFO assumes the **oldest stock is consumed first**. ERPNext maintains a **FIFO queue** of `[quantity, rate]` layers for each item-warehouse. Every receipt adds a layer at its actual incoming rate; every issue consumes layers from the **front** (oldest) of the queue at *their original rates*.

The valuation rate reported at any moment is the **weighted average of the layers currently remaining** in the queue, but each outgoing unit is costed at the *specific* rate of the layer it is drawn from.

### 2.2 Worked example

| Step | Transaction      | Queue after              | Stock value |
| ---- | ---------------- | ------------------------ | ----------- |
| 1    | Receive 10 @ 100 | `[10 @ 100]`             | 1,000       |
| 2    | Receive 10 @ 120 | `[10 @ 100], [10 @ 120]` | 2,200       |
| 3    | Issue 15         | `[5 @ 120]`              | 600         |

At step 3, the 15 issued units are costed as **10 @ 100 + 5 @ 120 = 1,600** (oldest first). The remaining 5 units stay valued at their original 120.

### 2.3 Accounting impact

In a perpetual-inventory company, the issue posts COGS at the **actual layered cost** of the consumed units:

- COGS (step 3) = 1,600
- Inventory is credited 1,600; remaining inventory asset = 600.

Because outgoing cost reflects the **actual historical purchase price** of the specific units leaving stock, FIFO closely tracks real acquisition cost and is widely accepted for statutory/tax reporting.

### 2.4 Pros

- **Closely matches actual cost flow** — the cost of goods sold reflects the genuine price paid for the specific units consumed.
- **Realistic ending inventory value** — remaining stock is valued at the most **recent** purchase prices, so the balance sheet reflects current replacement-ish cost.
- **Widely accepted** for accounting standards and tax authorities; intuitive and auditable (you can trace which layers were consumed).
- **Good for items with shelf life / lot rotation** (food, pharma, perishables) where you physically issue oldest-first anyway.

### 2.5 Cons

- **Sensitive to backdated entries** — inserting or editing a past transaction changes which layers later issues consume, so **every subsequent ledger entry must be recomputed (reposted)**. On long, dense ledgers this reposting is slow and resource-intensive.
- **Volatile COGS in rising-price environments** — older, cheaper layers are expensed first, which can understate COGS and overstate profit during inflation.
- **More computation / storage** — the layer queue must be maintained and serialized for every item-warehouse.
- **Heavier reposting load** when corrections, cancellations, or landed-cost vouchers touch historical entries.

---

## 3. Moving Average

### 3.1 How it works

Moving Average maintains a **single blended average rate** per item-warehouse. On **every receipt**, the average is recomputed:

```
new average = (existing qty × existing avg rate + incoming qty × incoming rate)
              ──────────────────────────────────────────────────────────────
                             existing qty + incoming qty
```

Issues are costed at the **current average rate** and do **not** change the average; only receipts (and revaluations) move it.

### 3.2 Worked example

| Step | Transaction      | Qty on hand | Avg rate | Stock value |
| ---- | ---------------- | ----------- | -------- | ----------- |
| 1    | Receive 10 @ 100 | 10          | 100      | 1,000       |
| 2    | Receive 10 @ 120 | 20          | 110      | 2,200       |
| 3    | Issue 15         | 5           | 110      | 550         |

At step 2 the average becomes `(10×100 + 10×120) / 20 = 110`. The 15 issued units at step 3 are each costed at **110** → COGS = 1,650; remaining 5 units valued at 110 = 550.

### 3.3 Accounting impact

- COGS (step 3) = **1,650** (15 × average 110).
- Inventory credited 1,650; remaining inventory asset = 550.

Compared with FIFO on the same data, Moving Average **smooths** the cost: COGS is 1,650 vs FIFO's 1,600, and the difference flows into the value of remaining stock.

### 3.4 Pros

- **Smooths out price fluctuations** — a single blended rate dampens the impact of volatile purchase prices, giving steadier COGS and margins.
- **Simpler and lighter** — only one rate per item-warehouse to maintain; no layer queue to store or walk.
- **Easier to understand and reconcile** — "one item, one current cost" is intuitive for operations and reporting.
- **Good for homogeneous, fast-moving, commoditized items** where individual lots are indistinguishable (bulk fasteners, fuel, raw chemicals).

### 3.5 Cons

- **Still requires reposting on backdated entries** — because a past receipt changes the running average for **all later** transactions, ERPNext must recompute the forward chain. Like FIFO, this can be slow on long ledgers.
- **Does not track actual lot cost** — outgoing cost is a blend, so it can diverge from the real price paid for the specific units shipped; less precise for lot-traceable or high-value items.
- **Average can lag reality** — in fast-moving price environments the blended rate trails current market cost, which may misstate margins on individual sales.
- **Less granular audit trail** — you cannot point to "these specific units left at this specific cost," only to the average at that time.

---

## 4. FIFO vs Moving Average — at a glance

| Aspect                           | FIFO                                            | Moving Average                               |
| --------------------------------- | ------------------------------------------------ | --------------------------------------------- |
| **Outgoing cost basis**          | Actual rate of the oldest remaining layer       | Current blended average rate                 |
| **Tracks real lot cost?**        | Yes (layer-accurate)                            | No (blended)                                 |
| **COGS behavior**                | Reflects oldest prices first                    | Smoothed across all receipts                 |
| **Ending inventory value**       | At most recent purchase prices                  | At the blended average                       |
| **Data maintained**              | Queue of `[qty, rate]` layers                   | Single average rate                          |
| **Backdated entry → reposting?** | **Yes** (recompute forward chain)               | **Yes** (recompute forward chain)             |
| **Computation cost**             | Higher (layer walking)                          | Lower (single rate)                          |
| **Best for**                     | Perishables, lot-rotated, audit-sensitive items | Homogeneous, high-volume, commoditized items |
| **Statutory acceptance**         | Very widely accepted                            | Widely accepted                              |

---

## 5. The shared limitation: backdated entries trigger reposting

This is the most important operational characteristic both methods share — and the key contrast with **Standard Cost**.

With **both FIFO and Moving Average**, the value of any stock ledger entry depends on **the entries before it** (which layers exist, or what the running average is). So when you:

- insert a **backdated** transaction,
- **cancel** or **amend** a historical voucher,
- apply a **Landed Cost Voucher** to a past receipt, or
- change a past valuation rate,

…ERPNext must **repost** — recompute the quantity, rate, value, and GL impact of **every subsequent stock ledger entry** for that item-warehouse (a *Repost Item Valuation* job). On items with long, dense histories this is **slow, resource-heavy, and temporarily changes the value of stock you considered settled**.

> If your organization frequently records **backdated corrections** and this reposting cost is painful, consider the **Standard Cost** method (see the separate *Standard Valuation Rate* guide), where the rate is known by date and backdated entries do **not** trigger reposting.

---

## 6. Choosing a method — recommendations

| Your situation                                                     | Recommended method                   |
| -------------------------------------------------------------------- | --------------------------------------- |
| Perishable / shelf-life items, physically issued oldest-first      | **FIFO**                             |
| High-value or lot-traceable items needing precise cost             | **FIFO**                             |
| Statutory/tax regime that expects actual cost flow                 | **FIFO**                             |
| Homogeneous, commoditized, fast-moving items                       | **Moving Average**                   |
| You want smoother, more stable margins                             | **Moving Average**                   |
| You want minimal valuation maintenance overhead                    | **Moving Average**                   |
| You frequently post **backdated** entries and reposting hurts      | **Standard Cost** *(separate guide)* |
| You want predictable, fixed product cost & isolated price variance | **Standard Cost** *(separate guide)* |

### Best practices (both methods)

- **Set the method before the item transacts.** Changing an item's valuation method while stock exists is disruptive and may be blocked.
- **Enable perpetual inventory accounts** (warehouse/stock, stock-received-but-not-billed, COGS, stock adjustment) so valuation and GL stay in lock-step.
- **Batch your historical corrections** and run them in low-traffic windows, since they trigger reposting.
- **Use Landed Cost Vouchers promptly** after receipt to avoid large retroactive revaluations later.
- **Reconcile stock value vs. GL** periodically (Stock Ledger / Stock Balance vs. the inventory account) to catch drift early.
- **Be consistent per item category** so reporting and margins are comparable across similar items.

---

## 7. Summary

- **FIFO** costs outgoing stock at the **actual rate of the oldest remaining layer** — precise, audit-friendly, ideal for perishables and lot-traceable goods, but layer-heavy and reposting-sensitive.
- **Moving Average** costs outgoing stock at a **single blended rate** — simple, smooth, ideal for commoditized high-volume items, but less precise and still reposting-sensitive.
- **Both** recompute (repost) the forward ledger when the past changes. If that cost is the deciding factor, the **Standard Cost** method avoids it entirely — see the *Standard Valuation Rate* guide.
