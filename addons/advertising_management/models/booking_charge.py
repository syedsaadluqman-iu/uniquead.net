from odoo import api, fields, models

from .utils import drop_blank_import_values


class AdvertisingBookingCharge(models.Model):
    _name = 'advertising.booking.charge'
    _description = 'Advertising Booking Additional Charge'
    _order = 'booking_id, sequence, id'

    booking_id = fields.Many2one('advertising.booking', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related='booking_id.company_id', store=True, index=True)
    partner_id = fields.Many2one(related='booking_id.partner_id')
    currency_id = fields.Many2one(related='booking_id.currency_id')

    name = fields.Char(string='Description', required=True)
    quantity = fields.Float(default=1.0, digits=(16, 2))
    price_unit = fields.Monetary(string='Unit Price')
    tax_ids = fields.Many2many('account.tax', string='Taxes', compute='_compute_tax_ids',
                               store=True, readonly=False, context={'active_test': False})
    price_subtotal = fields.Monetary(compute='_compute_amounts', store=True)
    price_tax = fields.Monetary(compute='_compute_amounts', store=True)
    price_total = fields.Monetary(compute='_compute_amounts', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            drop_blank_import_values(self.env, vals, ('tax_ids',))
        return super().create(vals_list)

    @api.depends('partner_id', 'company_id')
    def _compute_tax_ids(self):
        for charge in self:
            charge.tax_ids = self.env['advertising.booking']._get_default_rental_taxes(
                charge.company_id, charge.partner_id)

    @api.depends('quantity', 'price_unit', 'tax_ids', 'currency_id')
    def _compute_amounts(self):
        for charge in self:
            taxes = charge.tax_ids.compute_all(
                charge.price_unit, charge.currency_id or charge.env.company.currency_id,
                charge.quantity, partner=charge.partner_id)
            charge.price_subtotal = taxes['total_excluded']
            charge.price_total = taxes['total_included']
            charge.price_tax = taxes['total_included'] - taxes['total_excluded']
