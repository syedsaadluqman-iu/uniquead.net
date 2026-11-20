from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .utils import BILLING_FREQUENCIES, BLOCKING_STATES, compute_period_count, format_range


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    advertising_site_id = fields.Many2one('advertising.site', string='Site',
                                          domain="[('active', '=', True)]", index='btree_not_null')
    advertising_date_start = fields.Date(string='Start Date')
    advertising_date_end = fields.Date(string='End Date')
    advertising_billing_frequency = fields.Selection(
        BILLING_FREQUENCIES, string='Billing', compute='_compute_advertising_billing_frequency',
        store=True, readonly=False, precompute=True)

    @api.constrains('advertising_site_id', 'advertising_date_start', 'advertising_date_end')
    def _check_advertising_dates(self):
        for line in self.filtered('advertising_site_id'):
            start, end = line.advertising_date_start, line.advertising_date_end
            if start and end and end < start:
                raise ValidationError(_("The end date of site %s cannot be before its start date.",
                                        line.advertising_site_id.display_name))

    @api.depends('advertising_site_id')
    def _compute_advertising_billing_frequency(self):
        for line in self:
            line.advertising_billing_frequency = (
                line.advertising_site_id.default_billing_frequency or line.advertising_billing_frequency)

    def _is_advertising_site_line(self):
        self.ensure_one()
        return bool(self.advertising_site_id) and not self.display_type

    @api.depends('advertising_site_id', 'advertising_date_start', 'advertising_date_end',
                 'advertising_billing_frequency')
    def _compute_product_uom_qty(self):
        site_lines = self.filtered(lambda l: l._is_advertising_site_line())
        super(SaleOrderLine, self - site_lines)._compute_product_uom_qty()
        for line in site_lines:
            if line.advertising_billing_frequency == 'custom':
                line.product_uom_qty = line.product_uom_qty or 1.0
            else:
                line.product_uom_qty = compute_period_count(
                    line.advertising_date_start, line.advertising_date_end,
                    line.advertising_billing_frequency)

    def _get_display_price(self):
        # The rental price of a site line comes from the site, not from a pricelist.
        self.ensure_one()
        if self._is_advertising_site_line():
            return self.advertising_site_id.default_price
        return super()._get_display_price()

    @api.depends('advertising_site_id', 'advertising_date_start', 'advertising_date_end')
    def _compute_name(self):
        site_lines = self.filtered(lambda l: l._is_advertising_site_line())
        super(SaleOrderLine, self - site_lines)._compute_name()
        for line in site_lines:
            name = line.advertising_site_id.display_name
            if line.advertising_date_start and line.advertising_date_end:
                name = f"{name}\n{format_range(line.env, line.advertising_date_start, line.advertising_date_end)}"
            line.name = name

    def _get_advertising_product(self):
        return self.env.ref('advertising_management.product_site_rental', raise_if_not_found=False)

    @api.model_create_multi
    def create(self, vals_list):
        product = self._get_advertising_product()
        for vals in vals_list:
            site_id = vals.get('advertising_site_id')
            if not site_id or vals.get('display_type'):
                continue
            if product and not vals.get('product_id'):
                vals['product_id'] = product.product_variant_id.id
            # product_uom_qty has a static default, so it would never be computed on create
            if 'product_uom_qty' not in vals:
                site = self.env['advertising.site'].browse(site_id)
                frequency = vals.get('advertising_billing_frequency') or site.default_billing_frequency
                if frequency != 'custom':
                    vals['product_uom_qty'] = compute_period_count(
                        fields.Date.to_date(vals.get('advertising_date_start')),
                        fields.Date.to_date(vals.get('advertising_date_end')), frequency)
        lines = super().create(vals_list)
        lines.order_id.filtered(lambda o: not o.is_advertising).is_advertising = True
        return lines

    @api.onchange('advertising_site_id')
    def _onchange_advertising_site_id(self):
        for line in self.filtered(lambda l: l._is_advertising_site_line()):
            product = line._get_advertising_product()
            if product and not line.product_id:
                line.product_id = product.product_variant_id
            if line.product_id:
                line._reset_price_unit()

    def _get_advertising_conflicts(self):
        self.ensure_one()
        if not (self._is_advertising_site_line() and self.advertising_date_start and self.advertising_date_end):
            return self.env['advertising.booking.line']
        return self.env['advertising.booking.line'].sudo().search([
            ('site_id', '=', self.advertising_site_id.id),
            ('state', 'in', BLOCKING_STATES),
            ('date_start', '<=', self.advertising_date_end),
            ('date_end', '>=', self.advertising_date_start),
        ])

    def _get_advertising_conflict_message(self):
        self.ensure_one()
        conflicts = self._get_advertising_conflicts()
        if not conflicts:
            return ""
        periods = ", ".join(format_range(self.env, c.date_start, c.date_end) for c in conflicts)
        return _("Site %(site)s is already booked: %(periods)s.",
                 site=self.advertising_site_id.display_name, periods=periods)

    @api.onchange('advertising_site_id', 'advertising_date_start', 'advertising_date_end')
    def _onchange_advertising_conflict(self):
        for line in self:
            message = line._get_advertising_conflict_message()
            if message:
                return {'warning': {'title': _("Site not available"), 'message': message}}
