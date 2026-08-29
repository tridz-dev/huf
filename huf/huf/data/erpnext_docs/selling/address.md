---
title: "Address"
source_url: "https://docs.frappe.io/erpnext/address"
section: selling
---

An **Address** stores a physical or mailing location and can be linked to a [Customer](/erpnext/customer), [Supplier](/erpnext/supplier), Lead, shareholder, sales partner, [Warehouse](/erpnext/warehouse), or Company. One party can have several billing, shipping, office, and branch addresses.

Keep locations as linked Address records instead of creating duplicate Customers or Suppliers for each site.

![Billing Address for Summit Digital Stores with preferred billing status.](https://novacompanies.m.frappe.cloud/files/address-details.png)

## Before you begin

Confirm:

- the party or parties to link;
- whether the location is used for billing, shipping, or another purpose;
- which address should be preferred;
- the correct country and postal format; and
- any regional tax identifiers that belong to the location.

The selected Country determines the country-specific [Address Template](/erpnext/address-template) used when ERPNext renders the address.

## Create an Address

1. Open **CRM > Address** and select **Add Address**.
2. Enter the **Address Title** and select the **Address Type**.
3. Enter Address Line 1, optional Address Line 2, City/Town, County, State/Province, Country, and Postal Code.
4. Add phone, fax, email, or tax category when required.
5. Set preferred billing or shipping status when this is the normal location.
6. Add the party link.
7. Save the Address.

When created from a party, ERPNext normally derives a title such as `Party Name-Address Type`. A standalone Address needs a clear manual title.

## Create an Address from a party

1. Open the Customer or Supplier.
2. Select **Address & Contact**.
3. Select **New Address**.
4. Complete the location and save.

ERPNext adds the originating party link automatically. This route reduces link errors and is recommended for normal onboarding.

## Alternative ways to create Addresses

- Use [Data Import](/erpnext/data-import) for a controlled batch and include the correct Dynamic Link rows.
- Create an Address from a sales or purchase transaction when permitted.
- Use an approved integration when another system owns delivery locations.
- Create a standalone location and link it later.

## Important fields and what they mean

| Field                                 | What it controls                                                         |
| ---------------------------------------- | ---------------------------------------------------------------------------- |
| **Address Title**                     | Searchable label and part of the generated Address ID                    |
| **Address Type**                      | Classifies Billing, Shipping, Office, Personal, or another supported use |
| **Address Line 1 / 2**                | Street, building, suite, floor, or unit information                      |
| **City/Town, County, State/Province** | Regional location components used by templates and tax logic             |
| **Country**                           | Selects the country-specific Address Template and regional fields        |
| **Postal Code**                       | ZIP, PIN, or other postal identifier                                     |
| **Preferred Billing Address**         | Makes the Address the normal billing selection for the linked party      |
| **Preferred Shipping Address**        | Makes the Address the normal shipping selection                          |
| **Disabled**                          | Prevents new selection while retaining history                           |
| **Links**                             | Connects the Address to one or more supported parties or masters         |
| **Is Your Company Address**           | Identifies a facility belonging to your own Company                      |

## Link an Address to multiple parties

Use **Links** to review every party connected to the Address. Add another link only when the same physical location genuinely serves multiple parties.

![Links menu showing the Address connected to Summit Digital Stores.](https://novacompanies.m.frappe.cloud/files/address-linked-parties.png)

Do not link unrelated Customers merely because they share a building. Separate Address records preserve independent primary flags and tax details.

## Preferred billing and shipping addresses

A preferred billing Address can be fetched into [Sales Orders](/erpnext/sales-order), [Sales Invoices](/erpnext/sales-invoice), [Delivery Notes](/erpnext/delivery-note), purchase documents, and other supported transactions. The preferred shipping Address supplies the normal delivery destination.

One location may be both preferred billing and preferred shipping. For Summit Digital Stores, the Harbor Avenue office is billing and the Meridian Parkway warehouse is shipping.

Users can select another linked Address on a transaction. Submitted documents preserve the address text they used.

## Regional tax details

Regional apps can add fields and validation to Address. For India GST, store GSTIN and GST State on the Address—not only on the Customer or Supplier—because one party can have registrations in several states. Sales documents then fetch the registration belonging to the selected location.

For your own facilities, enable **Is Your Company Address** and link the [Company](/erpnext/company). Verify regional requirements against the installed compliance app and current law.

## Save and next steps

Address is saved rather than submitted. After saving:

- verify its Links menu;
- confirm preferred billing and shipping flags;
- select it on a test [Quotation](/erpnext/quotation) or transaction;
- check the formatted result; and
- disable obsolete locations instead of deleting history.

## Address types and availability

| Type or state       | Use                                           |
| ---------------------- | ------------------------------------------------ |
| **Billing**         | Invoice and statement location                |
| **Shipping**        | Delivery or receiving location                |
| **Office**          | General business location                     |
| **Preferred**       | Normal automatic selection for a linked party |
| **Disabled**        | Retained but unavailable for new selections   |
| **Company Address** | One of your organization's facilities         |

## Troubleshooting

| Problem                                | What to check                                                             |
| ------------------------------------------ | -------------------------------------------------------------------------- |
| Wrong Address appears on a transaction | Review party links, preferred flags, and the selected transaction Address |
| Address formatting is wrong            | Check Country and the applicable Address Template                         |
| Address cannot be found                | Search the generated title and verify it is not disabled                  |
| Import creates unlinked Addresses      | Correct Link DocType and Link Name child rows                             |
| Regional tax fields are missing        | Check Country, installed regional app, and company configuration          |

## Frequently asked questions

### Can one party have several billing or shipping Addresses?

Yes. Mark the normal choice as preferred and select alternatives per transaction.

### Can an Address link to multiple Customers or Suppliers?

Yes, when the location is genuinely shared.

### Should I edit an old Address after it changes?

For a minor correction, edit it. For a materially different location, create a new Address and disable the obsolete one.

### Does editing an Address change submitted documents?

No. Submitted documents preserve the address text stored at posting.

### Where should regional tax registration be stored?

Use the Address when the registration belongs to a location, following the relevant regional app.

## Related topics

- [Customer](/erpnext/customer)
- [Contact](/erpnext/contact)
- [Address Template](/erpnext/address-template)
- [Company](/erpnext/company)
