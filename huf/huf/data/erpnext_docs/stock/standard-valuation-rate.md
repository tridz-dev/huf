---
title: "Standard Valuation Rate (Standard Costing)"
source_url: "https://docs.frappe.io/erpnext/standard-valuation-rate"
section: stock
---

# Standard Valuation Rate (Standard Costing)

## 1. Overview

The **Standard Valuation Rate** feature lets you value an item's inventory at a single, pre-defined "standard" cost rather than at the constantly-changing rate produced by **FIFO** or **Moving Average**.

With FIFO or Moving Average, the value of your stock moves every time you receive, consume, or revalue material. With **Standard Cost**, the rate is fixed by you (via an **Item Standard Cost** record) and only changes when *you* deliberately publish a new rate. Every receipt, issue, and balance for that item is carried at the standard rate, and the difference between the actual purchase price and the standard rate is posted to a dedicated **Purchase Price Variance** account instead of silently inflating or deflating your inventory value.

This guide explains what the feature does, why you would choose it, how to set it up, how it behaves during transactions and accounting, and the rules you must follow to keep your standard-cost ledger consistent.

---

## 2. Why choose Standard Cost over FIFO / Moving Average?

| Concern                       | FIFO / Moving Average                                           | Standard Cost                                                                                                |
| ------------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Inventory value stability** | Changes with every receipt and revaluation                      | Fixed until you publish a new rate                                                                           |
| **Backdated transactions**    | Trigger a **full revaluation / reposting** of all later entries | **No reposting** — only a fast quantity/value shift                                                          |
| **Reposting performance**     | Slow on items with long, dense ledgers                          | Fast — the rate is known by date, nothing is recalculated                                                    |
| **Cost predictability**       | Cost of goods varies by lot/average                             | Cost of goods is the standard rate, always                                                                   |
| **Variance visibility**       | Price differences are buried in stock value                     | Price differences are isolated in a **Purchase Price Variance** account                                      |
| **Best suited for**           | Trading, where actual landed cost matters per lot               | Manufacturing & high-volume operations that want predictable product cost and frequent backdated corrections |

### The headline benefit: backdated entries do **not** trigger revaluation

This is the single most important reason to adopt Standard Cost.

- With **FIFO / Moving Average**, inserting a transaction *in the past* changes the average/lot consumption of **every later transaction**. The system must **repost** (recompute) the entire forward chain of stock ledger entries. On an item with months of dense history, this is slow and resource-heavy, and it temporarily changes the value of stock that you thought was settled.
- With **Standard Cost**, the value of every stock ledger entry is simply `quantity × standard rate as of that date`. A backdated entry only shifts the running **quantity** of later entries; their **value** is re-derived directly from the (already known) standard rate. There is **no FIFO/average recomputation and no reposting job**. The update is a single, fast quantity-and-value shift, and your inventory valuation stays stable and predictable.

> In short: Standard Cost trades "perfectly tracked actual cost" for **speed, stability, and predictability** — exactly the trade-off most manufacturing and high-throughput operations want.

---

## 3. Key concept: the **Item Standard Cost** record

The standard rate for an item is published through the **Item Standard Cost** document. Each record carries:

- **Item** — the item being standard-costed (only items whose valuation method resolves to *Standard Cost* are selectable).
- **Company** — the rate is per company.
- **Standard Rate** — the fixed valuation rate (must be greater than zero).
- **Effective Date** — the date from which this rate applies.

Each item+company has a **timeline** of Item Standard Cost records, with **strictly increasing effective dates**. The rate in force on any given date is the latest record whose effective date is on or before that date.

```
Item A (Company X)
 ├─ ISC-2025-0001  Effective 01-Jan-2025  Rate 100   ← rate from 01-Jan-2025 onward
 └─ ISC-2026-0001  Effective 01-Jan-2026  Rate 130   ← rate from 01-Jan-2026 onward
```

---

## 4. Setting up an item's Standard Cost — step by step

### Step 1 — Set the item's valuation method to *Standard Cost*

Set **Valuation Method = Standard Cost** on the item, in one of three ways (most specific wins):

