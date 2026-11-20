from odoo import _, api, fields, models


class AdvertisingScheduleMixin(models.AbstractModel):
    """Common fields of a billing period (customer invoice or landlord bill to generate)."""
    _name = 'advertising.schedule.mixin'
    _description = 'Advertising Billing Period'

    date_from = fields.Date(string='Period Start', required=True, index=True)
    date_to = fields.Date(string='Period End', required=True)
    invoice_date = fields.Date(string='Invoice Date', required=True, index=True,
                               compute='_compute_invoice_date', store=True, readonly=False,
                               precompute=True,
                               help="Date from which the invoice or bill is generated.")
    quantity = fields.Float(string='Periods', default=1.0, digits=(16, 2),
                            help="1 for a whole period, a fraction for a pro-rated one.")
    skip = fields.Boolean(string='Do Not Invoice',
                          help="Ignore this period: it is billed elsewhere or not billable.")
    move_id = fields.Many2one('account.move', string='Invoice', copy=False, index=True,
                              ondelete='set null')
    state = fields.Selection([
        ('to_invoice', 'To Invoice'),
        ('invoiced', 'Invoiced'),
        ('skipped', 'Skipped'),
    ], compute='_compute_state', store=True, index=True)

    @api.depends('date_from')
    def _compute_invoice_date(self):
        for period in self:
            period.invoice_date = period.invoice_date or period.date_from

    @api.depends('skip', 'move_id', 'move_id.state')
    def _compute_state(self):
        for period in self:
            if period.move_id and period.move_id.state != 'cancel':
                period.state = 'invoiced'
            elif period.skip:
                period.state = 'skipped'
            else:
                period.state = 'to_invoice'

    @api.model
    def _sync_periods(self, parent, periods, skip_before=None):
        """Create or realign the periods of ``parent`` on ``[(from, to, quantity)]``.

        Periods that already have an invoice are never changed. Periods ending
        before ``skip_before`` are flagged as not to invoice.
        """
        existing = {period.date_from: period for period in parent.schedule_ids}
        wanted = {date_from for date_from, _date_to, _quantity in periods}
        parent.schedule_ids.filtered(lambda p: p.date_from not in wanted and not p.move_id).unlink()
        new_vals = []
        for date_from, date_to, quantity in periods:
            skip = bool(skip_before and date_to < skip_before)
            current = existing.get(date_from)
            if not current:
                new_vals.append({
                    self._parent_field: parent.id, 'date_from': date_from, 'date_to': date_to,
                    'quantity': quantity, 'skip': skip,
                })
            elif not current.move_id:
                current.write({'date_to': date_to, 'quantity': quantity, 'skip': current.skip or skip})
        self.create(new_vals)

    def action_skip(self):
        self.filtered(lambda p: p.state == 'to_invoice').write({'skip': True})

    def action_restore(self):
        self.filtered(lambda p: p.state == 'skipped').write({'skip': False})

    def _open_moves_action(self, moves):
        action = {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'name': _("Invoices")}
        if len(moves) == 1:
            action.update({'view_mode': 'form', 'res_id': moves.id})
        else:
            action.update({'view_mode': 'list,form', 'domain': [('id', 'in', moves.ids)]})
        return action
