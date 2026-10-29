# Advertising Site Rental Management — Functional Requirements

## 1. System Purpose

The system will manage **advertising sites that are rented to customers**. A site can represent any type of advertising space, including:

- Billboard
- Wallscape
- Rooftop
- Digital screen
- Building façade
- Other advertising spaces

**Site Type must be configurable by authorized staff**, so new types can be added without modifying the software.

The system will manage the complete lifecycle:

**Site → Availability → Booking Request → Quotation → Confirmed Booking → Invoicing/Payments → Tracking → Booking Completion**

It will also manage the company's **lease obligations to landlords** for sites that are not owned by the company.

---

## 2. Site Management

The system shall allow authorized staff to create and manage advertising sites.

Each site shall contain:

- Unique site code/ID
- Site name
- Site type
- Address/location
- Optional latitude and longitude
- Optional map link
- Dimensions and physical specifications
- Site photographs
- Standard/default rental price
- Default billing frequency
- Ownership type:
  - Owned
  - Leased
- Landlord/owner, where applicable
- Active/inactive status
- Maintenance status
- Internal notes

### Site Types

Site types shall be configurable from the system, for example:

- Billboard
- Wallscape
- Rooftop
- Digital Screen
- Other

Staff must be able to add new site types without changing the application code.

### Site status

The system shall support:

- **Available**
- **Reserved**
- **Rented**
- **Maintenance**
- **Inactive**

The system should derive **Reserved/Rented/Available** from the site's booking schedule where possible rather than relying entirely on manual status changes.

---

## 3. Site Availability & Scheduling

The system shall maintain an availability schedule for every active site.

The schedule shall:

- Display existing reserved and confirmed booking periods.
- Display the exact start and end dates of occupied periods.
- Show available periods.
- Support different booking periods for different sites within the same customer booking.
- Prevent overlapping **confirmed bookings** for the same site.
- Warn staff about conflicts when creating or revising quotations.
- Allow a customer to request a site for a future period even when the site is currently occupied, provided it is available during the requested period.

### Customer visibility

Customers shall be able to see:

- Active sites
- Site type and details
- Site photographs
- Available dates
- Reserved/booked date ranges

Customers shall **not** see:

- The name of the customer who has reserved/booked the site
- Another customer's quotation
- Another customer's booking details
- Another customer's pricing
- Internal information

---

## 4. Customer & Booking Request

Customers shall be able to browse active sites through the customer portal and submit a **Booking Request**.

A Booking Request may contain:

- One or multiple sites
- Requested start date and end date for each site
- Different dates for different sites
- Customer comments/requirements

The system shall check the requested dates against site availability.

A Booking Request shall be available to staff for review and quotation preparation.

Staff shall also be able to create a Booking Request or quotation directly on behalf of a customer.

---

## 5. Quotation Management

The Booking Request shall lead to a customer quotation.

Where possible, the system shall use and extend **Odoo's existing Sales Quotation (`sale.order`) functionality** rather than creating a completely separate quotation system.

### Staff shall be able to:

- Review the customer's request.
- Add or remove sites.
- Change requested dates.
- Set different dates for different sites.
- Change rental prices.
- Apply discounts.
- Apply taxes.
- Add additional charges.
- Add quotation terms and conditions.
- Add internal notes.
- Modify the quotation before sending.
- Send or resend the quotation.
- Create a quotation directly without a customer request.

### Customer shall be able to:

- View the quotation.
- Review sites and rental periods.
- Review pricing, discounts and taxes.
- Accept the quotation.
- Reject the quotation.
- Request a quotation revision.

A customer **cannot directly modify the quotation**.

---

## 6. Confirmed Booking

When a customer accepts a quotation, staff shall be able to convert it into a **Confirmed Booking**.

Staff shall also be able to create a confirmed booking directly for any customer without going through the quotation process.

A booking shall support:

