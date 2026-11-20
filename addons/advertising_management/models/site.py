from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools.misc import format_date

from .utils import BILLING_FREQUENCIES, BLOCKING_STATES, drop_blank_import_values


class AdvertisingSite(models.Model):
    _name = 'advertising.site'
    _description = 'Advertising Site'
    _inherit = ['image.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = 'code'
    _rec_names_search = ['name', 'code']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string='Site Code', required=True, copy=False, index=True,
                       default=lambda self: _('New'), tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    site_type_id = fields.Many2one('advertising.site.type', string='Site Type',
                                   required=True, tracking=True, index=True)

    # Location
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    zip = fields.Char()
    state_id = fields.Many2one('res.country.state', string='State',
                               domain="[('country_id', '=?', country_id)]")
    country_id = fields.Many2one('res.country')
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    map_url = fields.Char(string='Map Link')

    # Physical specifications
    width = fields.Float(help="Width in meters")
    height = fields.Float(help="Height in meters")
    area = fields.Float(compute='_compute_area', store=True, string="Area (m²)")
    specifications = fields.Text(string='Physical Specifications')
    photo_ids = fields.One2many('advertising.site.photo', 'site_id', string='Photographs')

    # Commercial
    default_price = fields.Monetary(string='Standard Rental Price',
                                    help="Price per billing period.")
    default_billing_frequency = fields.Selection(BILLING_FREQUENCIES, string='Default Billing Frequency',
                                                 default='monthly', required=True)
    ownership = fields.Selection([('owned', 'Owned'), ('leased', 'Leased')],
                                 default='owned', required=True, tracking=True)
    landlord_id = fields.Many2one('res.partner', string='Landlord', tracking=True)

    # Status
    is_under_maintenance = fields.Boolean(string='Under Maintenance', tracking=True)
    status = fields.Selection([
        ('available', 'Available'),
        ('reserved', 'Reserved'),
        ('rented', 'Rented'),
        ('maintenance', 'Maintenance'),
        ('inactive', 'Inactive'),
    ], compute='_compute_status', store=True, index=True)

    booking_line_ids = fields.One2many('advertising.booking.line', 'site_id', string='Booking Lines')
    booking_count = fields.Integer(compute='_compute_booking_count')
    lease_ids = fields.One2many('advertising.lease', 'site_id', string='Landlord Leases')
    lease_count = fields.Integer(compute='_compute_lease_count')

    # Profitability, from posted invoices and vendor bills traced to the site
    revenue = fields.Monetary(compute='_compute_financials', groups='advertising_management.group_advertising_accounting')
    cost = fields.Monetary(compute='_compute_financials', groups='advertising_management.group_advertising_accounting')
    profit = fields.Monetary(compute='_compute_financials', groups='advertising_management.group_advertising_accounting')
    invoice_count = fields.Integer(compute='_compute_financials', groups='advertising_management.group_advertising_accounting')
    bill_count = fields.Integer(compute='_compute_financials', groups='advertising_management.group_advertising_accounting')
    availability_html = fields.Html(compute='_compute_availability_html', sanitize=False)
    notes = fields.Html(string='Internal Notes')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'The site code must be unique.'),
        ('dimensions_positive', 'CHECK(width >= 0 AND height >= 0)', 'Dimensions cannot be negative.'),
    ]

    @api.depends('width', 'height')
    def _compute_area(self):
        for site in self:
            site.area = site.width * site.height

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for site in self:
            site.display_name = f"[{site.code}] {site.name}" if site.code and site.name else site.name

    @api.depends('active', 'is_under_maintenance', 'booking_line_ids.state',
                 'booking_line_ids.date_start', 'booking_line_ids.date_end')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for site in self:
            if not site.active:
                site.status = 'inactive'
            elif site.is_under_maintenance:
                site.status = 'maintenance'
            else:
                lines = site.booking_line_ids.filtered(
                    lambda line: line.state in BLOCKING_STATES and line.date_end and line.date_end >= today)
                if any(line.date_start <= today for line in lines):
                    site.status = 'rented'
                elif lines:
                    site.status = 'reserved'
                else:
                    site.status = 'available'

    @api.depends('booking_line_ids.booking_id')
    def _compute_booking_count(self):
        for site in self:
            site.booking_count = len(site.booking_line_ids.booking_id)

    @api.depends('lease_ids')
    def _compute_lease_count(self):
        for site in self:
            site.lease_count = len(site.lease_ids)

    def _compute_financials(self):
        totals = {}
        counts = {}
        site_ids = [site.id for site in self if site.id]
        if site_ids:
            lines = self.env['account.move.line'].sudo()
            for site, move_type, result in lines._read_group(
                    [('advertising_site_id', 'in', site_ids), ('parent_state', '=', 'posted'),
                     ('display_type', '=', 'product')],
                    ['advertising_site_id', 'move_type'], ['advertising_result:sum']):
                totals[(site.id, move_type)] = result
            for site, move_type, move_count in lines._read_group(
                    [('advertising_site_id', 'in', site_ids), ('parent_state', '=', 'posted'),
                     ('display_type', '=', 'product')],
                    ['advertising_site_id', 'move_type'], ['move_id:count_distinct']):
                counts[(site.id, move_type)] = move_count
        for site in self:
            revenue = totals.get((site.id, 'out_invoice'), 0.0) + totals.get((site.id, 'out_refund'), 0.0)
            cost = -(totals.get((site.id, 'in_invoice'), 0.0) + totals.get((site.id, 'in_refund'), 0.0))
            site.revenue = revenue
            site.cost = cost
            site.profit = revenue - cost
            site.invoice_count = counts.get((site.id, 'out_invoice'), 0) + counts.get((site.id, 'out_refund'), 0)
            site.bill_count = counts.get((site.id, 'in_invoice'), 0) + counts.get((site.id, 'in_refund'), 0)

    @api.depends('booking_line_ids.state', 'booking_line_ids.date_start', 'booking_line_ids.date_end')
    def _compute_availability_html(self):
        for site in self:
            if not site.id:
                site.availability_html = False
                continue
            availability = site.get_availability()
            rows = [Markup('<h5>%s</h5>') % _("Occupied / reserved periods")]
            rows.append(self._render_ranges(availability['occupied'], _("No upcoming bookings.")))
            rows.append(Markup('<h5 class="mt-3">%s</h5>') % _("Available periods (next 12 months)"))
            rows.append(self._render_ranges(availability['free'], _("Not available.")))
            site.availability_html = Markup('').join(rows)

    def _render_ranges(self, ranges, empty_message):
        if not ranges:
            return Markup('<p class="text-muted">%s</p>') % empty_message
        items = [
            Markup('<li>%s &rarr; %s</li>') % (
                escape(format_date(self.env, start)), escape(format_date(self.env, end)))
            for start, end in ranges
        ]
        return Markup('<ul>%s</ul>') % Markup('').join(items)

    @api.model
    def get_import_templates(self):
        return [{
            'label': _("Import Template for Advertising Sites"),
            'template': '/advertising_management/static/xls/advertising_site_import_template.xlsx',
        }]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            drop_blank_import_values(self.env, vals, ('default_billing_frequency', 'ownership'))
            if not vals.get('code') or vals['code'] == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('advertising.site') or _('New')
        return super().create(vals_list)

    def get_availability(self, date_from=None, date_to=None):
        """Occupied and free date ranges of the site.

        Only dates are returned (never customer or booking details) so the
        result can safely be shown to customers.
        """
        self.ensure_one()
        date_from = date_from or fields.Date.context_today(self)
        date_to = date_to or date_from + relativedelta(years=1)
        one_day = timedelta(days=1)
        lines = self.sudo().booking_line_ids.filtered(
            lambda line: line.state in BLOCKING_STATES
            and line.date_end >= date_from and line.date_start <= date_to
        ).sorted('date_start')
        occupied, free = [], []
        cursor = date_from
        for line in lines:
            start = max(line.date_start, date_from)
            end = min(line.date_end, date_to)
            if start > cursor:
                free.append((cursor, start - one_day))
            occupied.append((start, end))
            cursor = max(cursor, end + one_day)
        if cursor <= date_to:
            free.append((cursor, date_to))
        return {'occupied': occupied, 'free': free}

    @api.model
    def _cron_refresh_status(self):
        """Statuses depend on today's date, so refresh them daily."""
        sites = self.with_context(active_test=False).search([])
        sites._compute_status()

    def action_view_bookings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Bookings"),
            'res_model': 'advertising.booking',
            'view_mode': 'list,form',
            'domain': [('line_ids.site_id', '=', self.id)],
        }

    def action_view_leases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Landlord Leases"),
            'res_model': 'advertising.lease',
            'view_mode': 'list,form',
            'domain': [('site_id', '=', self.id)],
            'context': {'default_site_id': self.id},
        }

    def _action_view_moves(self, name, move_types):
        self.ensure_one()
        moves = self.env['account.move'].search([
            ('invoice_line_ids.advertising_site_id', '=', self.id), ('move_type', 'in', move_types),
            ('state', '=', 'posted')])
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

    def action_view_invoices(self):
        return self._action_view_moves(_("Invoices"), ['out_invoice', 'out_refund'])

    def action_view_bills(self):
        return self._action_view_moves(_("Vendor Bills"), ['in_invoice', 'in_refund'])

    def action_open_map(self):
        self.ensure_one()
        url = self.map_url
        if not url and (self.latitude or self.longitude):
            url = f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
        if not url:
            return False
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
