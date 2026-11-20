from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AdvertisingBooking(models.Model):
    _name = 'advertising.booking'
    _description = 'Advertising Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Booking Reference', required=True, copy=False,
                       default=lambda self: _('New'), index=True)
    contract_ref = fields.Char(string='Contract Reference', copy=False, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True,
                                 tracking=True, index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                 required=True, index=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True,
                                  readonly=False, required=True, precompute=True)
    sale_order_id = fields.Many2one('sale.order', string='Quotation', readonly=True,
                                    copy=False, index=True)

    line_ids = fields.One2many('advertising.booking.line', 'booking_id', string='Sites', copy=True)
    charge_ids = fields.One2many('advertising.booking.charge', 'booking_id',
                                 string='Additional Charges', copy=True)
    date_start = fields.Date(compute='_compute_dates', store=True)
    date_end = fields.Date(compute='_compute_dates', store=True)
    site_count = fields.Integer(compute='_compute_site_count')

    amount_untaxed = fields.Monetary(compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(compute='_compute_amounts', store=True)

    terms = fields.Html(string='Terms and Conditions')
    notes = fields.Html(string='Internal Notes')
    attachment_ids = fields.Many2many('ir.attachment', string='Documents')

    auto_invoice = fields.Boolean(string='Generate Invoices Automatically', default=True,
                                  help="Draft invoices are created every day for the billing periods that are due.")
    schedule_ids = fields.One2many('advertising.billing.schedule', 'booking_id', string='Billing Schedule')
    invoice_ids = fields.One2many('account.move', 'advertising_booking_id', string='Invoices',
                                  domain=[('move_type', 'in', ('out_invoice', 'out_refund'))],
                                  groups='account.group_account_readonly')
    invoice_count = fields.Integer(compute='_compute_invoice_amounts', groups='account.group_account_readonly')
    amount_invoiced = fields.Monetary(compute='_compute_invoice_amounts', groups='account.group_account_readonly')
    amount_paid = fields.Monetary(compute='_compute_invoice_amounts', groups='account.group_account_readonly')
    amount_outstanding = fields.Monetary(compute='_compute_invoice_amounts', groups='account.group_account_readonly')

    @api.model
    def get_import_templates(self):
        return [{
            'label': _("Import Template for Advertising Bookings"),
            'template': '/advertising_management/static/xls/advertising_booking_import_template.xlsx',
        }]

    @api.depends('company_id')
    def _compute_currency_id(self):
        for booking in self:
            booking.currency_id = (booking.company_id or self.env.company).currency_id

    @api.depends('line_ids.date_start', 'line_ids.date_end')
    def _compute_dates(self):
        for booking in self:
            booking.date_start = min(booking.line_ids.mapped('date_start'), default=False)
            booking.date_end = max(booking.line_ids.mapped('date_end'), default=False)

    @api.depends('line_ids.site_id')
    def _compute_site_count(self):
        for booking in self:
            booking.site_count = len(booking.line_ids.site_id)

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax',
                 'charge_ids.price_subtotal', 'charge_ids.price_tax')
    def _compute_amounts(self):
        for booking in self:
            booking.amount_untaxed = sum(booking.line_ids.mapped('price_subtotal')) + sum(
                booking.charge_ids.mapped('price_subtotal'))
            booking.amount_tax = sum(booking.line_ids.mapped('price_tax')) + sum(
                booking.charge_ids.mapped('price_tax'))
            booking.amount_total = booking.amount_untaxed + booking.amount_tax

    @api.depends('invoice_ids.amount_total', 'invoice_ids.amount_residual', 'invoice_ids.state')
    def _compute_invoice_amounts(self):
        for booking in self:
            booking.invoice_count = len(booking.invoice_ids)
            booking.amount_invoiced, booking.amount_paid, booking.amount_outstanding = \
                booking.invoice_ids._get_advertising_amounts()

    @api.model
    def _get_default_rental_taxes(self, company, partner):
        """Customer taxes of the rental service product, mapped by fiscal position."""
        product = self.env.ref('advertising_management.product_site_rental', raise_if_not_found=False)
        if not product or not company:
            return self.env['account.tax']
        taxes = product.taxes_id._filter_taxes_by_company(company)
        fiscal_position = partner.property_account_position_id
        return fiscal_position.map_tax(taxes) if fiscal_position else taxes

    @api.constrains('state')
    def _check_no_overlap_on_state_change(self):
        self.line_ids._check_site_overlap()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('advertising.booking') or _('New')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_progress(self):
        if any(booking.state not in ('draft', 'cancelled') for booking in self):
            raise UserError(_("Only draft or cancelled bookings can be deleted. Cancel the booking instead."))

    def action_confirm(self):
        for booking in self:
            if booking.state != 'draft':
                continue
            if not booking.line_ids:
                raise UserError(_("Add at least one site before confirming booking %s.", booking.name))
        drafts = self.filtered(lambda b: b.state == 'draft')
        drafts.write({'state': 'confirmed'})
        self._update_states()
        drafts.line_ids._generate_billing_schedule()

    def action_complete(self):
        self.filtered(lambda b: b.state == 'active').write({'state': 'completed'})

    def action_cancel(self):
        self.filtered(lambda b: b.state in ('draft', 'confirmed', 'active')).write({'state': 'cancelled'})

    def action_draft(self):
        self.filtered(lambda b: b.state == 'cancelled').write({'state': 'draft'})

    def _update_states(self):
        """Move bookings along their lifecycle according to today's date."""
        today = fields.Date.context_today(self)
        to_complete = self.filtered(
            lambda b: b.state in ('confirmed', 'active') and b.date_end and b.date_end < today)
        to_complete.write({'state': 'completed'})
        to_activate = (self - to_complete).filtered(
            lambda b: b.state == 'confirmed' and b.date_start and b.date_start <= today)
        to_activate.write({'state': 'active'})

    @api.model
    def _cron_update_states(self):
        self.search([('state', 'in', ('confirmed', 'active'))])._update_states()
        self.env['advertising.site']._cron_refresh_status()

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
        }

    def action_create_due_invoices(self):
        today = fields.Date.context_today(self)
        due = self.schedule_ids.filtered(
            lambda p: p.state == 'to_invoice' and p.invoice_date <= today)
        if not due:
            raise UserError(_("There is no billing period to invoice yet."))
        return due.action_create_invoices()

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Invoices"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_move_type': 'out_invoice', 'default_partner_id': self.partner_id.id,
                        'default_advertising_booking_id': self.id},
        }
