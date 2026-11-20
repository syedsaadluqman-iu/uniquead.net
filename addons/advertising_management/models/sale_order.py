from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_advertising = fields.Boolean(string='Advertising Quotation', copy=False, index=True)
    advertising_request = fields.Boolean(string='Customer Booking Request', copy=False, index=True,
                                         help="Created from a customer's booking request.")
    advertising_booking_id = fields.Many2one('advertising.booking', string='Booking',
                                             readonly=True, copy=False, index=True)
    advertising_conflict_message = fields.Text(compute='_compute_advertising_conflict_message')

    @api.depends('order_line.advertising_site_id', 'order_line.advertising_date_start',
                 'order_line.advertising_date_end', 'advertising_booking_id', 'state')
    def _compute_advertising_conflict_message(self):
        for order in self:
            messages = []
            if order.state != 'cancel' and not order.advertising_booking_id:
                for line in order.order_line:
                    message = line._get_advertising_conflict_message()
                    if message:
                        messages.append(message)
            order.advertising_conflict_message = "\n".join(messages)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.filtered(lambda o: not o.is_advertising and o.order_line.advertising_site_id).is_advertising = True
        return orders

    def _prepare_advertising_booking_vals(self):
        self.ensure_one()
        site_lines = self.order_line.filtered(lambda l: l.advertising_site_id and not l.display_type)
        if not site_lines:
            raise UserError(_("Quotation %s has no advertising site line.", self.name))
        for line in site_lines:
            if not line.advertising_date_start or not line.advertising_date_end:
                raise UserError(_("Set the start and end dates for site %s.",
                                  line.advertising_site_id.display_name))
        charge_lines = (self.order_line - site_lines).filtered(
            lambda l: not l.display_type and l.product_id)
        return {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'sale_order_id': self.id,
            'contract_ref': self.name,
            'terms': self.note,
            'line_ids': [fields.Command.create({
                'site_id': line.advertising_site_id.id,
                'date_start': line.advertising_date_start,
                'date_end': line.advertising_date_end,
                'billing_frequency': line.advertising_billing_frequency,
                'period_count': line.product_uom_qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [fields.Command.set(line.tax_id.ids)],
                'sale_line_id': line.id,
            }) for line in site_lines],
            'charge_ids': [fields.Command.create({
                'name': line.name,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit * (1 - line.discount / 100.0),
                'tax_ids': [fields.Command.set(line.tax_id.ids)],
            }) for line in charge_lines],
        }

    def action_convert_to_booking(self):
        self.ensure_one()
        if self.advertising_booking_id:
            raise UserError(_("This quotation is already converted to booking %s.",
                              self.advertising_booking_id.name))
        if self.state == 'cancel':
            raise UserError(_("A cancelled quotation cannot be converted to a booking."))
        booking = self.env['advertising.booking'].create(self._prepare_advertising_booking_vals())
        booking.action_confirm()
        self.advertising_booking_id = booking
        if self.state in ('draft', 'sent'):
            self.action_confirm()
        booking.message_post(body=_("Created from quotation %s.", self._get_html_link()))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'advertising.booking',
            'res_id': booking.id,
            'view_mode': 'form',
        }

    def action_view_advertising_booking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'advertising.booking',
            'res_id': self.advertising_booking_id.id,
            'view_mode': 'form',
        }