1. **Item master** → *Valuation Method* = `Standard Cost`, **or**
2. Leave the item blank and set the **Company** default valuation method to `Standard Cost`, **or**
3. Leave both blank and set **Stock Settings** → default valuation method to `Standard Cost`.

> **Important:** an item that *already has stock movement* cannot be switched onto Standard Cost retroactively. Enable Standard Cost on a new item, or before any stock transaction exists for it.

### Step 2 — Create the first Item Standard Cost record

1. Go to **Item Standard Cost → New**.
2. Select the **Item** (the dropdown only lists items whose effective valuation method is *Standard Cost*).
3. Select the **Company**.
4. Enter the **Standard Rate** (must be > 0).
5. Set the **Effective Date** (cannot be a future date).
6. **Save** and **Submit**.

> The very first standard cost for an item can only be created **before any stock transaction exists** for that item+company. This guarantees the item starts its life under Standard Cost with nothing to revalue.

### Step 3 — Transact normally

Receive, issue, manufacture, and transfer the item as usual. Every stock ledger entry is automatically valued at the standard rate in force on its posting date.

### Step 4 — Change the rate later (when needed)

When the standard cost needs to change:

1. Create a **new** Item Standard Cost record with the new rate.
2. Give it an **Effective Date after the previous record's effective date** (effective dates must strictly increase) and **on or after the last stock transaction date** for that item.
3. **Submit** it.

On submission, the system automatically creates and submits a **revaluation Stock Reconciliation** that re-states all on-hand stock (across **all warehouses**) from the old rate to the new rate, and books the revaluation gain/loss to the **Stock Adjustment** account. You do not create this reconciliation manually — it is generated for you and linked on the record.

---

## 5. How Standard Cost behaves during transactions & accounting

### Stock ledger valuation

Every stock ledger entry for a standard-cost item is valued at the standard rate, regardless of the document (purchase) rate.

**Example — receive at a price different from standard:**

- Standard rate = **100**
- Purchase Receipt of 10 units billed at **150**
- The stock ledger values the receipt at **100** → stock value increases by **1,000** (not 1,500).

### Accounting — the Purchase Price Variance

The gap between the **document/purchase rate** and the **standard rate** is the *purchase price variance*, and it is posted to the company's **Default Purchase Price Variance Account** (or the item-level override, if set).

**Example — receive 1 unit @ 200, standard 130 (perpetual inventory):**

| Account                       | Debit | Credit |
| ------------------------------ | ----- | ------ |
| Stock (warehouse asset)       | 130   |        |
| Purchase Price Variance       | 70    |        |
| Stock Received But Not Billed |       | 200    |

> The 70 difference lands in **Purchase Price Variance**, *not* in Cost of Goods Sold. This applies to **Purchase Receipts**, and to **Purchase Invoices with "Update Stock"** (both when billed against a receipt and when stand-alone).
>
> **Prerequisite:** the company must have a **Default Purchase Price Variance Account** configured (or an item-level Purchase Price Variance account). If neither is set, the transaction is blocked with a clear error so the variance is never mis-booked.

### Accounting — manufacturing variance

When you manufacture, the finished good is valued at **its own standard rate**, not at the rolled-up cost of the consumed raw materials. Any difference between consumed input value and produced output value is a **manufacturing variance**, posted to the company's **Stock Adjustment** account.

**Example — consume 5 RM @ standard 50 (=250) to produce 1 FG @ standard 200:**

- FG is valued at **200**.
- The **50** difference is booked to **Stock Adjustment**.

### Revaluation on rate change

Publishing a new Item Standard Cost re-values on-hand stock in **every warehouse** to the new rate via the auto-generated revaluation Stock Reconciliation, and posts the gain/loss to **Stock Adjustment**. Serial- and batch-tracked items are revalued across all warehouses too, without requiring serial/batch bundles for the revaluation.

---

## 6. The rules that protect standard-cost integrity

Standard Cost achieves its speed and stability by enforcing a few rules. Understanding *why* they exist makes them easy to live with.

### 6.1 You cannot backdate a transaction before the latest effective rate

> **Rule (R2):** A standard-cost item's stock transaction **cannot be dated before the effective date of its latest Item Standard Cost.**

