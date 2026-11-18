# Paykings merchant application form: field reference

Source: 7 screenshots supplied by the user on 2026-11-18 (the second batch repeats the first six and adds Business Owner).
`*` = required (red asterisk in the form). Dropdown option lists were not visible ("Select..."), so they are unknown.
No merchant values are recorded here on purpose.

Mapping column: the current export column (45-column template), or **GAP** when there is none.

## 1. Business Information
| Field | Req | Format / note | Current column |
|---|---|---|---|
| Legal Business Name | * | text | Business Name |
| Business Start Date | * | date picker shown as dd/mm/yyyy (browser locale) | business_start_date (we store MM/DD/YYYY: convert when typing) |
| Business Description | * | free text: business and products/services | business_description / products_and_services_description |
| Business Advertising | * | free text: how the business advertises | **GAP** |
| Business Phone | * | `408-915-0817` style (no +1) | Phone (we store `+1 (408) 915-0817`: strip when typing) |
| Business Email | * | email | Email |
| Customer Service Phone | * | phone | **GAP** (usually same as Business Phone) |
| Customer Service Email | * | email | **GAP** (usually same as Business Email) |
| Website | conditional | must include `http://` or `https://`; required if accepting online payments | website |

## 2. Address Information
| Field | Req | Format / note | Current column |
|---|---|---|---|
| Business Address (Legal Address) | * | address autocomplete, min 3 chars | Street Address + City + State + ZIP |
| Suite/Apt/Unit | | text | **GAP** (currently inside Street Address, e.g. "UNIT 312") |
| Is the DBA different from Legal Info? | | checkbox | derive: DBA Name present and different from Business Name |
| Building Type | * | dropdown | **GAP** |
| Building Ownership | * | dropdown | **GAP** |
| Building Zoning | * | dropdown | **GAP** |
| Building Square Footage | * | dropdown | **GAP** |

## 3. Fulfillment Information
| Field | Req | Format / note | Current column |
|---|---|---|---|
| Is this a service only business? | | checkbox | **GAP** |
| How is Inventory Stored? | * | dropdown | **GAP** |
| Do you use a 3rd party fulfillment center? | | checkbox | **GAP** |
| Fulfillment Time Frame | * | dropdown; time to prepare to ship | **GAP** |
| Delivery Time Frame | * | dropdown; time to arrive / service rendered | **GAP** |
| Do you accept recurring payments? | | checkbox; subscriptions / repeat billing | **GAP** |
| When are customers charged? | * | dropdown | **GAP** |
| Refund Policy | * | free text: returns, refunds, cancellations | refund_policy |

## 4. Sales Metrics
| Field | Req | Format / note | Current column |
|---|---|---|---|
| Public Sales % | | number; Public + B2B must total 100 | **GAP** |
| B2B Sales % | | number | **GAP** |
| National Sales % | | number; National + International must total 100 | **GAP** |
| International Sales % | | number | **GAP** |
| Card Swipe % | | number; Swipe + Keyed + Internet must total 100 | card_present_percentage |
| Card Keyed % | | number | keyed_percentage |
| Card Internet % | | number | ecommerce_percentage |
| Monthly Processing Volume | * | USD, plain number | monthly_card_volume |
| Average Transaction Amount | * | USD | average_ticket |
| Maximum Transaction Amount | * | USD | high_ticket |
| Do you currently accept credit cards? | | checkbox | **GAP** |
| Were you previously terminated from processing? | | checkbox | **GAP** |

## 5. Banking Information
| Field | Req | Format / note | Current column |
|---|---|---|---|
| Bank Name | * | text | **GAP** |
| Bank Account Number | * | digits; entered twice (confirm field) | **GAP** (sensitive) |
| Routing Number | * | 9 digits | routing_number |

## 6. Business MCC and Tax Info
Banner (partly cut off): application is declined unless the business is registered in the United States and the signer holds US citizenship.

| Field | Req | Format / note | Current column |
|---|---|---|---|
| Business Type | * | dropdown | Business Entity Type (option names unknown; ours are snake_case values) |
| Industry (MCC Category) | * | dropdown | **GAP** |
| MCC Code | * | dropdown, depends on Industry | mcc |
| Tax Id Type (EIN/SSN) | * | dropdown: EIN or SSN | **GAP** (derive: EIN present -> EIN) |
| Federal Tax ID (EIN) | * | `12-3456789` | EIN / Notes (EIN mixed with notes today) |

## 7. Business Owner Information (repeatable: "Add Another Owner")
| Field | Req | Format / note | Current column |
|---|---|---|---|
| First Name | * | text | First Name |
| Last Name | * | text | Last Name (no middle-name field: "James B" style needs a decision) |
| Title | * | dropdown | **GAP** (schema has owner `title`, not exported) |
| Ownership | * | %, default 100 | ownership_percentage |
| Email | * | email | **GAP** (owner email; currently only business Email) |
| Phone | * | phone | **GAP** (owner phone) |
| Street Address | * | text | **GAP** (owner home address; ours is business address) |
| Suite/Apt/Unit | | text | **GAP** |
| City | * | text | **GAP** |
| Country | * | dropdown | **GAP** |
| State | * | dropdown | **GAP** |
| ZIP / Postal Code | * | text | **GAP** |
| SSN | * | full SSN `123-45-6789` | ssn_last4 only (tool deliberately stores last 4) |
| Date of Birth | * | date picker dd/mm/yyyy | date_of_birth (MM/DD/YYYY) |
| Driver License Number | | text | **GAP** (today put in EIN / Notes) |
| Driver License Expiration | | date | **GAP** (today put in EIN / Notes) |
| Driver License State | | dropdown | **GAP** |
| Passport Number | | text | **GAP** |
| Passport Expiration | | date | **GAP** |

## Decisions from the owner (2026-11-18)
- Full SSN and bank account number may be stored, as long as the exported files are only accessible on the owner's own computer.
- Building Type options include Residential, Industrial, etc. (full list not given).
- Owner Title: only "Owner".
- Business Type in the MCC/Tax step = business entity type.

## Implemented
- `preview_tool/paykings_layout.json`: 70-column CSV in form order (merchant_id, Status, the 7 steps, Notes).
- Preview tool and viewer.html render that layout with date hints, masked SSN/bank account, and the 100% / website checks.
- Merchant Notebook core (schema.json, CLI, EXPORT CSV) is unchanged.

## Takeaways for improving data entry
1. Order the export / preview by these 7 form steps so values can be copied top to bottom.
2. Add the GAP columns, at least the required ones: Business Advertising, Customer Service Phone/Email, Suite, Building x4, Inventory/Fulfillment/Delivery/Charge timing, Bank Name, Industry, Tax Id Type, owner Title/Email/Phone/home address/Country.
3. Split EIN out of "EIN / Notes"; add Driver License number/expiry/state instead of notes.
4. Phone: also provide the form's `XXX-XXX-XXXX` style. Dates: form shows dd/mm/yyyy in this browser; keep MM/DD/YYYY stored, note the conversion.
5. Validation rules to add: Public+B2B=100, National+International=100, Swipe+Keyed+Internet=100; website must start with http(s):// when Card Internet % > 0.
6. Open decisions for the owner: full SSN and bank account number (the tool currently refuses to store full SSN; storing them raises the sensitivity of every file); dropdown option values (need screenshots of the opened dropdowns).