- Customer
- Multiple sites
- Individual booking lines for each site
- Start date per site
- End date per site
- Rental price per site
- Billing frequency
- Discounts
- Taxes
- Additional charges
- Contract/reference number
- Terms and conditions
- Attachments/documents
- Internal notes

### Booking lifecycle

```text
Booking Request
      ↓
Quotation
      ↓
Quotation Sent
      ├── Rejected
      ├── Revision Requested
      │       ↓
      │   Revised Quotation
      │
      └── Accepted
             ↓
      Confirmed Booking
             ↓
          Active
             ↓
         Completed
```

A confirmed booking may also be cancelled by staff.

### Booking modification/cancellation

Customers **cannot directly modify or cancel a confirmed booking**.

The portal shall provide:

- Request Booking Change
- Request Cancellation

These requests shall be sent to staff for review and action.

---

## 7. Customer Invoicing & Payments

The system shall integrate with the existing **Cybrosys `base_accounting_kit` accounting solution** and standard Odoo accounting models.

The custom module shall **not implement its own accounting, invoice, payment, or tax system**.

A confirmed booking shall support:

- Recurring customer invoices
- Monthly billing as the default
- Weekly billing
- Quarterly billing
- Half-yearly billing
- Yearly billing
- Other/custom billing schedules
- Different billing frequencies where required
- Rental charges
- Discounts
- Taxes
- Additional charges
- Payment tracking

Every invoice shall remain a standard accounting record and must be traceable to:

**Customer → Booking → Site → Invoice → Payment**

The system shall display:

- Invoice number
- Invoice date
- Due date
- Amount
- Paid amount
- Outstanding amount
- Payment status
- Overdue status

The customer shall be able to view and download their invoices through the portal.

---

## 8. Taxes & Commercial Charges

The system shall use the existing accounting system's tax configuration.

The booking/quotation shall support:

- Applicable taxes
- Tax-inclusive or tax-exclusive pricing where configured
- Discounts
- Additional charges
- Tax calculation
- Credit notes/refunds where applicable

The custom module shall not duplicate tax calculation logic.

---

## 9. Landlord Lease Management

A site may be either **Owned** or **Leased**.

For leased sites, the system shall maintain a **Landlord Lease** record.

Each lease shall contain:

- Landlord/vendor
- Site
- Lease start date
- Lease end date
- Lease status
- Lease amount
- Payment frequency
- Custom payment schedule where required
- Taxes/other charges
- Renewal date
- Lease documents
- Terms and conditions
- Internal notes

Different landlords may have different payment schedules.

### Accounting integration

Landlord costs shall be integrated with the accounting system using vendor bills and payments.

The relationship shall be:

**Site → Landlord Lease → Vendor Bill → Payment**

The system should allow staff to determine the cost and profitability associated with a site.

---

## 10. Tracking

The system shall provide a **Tracking** function for active customer bookings.

A Tracking record shall be associated with:

- Customer
- Booking
- Site
- Tracking date/period

Each Tracking record shall support:

- Multiple photographs
- Photograph date/time
- Optional GPS/location information
- Notes/observations
- Staff member responsible
- Tracking status
- Sent date/time

### Tracking workflow

```text
Draft
  ↓
Reviewed
  ↓
Sent to Customer
```

Staff shall manually review and send the Tracking report.

The system shall **store every Tracking record and its photographs permanently** as part of the booking history.

### Customer access

The customer portal shall display the Tracking history for the customer's own bookings.

Customers shall be able to:

- View previous Tracking records
- View photographs
- Download photographs/reports where permitted

The same Tracking information shall also be sent to the customer by email when staff clicks **Send**.

---

## 11. Customer Portal

Customers shall have secure portal access.

The portal shall provide the following sections:

### My Quotations

Customers can:

- View quotations
- View sites and requested dates
- View pricing and taxes
- Accept quotations
- Reject quotations
- Request quotation revisions

### My Bookings

Customers can view:

- Current bookings
- Upcoming bookings
- Completed bookings
- Sites included in each booking
- Rental periods
- Booking status
- Pricing

