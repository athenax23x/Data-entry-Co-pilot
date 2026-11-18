"""Where every column of the Paykings form lives in a v2 record (schema_v2.json).

Paths use the field-spec notation of fields.py ('owners[]' means the primary owner, owners[0]).
tests/test_schema_v2.py checks that this map covers exactly the columns of preview_tool/paykings_layout.json
and that every path exists in a blank v2 record.
"""
from __future__ import annotations

OWNER = "personal_information.owners[]."

# Paykings column -> v2 field spec. None means the value is derived from the record, not stored as a field.
COLUMN_TO_SPEC = {
    # 1. Business Information
    "Legal Business Name": "business_information.legal_business_name",
    "Business Start Date": "business_information.business_start_date",
    "Business Description": "business_information.business_description",
    "Business Advertising": "business_information.advertising_methods",
    "Business Phone": "contact_information.phone",
    "Business Email": "contact_information.email",
    "Customer Service Phone": "contact_information.customer_service_phone",
    "Customer Service Email": "contact_information.customer_service_email",
    "Website": "business_information.website",
    # 2. Address Information
    "Business Address": "business_address.street_address",
    "Business Suite/Apt/Unit": "business_address.suite",
    "Business City": "business_address.city",
    "Business State": "business_address.state",
    "Business ZIP": "business_address.zip",
    "DBA Different From Legal Info": "business_information.dba_different_from_legal",
    "DBA Name": "business_information.dba_name",
    "Building Type": "business_address.building_type",
    "Building Ownership": "business_address.building_ownership",
    "Building Zoning": "business_address.building_zoning",
    "Building Square Footage": "business_address.building_square_footage",
    # 3. Fulfillment Information
    "Service Only Business": "fulfillment_information.service_only_business",
    "How Is Inventory Stored": "fulfillment_information.inventory_storage",
    "Uses 3rd Party Fulfillment Center": "fulfillment_information.uses_third_party_fulfillment",
    "Fulfillment Time Frame": "fulfillment_information.fulfillment_time_frame",
    "Delivery Time Frame": "fulfillment_information.delivery_time_frame",
    "Accepts Recurring Payments": "fulfillment_information.accepts_recurring_payments",
    "When Are Customers Charged": "fulfillment_information.when_customers_charged",
    "Refund Policy": "business_information.refund_policy",
    # 4. Sales Metrics
    "Public Sales %": "processing_information.public_sales_percentage",
    "B2B Sales %": "processing_information.b2b_sales_percentage",
    "National Sales %": "processing_information.national_sales_percentage",
    "International Sales %": "processing_information.international_sales_percentage",
    "Card Swipe %": "processing_information.card_present_percentage",
    "Card Keyed %": "processing_information.keyed_percentage",
    "Card Internet %": "processing_information.ecommerce_percentage",
    "Monthly Processing Volume": "processing_information.monthly_card_volume",
    "Average Transaction Amount": "processing_information.average_ticket",
    "Maximum Transaction Amount": "processing_information.high_ticket",
    "Currently Accepts Credit Cards": "processing_information.currently_accepts_cards",
    "Previously Terminated From Processing": "processing_information.previously_terminated",
    # 5. Banking Information
    "Bank Name": "banking_information.bank_name",
    "Bank Account Number": "banking_information.account_number",
    "Routing Number": "processing_information.routing_number",
    # 6. Business MCC and Tax Info
    "Business Type": "business_entity_type",
    "Industry (MCC Category)": "processing_information.industry_category",
    "MCC Code": "processing_information.mcc",
    "Tax Id Type": "tax_id_type",
    "Federal Tax ID (EIN)": "ein",
    # 7. Business Owner 1
    "Owner First Name": OWNER + "first_name",
    "Owner Last Name": OWNER + "last_name",
    "Owner Title": OWNER + "title",
    "Ownership %": OWNER + "ownership_percentage",
    "Owner Email": OWNER + "email",
    "Owner Phone": OWNER + "phone",
    "Owner Street Address": OWNER + "street_address",
    "Owner Suite/Apt/Unit": OWNER + "suite",
    "Owner City": OWNER + "city",
    "Owner Country": OWNER + "country",
    "Owner State": OWNER + "state",
    "Owner ZIP": OWNER + "zip",
    "SSN": OWNER + "ssn",
    "Date of Birth": OWNER + "date_of_birth",
    "Driver License Number": OWNER + "driver_license_number",
    "Driver License Expiration": OWNER + "driver_license_expiration",
    "Driver License State": OWNER + "driver_license_state",
    "Passport Number": OWNER + "passport_number",
    "Passport Expiration": OWNER + "passport_expiration",
    # Notes
    "Notes": "notes",
}

# CSV columns that are not form fields: taken from the record itself.
RECORD_COLUMNS = {"merchant_id": "merchant_id", "Status": "record_status"}

# Columns the user decided not to collect. They stay in the CSV as blank columns, but the UI does not show them
# and Claude is not asked for them.
SKIPPED_COLUMNS = frozenset({
    "Building Type", "Building Ownership", "Building Zoning", "Building Square Footage",                # address step
    "Service Only Business", "How Is Inventory Stored", "Uses 3rd Party Fulfillment Center",
    "Fulfillment Time Frame", "Delivery Time Frame", "Accepts Recurring Payments",
    "When Are Customers Charged", "Refund Policy",                                                      # whole fulfillment step
    "Industry (MCC Category)", "MCC Code",
})
SKIPPED_SPECS = frozenset(COLUMN_TO_SPEC[c] for c in SKIPPED_COLUMNS if COLUMN_TO_SPEC.get(c))

# Fields that may be stored locally but must never leave the laptop (no cloud AI, no logs).
SENSITIVE_SPECS = frozenset({
    OWNER + "ssn", OWNER + "ssn_last4", OWNER + "driver_license_number", OWNER + "passport_number",
    "banking_information.account_number",
})
