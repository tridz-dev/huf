---
title: "Auto Repost of Incorrect Stock Valuation in ERPNext"
source_url: "https://docs.frappe.io/erpnext/weekly-auto-repost"
section: stock
---

# Auto Repost of Incorrect Stock Valuation in ERPNext

## 1. What is this feature?

Sometimes the stock value recorded against an item can become **incorrect**. This usually happens when several stock transactions for the **same item and warehouse** are entered very close together (or backdated), and the system ends up calculating the stock value from the wrong earlier transaction.

When this happens:

- The **stock value** shown in your reports doesn't match what it should be, **or**
- The **stock value** and the **accounting value** (your inventory ledger in the General Ledger) no longer agree.

Normally, fixing this means a person has to open the relevant reports, spot the wrong entries, and manually trigger a "repost" to recalculate them.

**This feature automates that clean-up.** Once you switch it on, the system **checks your stock every week** and, where it finds incorrect values **in the current financial year**, it **automatically reposts the affected items** to correct them — no manual effort required.

---

## 2. When should you use it?

Turn this on if **any** of the following are true for your business:

- You enter a **high volume** of stock transactions, especially many for the same items and warehouses.
- You frequently make **backdated** or **corrective** stock entries.
- You've previously found mismatches in the **Stock Ledger Variance** report or the **Stock and Account Value Comparison** report and had to fix them by hand.
- You want **stock value and accounting value to stay reconciled** without someone checking every week.

When **not** to rely on it:

- If you only have a **small number** of stock transactions and rarely see valuation issues, you may not need it (you can still turn it on for peace of mind — it simply does nothing when there's nothing to fix).
- It is **not** a replacement for correct setup. If the underlying configuration is wrong (see Section 6), the feature will **tell you** rather than silently repost.

---

## 3. What exactly does it check and fix?

Every week the system looks at two standard reports for **each company**:

| Report                                 | What it catches                                                                                                 |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Stock Ledger Variance**              | Items whose stock quantity/value has become internally inconsistent (the "wrong previous transaction" problem). |
| **Stock and Account Value Comparison** | Vouchers where the **stock value** does not match the **accounting value** posted to the inventory account.     |

For anything it finds **in the current financial year**, it automatically creates a **repost** to recalculate and correct the values.

**Important:** it only acts on the **current financial year**. Older periods are intentionally left untouched (they are usually closed/audited, and reposting them could disturb finalised accounts). If you need to correct a previous year, do that manually and deliberately.

---

## 4. How to turn it on (step by step)

1. In the search bar, go to **Stock Reposting Settings**.
2. Find the section **Auto Reposting of Incorrect Valuation**.
3. Tick the checkbox **"Auto Repost Incorrect Valuation Entries (Weekly)"**.
4. **Save**.

That's it. The feature is **off by default**, so nothing happens until you tick this box. Once ticked, it runs **automatically once a week** in the background — you don't need to start it manually.

To turn it off again, simply un-tick the box and Save.

---

## 5. What happens after it runs?

- The system quietly creates **Repost Item Valuation** entries for the items/vouchers that need correcting. These run in the background and update the stock values.
- You can review what was reposted by opening the **Repost Item Valuation** list.
- It is designed to be **safe to run repeatedly**: it will not create duplicate reposts for something that is already being corrected.

You generally don't need to do anything — corrected values will simply appear once the reposts finish.

---

## 6. The one thing it can't fix on its own — and how you'll know

Some mismatches are **not** caused by calculation order, but by a **setup mistake**: a **warehouse is linked to the wrong type of account**.

For inventory accounting to work, a warehouse must be linked to an account whose **Account Type is "Stock"**. If a warehouse points to some other kind of account (for example a normal expense or receivable account), then **no amount of reposting will ever make the values match** — the problem is the configuration, not the calculation.

When the feature detects this situation, it does **not** waste time reposting. Instead it **sends a notification to the System Manager** describing:

- which voucher is affected,
- which warehouse is involved, and
- which account is set incorrectly.

**What to do if you receive this notification:**

1. Open the **Warehouse** mentioned in the message.
2. Check the **Account** linked to it.
3. Make sure that account's **Account Type is "Stock"** (or link the warehouse to the correct Stock account).
4. Save. The next weekly run (or a manual repost) can then reconcile the values.

---

## 7. Good to know (limitations & tips)

- **Journal Entries are never auto-reposted.** ERPNext does not repost Journal Entries, so any stock/account difference caused by a manual Journal Entry to an inventory account will **not** be touched by this feature. Review and correct those manually.
- **Current financial year only.** Older periods are deliberately skipped.
- **Runs weekly.** It is a scheduled clean-up, not an instant fix. If you need an urgent correction, you can still trigger a repost manually as before.
- **Large companies:** the weekly check examines every item-warehouse, so on very large databases it runs as a background task and may take a while — this is normal and does not slow down day-to-day work.
- **Notifications may repeat:** if a wrongly-configured warehouse account is not fixed, you may receive the same notification on the following week's run until it is corrected.

---

## 8. Quick FAQ

**Q: Will it change my accounts or stock without telling me?**  
It corrects stock **valuation** by reposting (the standard, supported way ERPNext recalculates stock value). It only acts on genuinely incorrect entries in the current year. For configuration problems it **notifies** rather than changing anything.

**Q: Is it safe to leave on permanently?**  
Yes. When there's nothing wrong, it simply finds nothing and does nothing.

**Q: Can I see what it did?**  
Yes — check the **Repost Item Valuation** list to see the reposts that were created.

**Q: I turned it on but nothing happened.**  
It runs on a **weekly schedule**, not immediately. Also, if your stock values are already correct, there's nothing for it to do.

**Q: Who gets the "wrong account" notification?**  
Users with the **System Manager** role.
