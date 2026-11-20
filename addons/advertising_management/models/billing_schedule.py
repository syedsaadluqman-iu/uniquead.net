import logging
from itertools import groupby

from odoo import Command, _, api, fields, models

from .utils import format_range

_logger = logging.getLogger(__name__)

INVOICEABLE_BOOKING_STATES = ('confirmed', 'active', 'completed')


class AdvertisingBillingSchedule(models.Model):
    _name = 'advertising.billing.schedule'
    _inherit = ['advertising.schedule.mixin']
    _description = 'Advertising Customer Billing Period'
    _parent_field = 'booking_line_id'
    _order = 'invoice_date, id'

    booking_line_id = fields.Many2one('advertising.booking.line', string='Booking Line',
                                      required=True, ondelete='cascade', index=True)
    booking_id = fields.Many2one(related='booking_line_id.booking_id', store=True, index=True)
    site_id = fields.Many2one(related='booking_line_id.site_id', store=True, index=True)
    partner_id = fields.Many2one(related='booking_line_id.partner_id', store=True, index=True)
    company_id = fields.Many2one(related='booking_line_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='booking_line_id.currency_id')
    amount_untaxed = fields.Monetary(string='Amount (excl. tax)', compute='_compute_amount_untaxed',
                                     store=True)
    payment_state = fields.Selection(related='move_id.payment_state', string='Payment Status')

    _sql_constraints = [
        ('line_period_uniq', 'unique(booking_line_id, date_from)',
         'A booking line can only have one billing period starting on a given date.'),
    ]

    @api.depends('quantity', 'booking_line_id.price_unit', 'booking_line_id.discount')
    def _compute_amount_untaxed(self):
        for period in self:
            line = period.booking_line_id
            period.amount_untaxed = line.price_unit * (1 - line.discount / 100.0) * period.quantity

    def _prepare_invoice_line_vals(self, product):
        self.ensure_one()
        line = self.booking_line_id
        return {
            'product_id': product.id,
            'name': f"{line.site_id.display_name}: {format_range(self.env, self.date_from, self.date_to)}",
            'quantity': self.quantity,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'tax_ids': [Command.set(line.tax_ids.ids)],
            'advertising_site_id': line.site_id.id,
            'advertising_booking_line_id': line.id,
            'advertising_period_start': self.date_from,
            'advertising_period_end': self.date_to,
        }

    def _prepare_invoice_vals(self, booking, invoice_date, periods, charges, product):
        return {
            'move_type': 'out_invoice',
            'partner_id': booking.partner_id.id,
            'company_id': booking.company_id.id,
            'currency_id': booking.currency_id.id,
            'invoice_date': invoice_date,
            'invoice_origin': booking.name,
            'ref': booking.contract_ref or booking.name,
            'advertising_booking_id': booking.id,
            'invoice_line_ids': [
                Command.create(period._prepare_invoice_line_vals(product)) for period in periods
            ] + [
                Command.create(charge._prepare_invoice_line_vals(product)) for charge in charges
            ],
        }

    def _create_invoices(self):
        """Create one draft customer invoice per booking and invoice date."""
        product = self.env.ref('advertising_management.product_site_rental',
                               raise_if_not_found=False).product_variant_id
        periods = self.filtered(lambda p: p.state == 'to_invoice').sorted(
            lambda p: (p.booking_id.id, p.invoice_date, p.id))
        moves = self.env['account.move']
        for booking, booking_periods in groupby(periods, key=lambda p: p.booking_id):
            charges = booking.charge_ids.filtered(lambda c: not c.is_billed)
            for invoice_date, group in groupby(booking_periods, key=lambda p: p.invoice_date):
                group = self.browse([p.id for p in group])
                vals = self._prepare_invoice_vals(booking, invoice_date, group, charges, product)
                move = self.env['account.move'].with_company(booking.company_id).create(vals)
                group.write({'move_id': move.id})
                charges.write({'is_billed': True, 'move_id': move.id})
                charges = booking.charge_ids.browse()
                moves |= move
        return moves

    def action_create_invoices(self):
        moves = self._create_invoices()
        return self._open_moves_action(moves) if moves else False

    @api.model
    def _cron_generate_invoices(self):
        today = fields.Date.context_today(self)
        periods = self.search([
            ('state', '=', 'to_invoice'),
            ('invoice_date', '<=', today),
            ('booking_id.state', 'in', INVOICEABLE_BOOKING_STATES),
            ('booking_id.auto_invoice', '=', True),
        ])
        for booking in periods.booking_id:
            try:
                with self.env.cr.savepoint():
                    periods.filtered(lambda p: p.booking_id == booking)._create_invoices()
            except Exception:
                _logger.exception("Could not generate the invoices of booking %s", booking.name)
