---
title: "Set Up Buy One Get One Free Offers"
source_url: "https://docs.frappe.io/erpnext/setting-up-buy-1-get-1-free-pricing-rule"
section: selling
---

## Overview

Product Discount Pricing Rules enable merchants to add complimentary items when transactions satisfy specific purchase conditions. The promotional item can match the purchased product or be an entirely separate item.

## Prerequisites

Before implementation, ensure:

- Qualifying and promotional items are created
- Selling prices are configured
- Stock levels support the free item allocation
- Customer segments (Customer, Customer Group, Territory, or campaign) are defined if applicable

Testing on demo transactions is recommended prior to rollout, as the system can reinstate free rows if users attempt removal while conditions remain met.

## Configuration Steps

1. Navigate to Pricing Rules and create a new rule
2. Provide a descriptive name (e.g., "Buy AeroBook Sleeve, Get One Free")
3. Set "Apply On" to Item Code and specify the qualifying item
4. Change "Price or Product Discount" to "Product Discount"
5. Enter minimum quantity as 1
6. In Product Discount settings:
   - Toggle "Same Item" if the purchased product is also free
   - Otherwise, select the promotional item
   - Set Free Qty to 1
7. Configure applicability, party restrictions, validity dates, and priority
8. Save and activate

## Testing Process

1. Create a Quotation or Sales Order
2. Choose an eligible customer and add the qualifying item
3. Input the minimum qualifying quantity
4. Apply Pricing Rules if needed
5. Verify ERPNext generates the free row with zero pricing

Stock indicators appear as colored dots—green indicates availability, red signals shortage.

## Offer Variations

| Scenario | Setup |
|----------|-------|
| Same item promotion | Enable Same Item; set Free Qty |
| Different item promotion | Disable Same Item; select promotional item |
| Bulk quantity offers | Adjust minimum quantity and Free Qty |
| Item Group offers | Apply to Item Group; test all eligible items |

## Stock Considerations

Zero-cost promotional items still require inventory allocation. Verify sufficient stock exists and include free rows in downstream Delivery Notes and inventory tracking. If stock shortages prevent document submission, replenish inventory or modify the offer rather than deleting the free row.

## Rule Interactions

Review conflicting Pricing Rules, Promotional Schemes, and Coupon Codes. Establish clear validity windows and priority levels; test whether concurrent offers should stack or remain mutually exclusive.

## Common Issues and Solutions

| Issue | Resolution |
|-------|-----------|
| Free row absent | Confirm rule activation and condition matching |
| Free row reappears after removal | Qualifying condition persists; adjust transaction or disable rule |
| Insufficient stock error | Verify free item stock and warehouse selection |
| Multiple promotions active | Review rule overlap and priority settings |
| Wrong item marked free | Check Same Item setting and promotional item selection |

## FAQ

**Can promotional items differ from purchased items?**
Yes—disable Same Item and select an alternative product.

**Is Buy 2 Get 1 Free possible?**
Yes—set minimum quantity to 2 and Free Qty to 1.

**Do free items appear on delivery documents?**
Yes, when the mapped document transfers the promotional row.

**Can free items have non-zero pricing?**
Product Discount rules enforce zero rates. Use Price Discount rules for reduced, non-zero pricing.

## Related Resources

- [Pricing Rule](/erpnext/pricing-rule)
- [Promotional Scheme](/erpnext/promotional-scheme)
- [Applying a Discount](/erpnext/applying-discount)
- [Sales Order](/erpnext/sales-order)
- [Delivery Note](/erpnext/delivery-note)
