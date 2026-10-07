---
document_id: GUIDE-WMS-003
title: Goods Receipt Error Guide
revision: 1
status: approved
effective_from: 2026-02-01
site: HAM-01
process: inbound_receiving
applicable_roles: [warehouse_operator, shift_lead, wms_key_user]
owner_role: wms_key_user
---
# GUIDE-WMS-003 Goods Receipt Error Guide (Revision 1)

> Synthetic demonstration document. Kestrova Components GmbH is a fictional company. Not for operational use.

## 1 How to use this guide

Look up the error code shown by the WMS. Follow the action. Never override an error with a manual posting. If the code is not listed in this guide, stop and contact the WMS key user (see MATRIX-ESC-001).

## 2 Error codes

### GR-101 Purchase order line closed

Meaning: the purchase order line is already fully received or closed by purchasing.
Action: do not post. Move the handling unit to the over-delivery area OD-01 and inform purchasing.
Never: post against another open line of the same purchase order.

### GR-204 Quantity above open order quantity

Meaning: the scanned quantity is higher than the open quantity of the purchase order line.
Action: post only the open quantity after the shift lead has confirmed the count. Move the excess units to the over-delivery area OD-01 and inform purchasing.
Never: increase the purchase order quantity yourself.

### GR-310 Material master missing for the site

Meaning: the material has no material master data for HAM-01.
Action: do not post. Move the handling unit to the blocked area B-02 and inform the WMS key user.
Never: post the material under a similar material number.

### GR-415 Storage location blocked

Meaning: the proposed storage location is blocked for inventory or maintenance.
Action: ask the shift lead for an alternative storage location; the shift lead assigns it in the WMS.
Never: put the material away in an unrecorded location.

### GR-512 Duplicate receipt warning

Meaning: a goods receipt with the same delivery note number already exists.
Action: stop and check the existing goods receipt with the shift lead before posting again.
Never: confirm the warning without checking.
