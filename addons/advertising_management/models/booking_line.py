from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .utils import (
    BILLING_FREQUENCIES, BLOCKING_STATES, compute_period_count, drop_blank_import_values, format_range,
    generate_periods)


class AdvertisingBookingLine(models.Model):
    _name = 'advertising.booking.line'
    _description = 'Advertising Booking Line'
    _order = 'booking_id, sequence, id'

    booking_id = fields.Many2one('advertising.booking', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    state = fields.Selection(related='booking_id.state', store=True, index=True)
    partner_id = fields.Many2one(related='booking_id.partner_id', store=True, index=True)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='booking_id.currency_id')

    site_id = fields.Many2one('advertising.site', string='Site', required=True, index=True,
                              domain="[('active', '=', True)]")
    site_type_id = fields.Many2one(related='site_id.site_type_id', store=True)
    date_start = fields.Date(string='Start Date', required=True, index=True)
    date_end = fields.Date(string='End Date', required=True, index=True)

    billing_frequency = fields.Selection(BILLING_FREQUENCIES, compute='_compute_billing_frequency',
                                         store=True, readonly=False, required=True, precompute=True)
    period_count = fields.Float(string='Billing Periods', compute='_compute_period_count',
                                store=True, readonly=False, digits=(16, 2), precompute=True,
                                help="Number of billing periods in the booked range. "
                                     "Editable for the custom billing frequency.")
    price_unit = fields.Monetary(string='Price per Period', compute='_compute_price_unit',
                                 store=True, readonly=False, precompute=True)
    discount = fields.Float(string='Discount (%)', digits=(16, 2))
    tax_ids = fields.Many2many('account.tax', string='Taxes', compute='_compute_tax_ids',
                               store=True, readonly=False,
                               context={'active_test': False})
    price_subtotal = fields.Monetary(compute='_compute_amounts', store=True)
    price_tax = fields.Monetary(compute='_compute_amounts', store=True)
    price_total = fields.Monetary(compute='_compute_amounts', store=True)

    sale_line_id = fields.Many2one('sale.order.line', string='Quotation Line',
                                   readonly=True, copy=False, index=True)
    schedule_ids = fields.One2many('advertising.billing.schedule', 'booking_line_id',
                                   string='Billing Schedule', copy=False)

    _sql_constraints = [
        ('dates_check', 'CHECK(date_end >= date_start)', 'The end date cannot be before the start date.'),
        ('discount_check', 'CHECK(discount >= 0 AND discount <= 100)', 'The discount must be between 0 and 100%.'),
    ]

    def _generate_billing_schedule(self, skip_before=None):
        """Create or realign the billing periods of the lines.

        Periods already invoiced are never touched. Periods ending before
        ``skip_before`` are marked as not to invoice (history billed elsewhere).
        """
        for line in self:
            periods = generate_periods(line.date_start, line.date_end, line.billing_frequency)
            if line.billing_frequency == 'custom' and periods:
                periods = [(periods[0][0], periods[0][1], line.period_count or 1.0)]
            self.env['advertising.billing.schedule']._sync_periods(line, periods, skip_before)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            drop_blank_import_values(
                self.env, vals, ('billing_frequency', 'period_count', 'price_unit', 'tax_ids'))
        return super().create(vals_list)

    @api.depends('site_id')
    def _compute_billing_frequency(self):
        for line in self:
            line.billing_frequency = line.site_id.default_billing_frequency or line.billing_frequency or 'monthly'

    @api.depends('date_start', 'date_end', 'billing_frequency')
    def _compute_period_count(self):
        for line in self:
            if line.billing_frequency == 'custom':
                line.period_count = line.period_count or 1.0
            else:
                line.period_count = compute_period_count(
                    line.date_start, line.date_end, line.billing_frequency)

    @api.depends('site_id')
    def _compute_price_unit(self):
        for line in self:
            if line.site_id:
                line.price_unit = line.site_id.default_price

    @api.depends('site_id', 'partner_id', 'company_id')
    def _compute_tax_ids(self):
        for line in self:
            line.tax_ids = self.env['advertising.booking']._get_default_rental_taxes(
                line.company_id, line.partner_id)

    @api.depends('period_count', 'price_unit', 'discount', 'tax_ids', 'currency_id')
    def _compute_amounts(self):
        for line in self:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_ids.compute_all(
                price, line.currency_id or line.env.company.currency_id,
                line.period_count, partner=line.partner_id)
            line.price_subtotal = taxes['total_excluded']
            line.price_total = taxes['total_included']
            line.price_tax = taxes['total_included'] - taxes['total_excluded']

    @api.depends('site_id', 'date_start', 'date_end')
    def _compute_display_name(self):
        for line in self:
            if line.site_id and line.date_start and line.date_end:
                line.display_name = f"{line.site_id.display_name} ({format_range(line.env, line.date_start, line.date_end)})"
            else:
                line.display_name = line.site_id.display_name or _("New")

    def _get_overlapping_lines(self):
        """Confirmed/active lines of other bookings overlapping this line's period."""
        self.ensure_one()
        return self.sudo().search([
            ('id', '!=', self.id),
            ('site_id', '=', self.site_id.id),
            ('state', 'in', BLOCKING_STATES),
            ('date_start', '<=', self.date_end),
            ('date_end', '>=', self.date_start),
        ])

    @api.constrains('site_id', 'date_start', 'date_end', 'state')
    def _check_site_overlap(self):
        for line in self.filtered(lambda l: l.state in BLOCKING_STATES and l.site_id):
            overlapping = line._get_overlapping_lines()
            if overlapping:
                other = overlapping[0]
                raise ValidationError(_(
                    "Site %(site)s is already booked from %(range)s (booking %(booking)s). "
                    "Confirmed bookings of the same site cannot overlap.",
                    site=line.site_id.display_name,
                    range=format_range(self.env, other.date_start, other.date_end),
                    booking=other.booking_id.name,
                ))