### My Invoices & Payments

Customers can view:

- Invoices
- Invoice dates
- Due dates
- Amounts
- Payment status
- Outstanding amounts
- Payment history
- Downloadable invoice documents

### Site Availability

Customers can:

- Browse active sites
- Filter by site type
- View site information
- View photographs
- View availability
- View exact occupied/reserved date ranges
- Select dates and submit a booking request

### My Tracking

Customers can:

- View Tracking history
- View Tracking photographs
- View Tracking notes
- Download Tracking photographs/reports

### Data isolation

A customer shall only be able to access:

- Their own quotations
- Their own bookings
- Their own invoices
- Their own payments
- Their own Tracking records

They must not be able to access another customer's information.

---

## 12. Notifications & Communication

The system shall use Odoo's existing Mail/Email functionality.

Notifications should support:

- New Booking Request → Staff
- Quotation Sent → Customer
- Quotation Accepted → Staff
- Quotation Rejected → Staff
- Revision Requested → Staff
- Booking Confirmed → Customer
- Invoice Generated → Customer
- Invoice Due/Overdue → Customer
- Tracking Sent → Customer
- Booking Expiry → Staff
- Lease Expiry/Renewal → Staff

---

## 13. Dashboard & Reports

The system shall provide management information including:

### Site information
- Total sites
- Available sites
- Reserved sites
- Rented sites
- Maintenance sites
- Inactive sites
- Site utilization/occupancy

### Booking information
- Current bookings
- Upcoming bookings
- Completed bookings
- Expiring bookings
- Booking history by site
- Booking history by customer

### Financial information
- Revenue by site
- Revenue by customer
- Outstanding customer invoices
- Landlord costs
- Site-level profitability/margin

### Operations
- Expiring leases
- Pending Tracking
- Tracking history

Tax and formal accounting reports shall remain the responsibility of the existing accounting system.

---

## 14. User Roles & Access Control

The system should support appropriate permissions for:

### Sales/Booking Staff
- Manage customers' booking requests
- Prepare quotations
- Manage bookings
- View site availability

### Operations Staff
- Manage sites
- Manage availability
- Manage Tracking
- Upload Tracking photographs

### Accounting Staff
- View related invoices and payments
- Manage landlord/vendor bills
- Manage accounting records

### Manager/Administrator
- Full access

### Customer
- Portal-only access to their own records and public site availability.

---

## 15. Integration With Existing Odoo/Cybrosys Modules

The custom module shall reuse existing functionality wherever possible:

| Requirement | Existing Odoo/Cybrosys functionality |
|---|---|
| Customers/Landlords | Contacts |
| Customer quotations | Sales |
| Customer invoices | Cybrosys/Odoo Accounting |
| Taxes | Accounting |
| Customer payments | Accounting |
| Vendor bills | Accounting |
| Vendor payments | Accounting |
| Email | Mail |
| Documents/photos | Odoo Attachments/Documents |
| Customer authentication | Portal |
| Customer portal | Website/Portal |
| Activities/reminders | Mail/Activities |

### Custom module

The complete custom functionality should initially be contained in:

**`advertising_management`**

with the core models:

```text
advertising.site
advertising.booking
advertising.lease
advertising.tracking
```

The central business flow is:

```text
Customer
   │
   ▼
Browse Sites & Availability
   │
   ▼
Booking Request
   │
   ▼
Quotation
   │
   ├── Reject
   ├── Request Revision
   │
   └── Accept
          │
          ▼
    Confirmed Booking
          │
     ┌────┼───────────────┐
     ▼    ▼               ▼
 Invoices Payments     Tracking
     │                    │
     └────────┬───────────┘
              ▼
       Customer Portal
```

This version is the **requirements baseline** I would use for development. It is detailed enough to prevent ambiguity while still keeping the custom system focused on the actual advertising-rental business rather than rebuilding functionality that Odoo/Cybrosys already provides.
