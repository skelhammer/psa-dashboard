# SuperOps GraphQL API Schema Reference

Discovered via introspection queries against the live API.

## Query Entry Points

| Query | Input Type | Returns |
|-------|-----------|---------|
| `getTicketList` | `ListInfoInput!` | `TicketList` |
| `getTechnicianList` | `ListInfoInput!` | `TechnicianList` |
| `getClientList` | `ListInfoInput!` | `ClientList` |
| `getClientContractList` | `ListInfoInput` | `ClientContractList` |
| `getTicketConversationList` | `TicketIdentifierInput!` | `[TicketConversation]` |

---

## Ticket

All fields are scalars or JSON scalars (no sub-selection needed on JSON fields).

| Field | Type | Notes |
|-------|------|-------|
| `ticketId` | ID! | Internal numeric ID |
| `displayId` | String! | Human-readable ID (e.g. "TK-1234") |
| `subject` | String! | |
| `source` | String! | Email, Portal, etc. |
| `client` | JSON | `{accountId, name, ...}` |
| `site` | JSON | |
| `requester` | JSON | `{userId, name, ...}` |
| `additionalRequester` | JSON | |
| `followers` | JSON | |
| `techGroup` | JSON | `{groupId, name}` |
| `technician` | JSON | `{userId, name}` |
| `status` | String | Open, Resolved, Closed, Customer Replied, etc. |
| `approvalStatus` | String | |
| `priority` | String | Critical, High, Medium, Low |
| `impact` | String | |
| `urgency` | String | |
| `category` | String | |
| `subcategory` | String | |
| `cause` | String | |
| `subcause` | String | |
| `resolutionCode` | String | |
| `sla` | JSON | `{identity, id, name, ...}` |
| `createdTime` | String | ISO datetime |
| `updatedTime` | String | ISO datetime |
| `firstResponseDueTime` | String | ISO datetime |
| `firstResponseTime` | String | ISO datetime |
| `firstResponseViolated` | Boolean | |
| `resolutionDueTime` | String | ISO datetime |
| `resolutionTime` | String | ISO datetime |
| `resolutionViolated` | Boolean | |
| `customFields` | JSON | UDF fields |
| `requestType` | String | Incident, Service Request, etc. |
| `worklogTimespent` | String | Minutes as string (e.g. "100.00") |

---

## Client

| Field | Type | Notes |
|-------|------|-------|
| `accountId` | ID! | |
| `name` | String! | |
| `stage` | String! | Active, Prospect, etc. |
| `status` | String | Paid, Unpaid, null |
| `emailDomains` | [String] | |
| `accountManager` | JSON | |
| `primaryContact` | JSON | |
| `secondaryContact` | JSON | |
| `hqSite` | JSON | |
| `technicianGroups` | JSON | |
| `customFields` | JSON | See UDF fields below |
| `createdTime` | String | ISO datetime |
| `updatedTime` | String | ISO datetime |

### Client Custom Fields (customFields JSON)

| Key | Label in SuperOps | Example Values |
|-----|-------------------|----------------|
| `udf1select` | Plan | Plan names (configured in config.yaml) |
| `udf11select` | Profit Type | "For Profit", "Non-Profit" |
| `udf12num` | Account Number | Numeric string |

Note: Many clients (especially older/unconfigured ones) have `customFields: null`.

---

## ClientContractList

| Field | Type | Notes |
|-------|------|-------|
| `clientContracts` | [ClientContract!] | NOT `contracts` |
| `listInfo` | ListInfo | |

## ClientContract

| Field | Type | Notes |
|-------|------|-------|
| `contractId` | ID | |
| `client` | JSON! | `{accountId, name, ...}` (JSON scalar, no sub-selection) |
| `contract` | Contract! | Object (needs sub-selection) |
| `startDate` | String! | |
| `endDate` | String | |
| `contractStatus` | ClientContractStatus! | Enum |

### ClientContractStatus (Enum)
- `DRAFT`
- `ACTIVE`
- `INACTIVE`

## Contract (nested inside ClientContract)

| Field | Type | Notes |
|-------|------|-------|
| `contractId` | ID! | |
| `name` | String | |
| `description` | String | |
| `contractType` | ContractType! | Enum |
| `billableContract` | BillableContract | Pricing details |

### ContractType (Enum)
- `SERVICE` (maps to "managed")
- `USAGE` (maps to "hourly")
- `ONE_TIME` (maps to "flat_rate")
- `TIME_AND_MATERIAL` (maps to "hourly")

## BillableContract

| Field | Type | Notes |
|-------|------|-------|
| `contractId` | ID! | |
| `chargeItem` | JSON! | |
| `quantityCalculationType` | ContractQuantityCalculationType! | |
| `sellingPriceCalculationType` | ContractSellingPriceCalculationType! | |
| `provisionRule` | JSON | |
| `sellingPriceOverridden` | Boolean | |
| `sellingPrice` | PricingModel | |
| `discountRate` | String | |
| `frequencyType` | ContractFrequencyType! | |
| `includedItems` | [IncludedItem!] | |
| `billableSiteType` | BillableSiteType! | |
| `sites` | [Site!] | |
| `recurringContract` | RecurringContract | |
| `redeemableContract` | RedeemableContract | |
| `perpetualContract` | PerpetualContract | |
| `changes` | [Change!] | |
| `project` | JSON | |
| `blockItemsInfo` | [BlockItemInfo] | |

---

## TicketConversation

| Field | Type | Notes |
|-------|------|-------|
| `conversationId` | ID! | |
| `workItem` | JSON | |
| `content` | String | HTML content |
| `time` | String! | ISO datetime |
| `user` | JSON | `{userId, name, email}` (JSON scalar, no sub-selection!) |
| `toUsers` | [RecipientInfo] | |
| `ccUsers` | [RecipientInfo] | |
| `bccUsers` | [RecipientInfo] | |
| `attachments` | [Attachment] | |
| `type` | TicketConversationType! | Enum |

### TicketConversationType (Enum)
- `DESCRIPTION` (initial ticket description)
- `REQ_REPLY` (requester/customer reply)
- `REQ_NOTIFICATION` (notification to requester)
- `TECH_REPLY` (technician reply)
- `TECH_NOTIFICATION` (notification to tech)

---

## Technician (from TechnicianList.userList)

| Field | Type | Notes |
|-------|------|-------|
| `userId` | ID | |
| `name` | String | Full name as single string |

---

## ListInfo (pagination)

| Field | Type |
|-------|------|
| `page` | Int |
| `pageSize` | Int |
| `hasMore` | Boolean |
| `totalCount` | Int |

---

## ListInfoInput

| Field | Type | Notes |
|-------|------|-------|
| `page` | Int | |
| `pageSize` | Int | Max 100 |
| `condition` | Condition | Filter conditions |
| `sort` | [SortInput] | Sort order |

### Condition format
```json
{
  "attribute": "status",
  "operator": "includes",
  "value": ["Open", "In Progress"]
}
```

Compound conditions:
```json
{
  "joinOperator": "AND",
  "operands": [condition1, condition2]
}
```