**Why.** The fast "no-reposting" guarantee depends on the standard rate being **constant** across the window from the latest effective date to today. If you could insert a transaction *before* a rate change:

1. Later stock ledger entries would span **two different rates**, and the fast single-rate value shift would mis-value the entries posted after the rate change; and
2. More seriously, the **revaluation reconciliation** created at the rate change asserted the on-hand quantity *as it was at that moment*. A backdated entry changes that historical quantity, making the revaluation's quantity snapshot — and its GL impact — **stale**. Correcting it would require a full reposting, which is exactly what Standard Cost is designed to avoid.

So the system blocks the entry with a message like:

> **Backdated Entry Not Allowed**
> Cannot post Standard Cost item *Item A* on **01-06-2025**: it is before **01-01-2026**, the effective date of its latest Standard Valuation Rate *ISC-2026-0001*.
> Post this entry on or after **01-01-2026**.

**What to do instead:** post the transaction (or a correcting adjustment) **on or after** the latest effective date.

> **Note:** Backdated entries *within the current rate regime* (on or after the latest effective date, but earlier than today) **are** allowed — they only shift later quantities and are handled by the fast quantity/value update with no reposting.

### 6.2 You cannot cancel old stock transactions — create adjustments instead

Once a Standard Cost is established and later transactions exist, you should **not** try to "fix the past" by cancelling old stock vouchers. Cancelling a historical entry is itself a backdated change to the quantity timeline: it would invalidate the on-hand quantity that every later revaluation relied on, and would force a reposting / revaluation cascade — defeating the purpose of standard costing and risking inconsistent inventory value.

**The correct workflow is forward-looking:** record a **new adjustment entry** (e.g. a Stock Entry or Stock Reconciliation) dated **on or after** the latest effective date to reflect the change. This keeps the historical ledger immutable and the standard-cost timeline intact.

Likewise, **Item Standard Cost records cannot be cancelled.** To change a published rate, **submit a new Item Standard Cost** record with the new rate and a later effective date. The new record's revaluation handles the transition cleanly; the old record stays as the historical rate.

---

## 7. Worked scenarios

### Scenario A — Standard purchasing with price variance

1. Set Item A to *Standard Cost*; create Item Standard Cost rate **100**, effective today.
2. Receive 100 units at a billed rate of **120**.
3. **Result:** stock value rises by `100 × 100 = 10,000`; the `100 × 20 = 2,000` price difference is booked to **Purchase Price Variance**. Your inventory is valued at a clean, predictable 100/unit.

### Scenario B — Annual rate revision

1. Item A has run all year at rate **100** (effective 01-Jan-2025), 500 units on hand across two warehouses.
2. On 01-Jan-2026 you publish a new Item Standard Cost rate **130**.
3. **Result:** a revaluation Stock Reconciliation auto-revalues the 500 on-hand units (in both warehouses) from 100 → 130; the `500 × 30 = 15,000` uplift is posted to **Stock Adjustment**. From 01-Jan-2026, new receipts/issues are valued at 130.
4. You now **cannot** post any Item A stock transaction dated before 01-Jan-2026 (see §6.1). A late invoice for December must be recorded with a posting date on/after 01-Jan-2026, or handled as a forward adjustment.

### Scenario C — Backdated correction within the current regime

1. Latest effective rate is **130** (01-Jan-2026); today is 15-Jan-2026.
2. You discover a missed receipt of 20 units dated 05-Jan-2026.
3. **Result:** allowed. The entry posts at rate 130; later entries' running quantities shift forward and their values are re-derived at 130 — **no reposting job**, fast and stable.

### Scenario D — Manufacturing

1. RM standard **50**, FG standard **200**.
2. Repack consumes 5 RM (value 250) and produces 1 FG.
3. **Result:** FG valued at **200**; the **50** manufacturing variance goes to **Stock Adjustment**.

---

## 8. Limitations, best practices & recommendations

### Limitations

