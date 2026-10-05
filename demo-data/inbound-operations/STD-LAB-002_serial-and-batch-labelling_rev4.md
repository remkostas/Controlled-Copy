---
document_id: STD-LAB-002
title: Serial and Batch Labelling Standard
revision: 4
status: approved
effective_from: 2025-09-01
site: all
process: inbound_receiving
applicable_roles: [warehouse_operator, shift_lead]
owner_role: process_owner
supersedes: STD-LAB-002 rev 3
---
# STD-LAB-002 Serial and Batch Labelling Standard (Revision 4)

> Synthetic demonstration document. Kestrova Components GmbH is a fictional company. Not for operational use.

## 1 Purpose

This standard defines how incoming material is identified by batch number or serial number and what to do when labels are missing or unreadable.

## 2 Which material needs a batch or serial number

The material master defines whether a material is batch-managed or serial-managed. The WMS shows the flag on the receiving screen. Material without either flag needs no batch or serial number.

## 3 Label check

The supplier label must match the delivery note in material number, quantity and batch or serial number. If the label and the delivery note do not match, do not post the goods receipt; move the handling unit to the blocked area B-02 and inform the shift lead.

## 4 Missing batch number

If the material is batch-managed and no batch number is visible on the label, do not post the goods receipt. Move the handling unit to the blocked area B-02 and inform the shift lead. The shift lead contacts the supplier for the batch number.

## 5 Unreadable barcode

If a barcode cannot be scanned, the number may be entered manually only by a shift lead, with a second person checking the entry against the label (four-eyes check). Warehouse operators do not enter batch or serial numbers manually.

## 6 Serial numbers

Every serial number must be scanned individually. Do not post a serial-managed material with a quantity greater than the number of scanned serial numbers.
