---
document_id: SOP-INB-001
title: Inbound Receiving Procedure
revision: 3
status: approved
effective_from: 2026-01-01
site: HAM-01
process: inbound_receiving
applicable_roles: [warehouse_operator, shift_lead]
owner_role: process_owner
supersedes: SOP-INB-001 rev 2
---
# SOP-INB-001 Inbound Receiving Procedure (Revision 3)

> Synthetic demonstration document. Kestrova Components GmbH is a fictional company. Not for operational use.

## 1 Purpose

This procedure describes how inbound deliveries are received at the Hamburg distribution centre (site HAM-01), from the arrival of the truck to the goods receipt posting in the warehouse management system (WMS).

## 2 Scope

This procedure applies to all inbound deliveries of purchased material at HAM-01. Customer returns and transfers between sites are out of scope.

## 3 Responsibilities

- The warehouse operator unloads, checks and counts the delivery and posts the goods receipt.
- The shift lead confirms deviations, decides on blocked deliveries and is the first contact for the warehouse operator.
- The process owner (inbound) maintains this procedure.

## 4 Procedure

### 4.1 Arrival and document check

Check that a delivery note is present and that it refers to an open purchase order. If the delivery note is missing or refers to an unknown purchase order, do not unload. Inform the shift lead.

### 4.2 Quantity check and tolerance

Count every delivery line before posting. Compare the counted quantity with the quantity on the delivery note and on the purchase order.

Deviations of up to 2% of the ordered quantity or 2 units, whichever is smaller, are posted as counted with a note in the goods receipt.

Larger deviations must not be posted until the shift lead has confirmed a recount. After the confirmation, post the counted quantity, never the ordered quantity, and record the reason for the deviation. The shift lead informs purchasing about every confirmed short or over delivery.

### 4.3 Quality-managed material

Material that is flagged as quality-managed in the material master is always posted to quality inspection stock, regardless of the supplier's certification status. Only the QA inspector releases quality inspection stock to unrestricted stock.

### 4.4 Batch-managed material

For batch-managed material, the batch number from the supplier label must be recorded before the goods receipt is posted. If no batch number is visible, follow STD-LAB-002.

### 4.5 Goods receipt posting

Post the goods receipt in the WMS against the purchase order line. If the WMS shows an error code, follow GUIDE-WMS-003. Never bypass a WMS error by posting against a different purchase order line.

## 5 Condition check

### 5.1 General

Inspect every handling unit for damage before it is moved into the warehouse. Damage that is found later cannot be claimed against the carrier.

### 5.2 Product damage

If the product itself is visibly damaged, follow WI-QUA-004.

### 5.3 Damaged outer packaging

If the outer packaging of a handling unit shows visible damage, refuse the delivery and note the reason on the delivery note before the driver leaves.

## 6 Putaway

After posting, move the material to the storage location proposed by the WMS. Material in quality inspection stock or blocked stock stays in the inspection area until it is released.

## 7 Records

The goods receipt document, the delivery note and any photos are the records of the receipt. They are kept in the WMS for ten years.

## 8 Change history

| Revision | Effective | Change |
| :--- | :--- | :--- |
| 3 | 2026-01-01 | Quality-managed material always goes to quality inspection stock; tolerance reduced to 2% or 2 units |
| 2 | 2024-03-01 | Direct posting for certified suppliers; tolerance 5% |
