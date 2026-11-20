import logging
from itertools import groupby

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import BILLING_FREQUENCIES, drop_blank_import_values, generate_periods

_logger = logging.getLogger(__name__)


class AdvertisingLease(models.Model):
    _name = 'advertising.lease'
    _description = 'Advertising Landlord Lease'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'

    name = fields.Char(string='Lease Reference', required=True, copy=False,
                       default=lambda self: _('New'), index=True)
    site_id = fields.Many2one('advertising.site', string='Site', required=True, tracking=True,
                              index=True, domain="[('ownership', '=', 'leased')]")
    partner_id = fields.Many2one('res.partner', string='Landlord', required=True, tracking=True,
                                 compute='_compute_partner_id', store=True, readonly=False,
                                 precompute=True, index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True, copy=False, index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                 required=True, index=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True,
                                  readonly=False, required=True, precompute=True)

    date_start = fields.Date(string='Lease Start', required=True, tracking=True)
    date_end = fields.Date(string='Lease End', required=True, tracking=True)
    renewal_date = fields.Date(string='Renewal Date', compute='_compute_renewal_date', store=True,
                               readonly=False, precompute=True,
                               help="Date by which the lease should be renewed or terminated.")

    amount = fields.Monetary(string='Lease Amount', required=True, tracking=True,
                             help="Amount due for each payment period.")
    payment_frequency = fields.Selection(BILLING_FREQUENCIES, string='Payment Frequency',
                                         default='monthly', required=True)
    other_charges = fields.Monetary(string='Other Charges', help="Additional amount due with each payment.")
    tax_ids = fields.Many2many('account.tax', string='Taxes', compute='_compute_tax_ids',
                               store=True, readonly=False, precompute=True,
                               domain="[('type_tax_use', '=', 'purchase')]",
                               context={'active_test': False})
    auto_bill = fields.Boolean(string='Generate Bills Automatically', default=True)

    terms = fields.Html(string='Terms and Conditions')
    notes = fields.Html(string='Internal Notes')
    attachment_ids = fields.Many2many('ir.attachment', string='Documents')

    schedule_ids = fields.One2many('advertising.lease.schedule', 'lease_id', string='Payment Schedule',
                                   copy=False)
    bill_ids = fields.One2many('account.move', 'advertising_lease_id', string='Vendor Bills',
                               domain=[('move_type', 'in', ('in_invoice', 'in_refund'))],
                               groups='account.group_account_readonly')
    bill_count = fields.Integer(compute='_compute_bill_amounts', groups='account.group_account_readonly')
    amount_billed = fields.Monetary(compute='_compute_bill_amounts', groups='account.group_account_readonly')
    amount_paid = fields.Monetary(compute='_compute_bill_amounts', groups='account.group_account_readonly')
    amount_outstanding = fields.Monetary(compute='_compute_bill_amounts', groups='account.group_account_readonly')

    _sql_constraints = [
        ('dates_check', 'CHECK(date_end >= date_start)', 'The lease cannot end before it starts.'),
    ]

    @api.model
    def get_import_templates(self):
        return [{
            'label': _("Import Template for Landlord Leases"),
            'template': '/advertising_management/static/xls/advertising_lease_import_template.xlsx',
        }]

    @api.depends('site_id')
    def _compute_partner_id(self):
        for lease in self:
            lease.partner_id = lease.site_id.landlord_id or lease.partner_id

    @api.depends('company_id')
    def _compute_currency_id(self):
        for lease in self:
            lease.currency_id = (lease.company_id or self.env.company).currency_id

    @api.depends('date_end')
    def _compute_renewal_date(self):
        for lease in self:
            lease.renewal_date = lease.date_end and lease.date_end - relativedelta(days=30)

    @api.depends('company_id')
    def _compute_tax_ids(self):
        product = self.env.ref('advertising_management.product_site_lease', raise_if_not_found=False)
        for lease in self:
            lease.tax_ids = product.supplier_taxes_id._filter_taxes_by_company(
                lease.company_id) if product and lease.company_id else self.env['account.tax']

    @api.depends('bill_ids.amount_total', 'bill_ids.amount_residual', 'bill_ids.state')
    def _compute_bill_amounts(self):
        for lease in self:
            lease.bill_count = len(lease.bill_ids)
            lease.amount_billed, lease.amount_paid, lease.amount_outstanding = lease.bill_ids._get_advertising_amounts()

    @api.constrains('site_id')
    def _check_site_leased(self):
        for lease in self:
            if lease.site_id.ownership != 'leased':
                raise ValidationError(_(
                    "Site %s is not marked as leased: landlord leases can only be created for leased sites.",
                    lease.site_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            drop_blank_import_values(self.env, vals, ('payment_frequency', 'tax_ids', 'renewal_date'))
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('advertising.lease') or _('New')
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_in_progress(self):
        if any(lease.state not in ('draft', 'cancelled') or lease.bill_ids for lease in self):
            raise UserError(_("Only draft or cancelled leases without vendor bills can be deleted."))

    def action_confirm(self):
        draft = self.filtered(lambda l: l.state == 'draft')
        draft.write({'state': 'active'})
        draft._generate_schedule()
        draft._update_states()

    def action_cancel(self):
        self.filtered(lambda l: l.state in ('draft', 'active')).write({'state': 'cancelled'})

    def action_draft(self):
        self.filtered(lambda l: l.state == 'cancelled').write({'state': 'draft'})

    def action_renew(self):
        """Create the draft lease continuing this one for the same duration."""
        self.ensure_one()
        duration = self.date_end - self.date_start
        new_start = self.date_end + relativedelta(days=1)
        renewal = self.copy({
            'date_start': new_start,
            'date_end': new_start + duration,
            'partner_id': self.partner_id.id,
            'tax_ids': [Command.set(self.tax_ids.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'advertising.lease',
            'res_id': renewal.id,
            'view_mode': 'form',
        }

    def _update_states(self):
        today = fields.Date.context_today(self)
        self.filtered(lambda l: l.state == 'active' and l.date_end < today).write({'state': 'expired'})

    def _generate_schedule(self, skip_before=None):
        """Create or realign the payment periods (see booking line schedule)."""
        for lease in self:
            periods = generate_periods(lease.date_start, lease.date_end, lease.payment_frequency)
            self.env['advertising.lease.schedule']._sync_periods(lease, periods, skip_before)

    @api.model
    def _cron_update_leases(self):
        self.search([('state', '=', 'active')])._update_states()
        self.env['advertising.lease.schedule']._cron_generate_bills()

    def action_create_due_bills(self):
        today = fields.Date.context_today(self)
        due = self.schedule_ids.filtered(lambda p: p.state == 'to_invoice' and p.invoice_date <= today)
        if not due:
            raise UserError(_("There is no payment period to bill yet."))
        return due.action_create_invoices()

    def action_view_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Vendor Bills"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.bill_ids.ids)],
            'context': {'default_move_type': 'in_invoice', 'default_partner_id': self.partner_id.id,
                        'default_advertising_lease_id': self.id},
        }


class AdvertisingLeaseSchedule(models.Model):
    _name = 'advertising.lease.schedule'
    _inherit = ['advertising.schedule.mixin']
    _description = 'Advertising Lease Payment Period'
    _parent_field = 'lease_id'
    _order = 'invoice_date, id'

    lease_id = fields.Many2one('advertising.lease', string='Lease', required=True,
                               ondelete='cascade', index=True)
    site_id = fields.Many2one(related='lease_id.site_id', store=True, index=True)
    partner_id = fields.Many2one(related='lease_id.partner_id', store=True, index=True)
    company_id = fields.Many2one(related='lease_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='lease_id.currency_id')
    move_id = fields.Many2one(string='Vendor Bill')
    invoice_date = fields.Date(string='Bill Date')
    amount_untaxed = fields.Monetary(string='Amount (excl. tax)', compute='_compute_amount_untaxed',
                                     store=True)
    payment_state = fields.Selection(related='move_id.payment_state', string='Payment Status')

    _sql_constraints = [
        ('lease_period_uniq', 'unique(lease_id, date_from)',
         'A lease can only have one payment period starting on a given date.'),
    ]

    @api.depends('quantity', 'lease_id.amount', 'lease_id.other_charges')
    def _compute_amount_untaxed(self):
        for period in self:
            period.amount_untaxed = (period.lease_id.amount + period.lease_id.other_charges) * period.quantity

    def _prepare_bill_vals(self, lease, bill_date, periods, product):
        lines = []
        for period in periods:
            period_label = f"{period.date_from} - {period.date_to}"
            common = {
                'product_id': product.id,
                'quantity': period.quantity,
                'tax_ids': [Command.set(lease.tax_ids.ids)],
                'advertising_site_id': lease.site_id.id,
                'advertising_period_start': period.date_from,
                'advertising_period_end': period.date_to,
            }
            lines.append(Command.create({
                **common, 'name': f"{lease.site_id.display_name}: {period_label}", 'price_unit': lease.amount}))
            if lease.other_charges:
                lines.append(Command.create({
                    **common, 'name': _("Other charges: %s", period_label), 'price_unit': lease.other_charges}))
        return {
            'move_type': 'in_invoice',
            'partner_id': lease.partner_id.id,
            'company_id': lease.company_id.id,
            'currency_id': lease.currency_id.id,
            'invoice_date': bill_date,
            'invoice_origin': lease.name,
            'ref': f"{lease.name}/{periods[0].date_from}",
            'advertising_lease_id': lease.id,
            'invoice_line_ids': lines,
        }

    def _create_bills(self):
        """Create one draft vendor bill per lease and bill date."""
        product = self.env.ref('advertising_management.product_site_lease',
                               raise_if_not_found=False).product_variant_id
        bills = self.env['account.move']
        periods = self.filtered(lambda p: p.state == 'to_invoice').sorted(
            lambda p: (p.lease_id.id, p.invoice_date, p.id))
        for (lease, bill_date), group in groupby(periods, key=lambda p: (p.lease_id, p.invoice_date)):
            group = self.browse([p.id for p in group])
            vals = self._prepare_bill_vals(lease, bill_date, group, product)
            bill = self.env['account.move'].with_company(lease.company_id).create(vals)
            group.write({'move_id': bill.id})
            bills |= bill
        return bills

    def action_create_invoices(self):
        bills = self._create_bills()
        return self._open_moves_action(bills) if bills else False

    @api.model
    def _cron_generate_bills(self):
        today = fields.Date.context_today(self)
        periods = self.search([
            ('state', '=', 'to_invoice'),
            ('invoice_date', '<=', today),
            ('lease_id.state', 'in', ('active', 'expired')),
            ('lease_id.auto_bill', '=', True),
        ])
        for lease in periods.lease_id:
            try:
                with self.env.cr.savepoint():
                    periods.filtered(lambda p: p.lease_id == lease)._create_bills()
            except Exception:
                _logger.exception("Could not generate the vendor bills of lease %s", lease.name)
