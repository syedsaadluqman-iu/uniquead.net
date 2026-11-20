from odoo import Command, api, fields, models


class AdvertisingScheduleWizard(models.TransientModel):
    _name = 'advertising.schedule.wizard'
    _description = 'Generate Billing Schedules'

    booking_ids = fields.Many2many('advertising.booking', string='Bookings')
    lease_ids = fields.Many2many('advertising.lease', string='Landlord Leases')
    skip_before = fields.Date(
        string='Skip Periods Ending Before',
        help="Periods ending before this date are marked as 'Do Not Invoice'. Use it for historical "
             "bookings and leases whose past periods are already billed or imported separately.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        active_model = self.env.context.get('active_model')
        if active_model == 'advertising.booking':
            values['booking_ids'] = [Command.set(active_ids)]
        elif active_model == 'advertising.lease':
            values['lease_ids'] = [Command.set(active_ids)]
        return values

    def action_generate(self):
        self.ensure_one()
        bookings = self.booking_ids.filtered(lambda b: b.state != 'cancelled')
        bookings.line_ids._generate_billing_schedule(self.skip_before)
        leases = self.lease_ids.filtered(lambda l: l.state != 'cancelled')
        leases._generate_schedule(self.skip_before)
        return {'type': 'ir.actions.act_window_close'}