- **No retroactive adoption.** An item with existing stock movement cannot be switched to Standard Cost; enable it before the item transacts.
- **The first rate must precede all movement.** The initial Item Standard Cost can only be created before any stock transaction exists for that item+company.
- **Effective dates are strictly increasing**, must not be in the future, and must be on/after the last stock transaction date.
- **No pre-rate-change backdating.** Transactions cannot be dated before the latest effective rate (§6.1).
- **No cancellation** of Item Standard Cost records, and historical stock vouchers should not be cancelled — use forward adjustments (§6.2).

### Best practices

- **Configure accounts up front:** set the company's **Default Purchase Price Variance Account** and **Stock Adjustment Account** before transacting standard-cost items, so variances are booked correctly and the system never blocks a receipt for a missing account.
- **Review variance accounts periodically.** A consistently large Purchase Price Variance signals that your standard rate has drifted from reality — time to publish a new rate.
- **Plan rate changes for clean cut-over dates** (e.g. period/year start). Because you cannot post before the latest effective date, choose an effective date that follows your last booked transaction, ideally after all prior-period entries are in.
- **Make corrections forward, not backward.** Treat the historical ledger as immutable; reflect any change with a new dated adjustment.
- **Use per-item Purchase Price Variance overrides** (via Item Default) only when an item genuinely needs to separate its variance from the company default.

### When to recommend Standard Cost in production

Standard Cost is most beneficial for organizations that:

- run **high transaction volumes** where FIFO/Moving-Average reposting is slow;
- frequently record **backdated corrections** and need them to be cheap and non-disruptive;
- want **predictable, stable product cost** and a clear, isolated view of **price variances**;
- operate **manufacturing** flows where finished goods should carry a planned standard cost.

It is **less suitable** for pure trading operations where the actual landed cost of each lot is the number that matters most.

---

# Manufacturing Variance (for Standard Cost items)

## 1. What is this feature?

When you use the **Standard Cost** valuation method, every finished good is always valued at a fixed **standard rate** that you set — regardless of what it actually cost to make it.

But the real cost of making it (raw materials consumed + any additional/landed costs) is rarely *exactly* equal to that standard rate. There is almost always a small difference.

That difference is called the **Manufacturing Variance**:

- If making the item **cost more** than its standard rate → **unfavourable** variance (you spent more than planned).
- If making the item **cost less** than its standard rate → **favourable** variance (you spent less than planned).

This feature makes sure that difference is booked to a **dedicated Manufacturing Variance account**, so it is easy to see and report on — instead of being quietly mixed into your general Stock Adjustment / cost accounts.

> It is the manufacturing equivalent of the **Purchase Price Variance** you may already use on Purchase Receipts.

---

## 2. A simple example

You value a finished product at a **standard rate of ₹200**.

To produce **1 unit**, you consume raw materials worth **₹250**.

- Finished good goes into stock at its standard value: **₹200**
- Actual cost consumed: **₹250**
- **Manufacturing Variance = ₹50 (unfavourable)** → booked to the Manufacturing Variance account.

If instead the raw materials had only cost **₹180**, the variance would be **₹20 favourable** (a credit in the variance account).

---

## 3. When does it apply?

It applies automatically to a **Manufacture** or **Repack** Stock Entry whenever the **finished good** uses the **Standard Cost** valuation method.

It does **not** apply to items valued using FIFO or Moving Average — those items simply absorb their real cost as usual, so there is no variance to book.

---

## 4. What you need to set up (one time)

The system needs to know **which account** to record the variance in. You can set this in two places:

1. **Company level (recommended default)**
  - Go to **Company** → open your company.
  - In the **Stock Settings** area, set **Default Manufacturing Variance Account**.
  - This account will be used for all Standard Cost items in that company.
2. **Item level (optional override)**
  - Go to the **Item** → **Item Defaults** section (per company).
  - Set **Manufacturing Variance Account** for that specific item.
  - If set, this takes priority over the company default for that item only.

**Which account should it be?** Usually an **Expense-type** account (for example under *Stock Expense* group), chosen together with your accountant.

---

## 5. What happens if the account is not set?

If a Standard Cost item is manufactured/repacked and **no** Manufacturing Variance account is found (neither on the Item nor on the Company), the system will **stop and show an error** asking you to set one.

This is intentional — it prevents the variance from being posted to the wrong place. Simply set the account (Section 4) and submit again.
