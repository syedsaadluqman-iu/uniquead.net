from odoo import _, api, fields, models
from odoo.osv import expression

from .utils import drop_blank_import_values


class AccountMove(models.Model):
    _inherit = 'account.move'

    advertising_booking_id = fields.Many2one('advertising.booking', string='Booking', index='btree_not_null',
                                             tracking=True)
    advertising_lease_id = fields.Many2one('advertising.lease', string='Landlord Lease',
                                           index='btree_not_null', tracking=True)
    advertising_amount_paid = fields.Monetary(string='Paid Amount', compute='_compute_advertising_amount_paid',
                                              currency_field='currency_id')
    advertising_overdue = fields.Boolean(string='Overdue', compute='_compute_advertising_overdue',
                                         search='_search_advertising_overdue')

    @api.model
    def get_import_templates(self):
        return super().get_import_templates() + [{
            'label': _("Import Template for Advertising Customer Invoices"),
            'template': '/advertising_management/static/xls/advertising_invoice_import_template.xlsx',
        }, {
            'label': _("Import Template for Landlord Vendor Bills"),
            'template': '/advertising_management/static/xls/advertising_vendor_bill_import_template.xlsx',
        }]

    @api.depends('amount_total', 'amount_residual', 'state')
    def _compute_advertising_amount_paid(self):
        for move in self:
            move.advertising_amount_paid = move.amount_total - move.amount_residual if move.state == 'posted' else 0.0

    @api.model
    def _get_advertising_overdue_domain(self):
        return [
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'in_invoice')),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', fields.Date.context_today(self)),
        ]

    @api.depends('invoice_date_due', 'payment_state', 'state', 'move_type')
    def _compute_advertising_overdue(self):
        overdue = self.filtered_domain(self._get_advertising_overdue_domain())
        overdue.advertising_overdue = True
        (self - overdue).advertising_overdue = False

    def _search_advertising_overdue(self, operator, value):
        domain = self._get_advertising_overdue_domain()
        if (operator == '=') == bool(value):
            return domain
        return ['!'] + expression.normalize_domain(domain)

    def _get_advertising_amounts(self):
        """(invoiced, paid, outstanding) of the posted moves; credit notes count negatively."""
        invoiced = paid = outstanding = 0.0
        for move in self.filtered(lambda m: m.state == 'posted'):
            sign = -1 if move.move_type in ('out_refund', 'in_refund') else 1
            invoiced += sign * move.amount_total
            paid += sign * (move.amount_total - move.amount_residual)
            outstanding += sign * move.amount_residual
        return invoiced, paid, outstanding


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    advertising_site_id = fields.Many2one('advertising.site', string='Advertising Site',
                                          index='btree_not_null')
    advertising_booking_line_id = fields.Many2one('advertising.booking.line', string='Booking Line',
                                                  index='btree_not_null', copy=False)
    advertising_period_start = fields.Date(string='Period Start')
    advertising_period_end = fields.Date(string='Period End')
    advertising_result = fields.Monetary(string='Site Result', compute='_compute_advertising_result',
                                         store=True, currency_field='company_currency_id',
                                         help="Income (positive) or cost (negative) of the site, "
                                              "in company currency.")

    @api.depends('balance', 'advertising_site_id')
    def _compute_advertising_result(self):
        for line in self:
            line.advertising_result = -line.balance if line.advertising_site_id else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            drop_blank_import_values(self.env, vals, ('account_id', 'tax_ids'))
        return super().create(vals_list)
