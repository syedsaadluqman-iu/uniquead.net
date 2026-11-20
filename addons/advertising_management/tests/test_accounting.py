from datetime import date

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged

from ..models.utils import compute_period_count, generate_periods
from .common import TemplateImportMixin


@tagged('post_install', '-at_install')
class TestAdvertisingAccounting(TemplateImportMixin, AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref('advertising_management.group_advertising_manager')
        cls.site_type = cls.env.ref('advertising_management.site_type_billboard')
        cls.site = cls.env['advertising.site'].create({
            'name': 'Main Boulevard', 'site_type_id': cls.site_type.id, 'default_price': 1000.0})
        cls.landlord = cls.env['res.partner'].create({'name': 'City Properties Ltd'})
        cls.leased_site = cls.env['advertising.site'].create({
            'name': 'Leased Rooftop', 'site_type_id': cls.site_type.id, 'default_price': 1000.0,
            'ownership': 'leased', 'landlord_id': cls.landlord.id})

    def _booking(self, start, end, site=None, state=None, confirm=True):
        vals = {
            'partner_id': self.partner_a.id,
            'line_ids': [(0, 0, {'site_id': (site or self.site).id, 'date_start': start, 'date_end': end})],
        }
        if state:
            vals['state'] = state
        booking = self.env['advertising.booking'].create(vals)
        if confirm:
            booking.action_confirm()
        return booking

    def _pay(self, move, amount):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create({'amount': amount})._create_payments()

    def test_generate_periods(self):
        self.assertEqual(generate_periods(date(2026, 1, 1), date(2026, 2, 14), 'monthly'),
                         [(date(2026, 1, 1), date(2026, 1, 31), 1.0), (date(2026, 2, 1), date(2026, 2, 14), 0.5)])
        self.assertEqual(len(generate_periods(date(2026, 1, 1), date(2026, 1, 14), 'weekly')), 2)
        self.assertEqual(generate_periods(date(2026, 1, 1), date(2026, 12, 31), 'custom'),
                         [(date(2026, 1, 1), date(2026, 12, 31), 1.0)])
        for frequency in ('weekly', 'monthly', 'quarterly', 'half_yearly', 'yearly'):
            start, end = date(2025, 1, 31), date(2027, 3, 10)
            total = sum(qty for _from, _to, qty in generate_periods(start, end, frequency))
            self.assertAlmostEqual(total, compute_period_count(start, end, frequency), delta=0.05)

    def test_booking_invoicing_and_payment(self):
        booking = self._booking(date(2024, 1, 1), date(2024, 3, 31))
        booking.charge_ids = [(0, 0, {'name': 'Installation', 'price_unit': 500.0})]
        self.assertEqual(booking.schedule_ids.mapped('quantity'), [1.0, 1.0, 1.0])
        self.assertEqual(set(booking.schedule_ids.mapped('state')), {'to_invoice'})

        booking.action_create_due_invoices()
        invoices = booking.invoice_ids.sorted('invoice_date')
        self.assertEqual(len(invoices), 3)
        self.assertEqual(invoices.mapped('amount_untaxed'), [1500.0, 1000.0, 1000.0])
        first_line = invoices[0].invoice_line_ids[0]
        self.assertEqual(first_line.advertising_site_id, self.site)
        self.assertEqual((first_line.advertising_period_start, first_line.advertising_period_end),
                         (date(2024, 1, 1), date(2024, 1, 31)))
        self.assertTrue(booking.charge_ids.is_billed)
        self.assertEqual(set(booking.schedule_ids.mapped('state')), {'invoiced'})
        with self.assertRaises(UserError):
            booking.action_create_due_invoices()

        invoices.action_post()
        self.assertEqual(booking.amount_invoiced, 3500.0)
        self.assertEqual(booking.amount_outstanding, 3500.0)
        self.assertIn(invoices[0], self.env['account.move'].search([('advertising_overdue', '=', True)]))
        self._pay(invoices[0], 600.0)
        self.assertEqual((booking.amount_paid, booking.amount_outstanding), (600.0, 2900.0))
        self.assertEqual(invoices[0].advertising_amount_paid, 600.0)
        self._pay(invoices[0], 900.0)
        self.assertNotIn(invoices[0], self.env['account.move'].search([('advertising_overdue', '=', True)]))
        self.assertEqual(booking.schedule_ids.filtered(lambda p: p.move_id == invoices[0]).payment_state,
                         invoices[0].payment_state)

    def test_cancelled_invoice_releases_period(self):
        booking = self._booking(date(2024, 1, 1), date(2024, 1, 31))
        booking.action_create_due_invoices()
        booking.invoice_ids.button_cancel()
        self.assertEqual(booking.schedule_ids.state, 'to_invoice')
        booking.action_create_due_invoices()
        self.assertEqual(len(booking.invoice_ids.filtered(lambda m: m.state != 'cancel')), 1)

    def test_historical_booking_schedule_and_cron(self):
        booking = self._booking(date(2023, 1, 1), date(2023, 12, 31), state='completed', confirm=False)
        self.assertFalse(booking.schedule_ids)
        wizard = self.env['advertising.schedule.wizard'].with_context(
            active_model='advertising.booking', active_ids=booking.ids).create({'skip_before': date(2023, 7, 1)})
        self.assertEqual(wizard.booking_ids, booking)
        wizard.action_generate()
        wizard.action_generate()
        self.assertEqual(len(booking.schedule_ids), 12)
        self.assertEqual(len(booking.schedule_ids.filtered(lambda p: p.state == 'skipped')), 6)

        booking.auto_invoice = False
        self.env['advertising.billing.schedule']._cron_generate_invoices()
        self.assertFalse(booking.invoice_ids)
        booking.auto_invoice = True
        self.env['advertising.billing.schedule']._cron_generate_invoices()
        self.assertEqual(len(booking.invoice_ids), 6)
        self.assertEqual(len(booking.schedule_ids.filtered(lambda p: p.state == 'skipped')), 6)

    def test_lease_bills_and_site_profitability(self):
        with self.assertRaises(ValidationError):
            self.env['advertising.lease'].create({
                'site_id': self.site.id, 'partner_id': self.landlord.id, 'amount': 1,
                'date_start': date(2024, 1, 1), 'date_end': date(2024, 3, 31)})
        lease = self.env['advertising.lease'].create({
            'site_id': self.leased_site.id, 'amount': 400.0, 'other_charges': 100.0,
            'date_start': date(2024, 1, 1), 'date_end': date(2024, 3, 31)})
        self.assertEqual(lease.partner_id, self.landlord)
        self.assertTrue(lease.name.startswith('LS/'))
        lease.action_confirm()
        self.assertEqual(lease.state, 'expired')
        self.assertEqual(len(lease.schedule_ids), 3)

        lease.action_create_due_bills()
        bills = lease.bill_ids
        self.assertEqual(len(bills), 3)
        self.assertEqual(bills.mapped('amount_untaxed'), [500.0] * 3)
        self.assertEqual(bills.invoice_line_ids.advertising_site_id, self.leased_site)
        self.assertEqual(len(set(bills.mapped('ref'))), 3)
        bills.action_post()
        self._pay(bills[0], 200.0)
        self.assertEqual((lease.amount_billed, lease.amount_paid, lease.amount_outstanding),
                         (1500.0, 200.0, 1300.0))

        booking = self._booking(date(2024, 1, 1), date(2024, 3, 31), site=self.leased_site)
        booking.action_create_due_invoices()
        booking.invoice_ids.action_post()
        site = self.leased_site
        self.assertEqual((site.revenue, site.cost, site.profit), (3000.0, 1500.0, 1500.0))
        self.assertEqual((site.invoice_count, site.bill_count, site.lease_count), (3, 3, 1))
        self.assertEqual(len(site.action_view_invoices()['domain'][0][2]), 3)

        refund = booking.invoice_ids[0]._reverse_moves()
        refund.action_post()
        site.invalidate_recordset()
        self.assertEqual(site.revenue, 2000.0)

    def _staff_user(self, login, group_xmlid):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'email': f'{login}@example.com',
            'groups_id': [(6, 0, [self.env.ref(group_xmlid).id])],
        })

    def test_staff_access_and_forms(self):
        sales = self._staff_user('adv_sales', 'advertising_management.group_advertising_sales')
        operations = self._staff_user('adv_ops', 'advertising_management.group_advertising_operations')
        booking = self._booking(date(2024, 1, 1), date(2024, 3, 31), confirm=False)
        lease = self.env['advertising.lease'].create({
            'site_id': self.leased_site.id, 'amount': 400.0,
            'date_start': date(2024, 1, 1), 'date_end': date(2024, 3, 31)})

        booking.with_user(sales).action_confirm()
        self.assertEqual(len(booking.schedule_ids), 3)
        with self.assertRaises(AccessError):
            booking.with_user(sales).action_create_due_invoices()
        booking.action_create_due_invoices()
        for user, models in ((sales, ('advertising.booking', 'advertising.site')),
                             (operations, ('advertising.booking', 'advertising.site', 'advertising.lease'))):
            for model in models:
                self.env[model].with_user(user).get_views([(False, 'form'), (False, 'list')])
        booking.with_user(sales).read(['name', 'schedule_ids', 'amount_total'])
        with self.assertRaises(AccessError):
            booking.with_user(sales).read(['invoice_count'])
        lease.with_user(operations).read(['name', 'amount', 'schedule_ids'])
        with self.assertRaises(AccessError):
            self.leased_site.with_user(operations).read(['profit'])

        with Form(self.env['advertising.lease']) as lease_form:
            lease_form.site_id = self.leased_site
            lease_form.date_start = date(2025, 1, 1)
            lease_form.date_end = date(2025, 12, 31)
            lease_form.amount = 700.0
        with Form(booking) as booking_form:
            booking_form.contract_ref = 'CTR-1'
        with Form(self.env['advertising.booking']) as new_booking_form:
            new_booking_form.partner_id = self.partner_a
            with new_booking_form.line_ids.new() as line_form:
                line_form.site_id = self.site
                line_form.date_start = date(2025, 1, 1)
                line_form.date_end = date(2025, 3, 31)
        self.assertEqual(new_booking_form.record.amount_untaxed, 3000.0)
        with Form(self.leased_site):
            pass

    def test_lease_renewal(self):
        lease = self.env['advertising.lease'].create({
            'site_id': self.leased_site.id, 'amount': 400.0,
            'date_start': date(2024, 1, 1), 'date_end': date(2024, 3, 31)})
        renewal = self.env['advertising.lease'].browse(lease.action_renew()['res_id'])
        self.assertEqual((renewal.date_start, renewal.date_end), (date(2024, 4, 1), date(2024, 6, 30)))
        self.assertEqual((renewal.state, renewal.amount, renewal.partner_id), ('draft', 400.0, self.landlord))

    def test_lease_import_template(self):
        self.leased_site.code = 'SITE-0002'
        self.leased_site.flush_recordset(['code'])
        self._run_template_import('advertising.lease', 'Leases')
        old = self.env['advertising.lease'].search([('name', '=', 'OLD-LS-2023-01')])
        self.assertEqual((old.state, old.amount, old.payment_frequency, old.auto_bill),
                         ('expired', 40000.0, 'monthly', False))
        current = self.env['advertising.lease'].search([('site_id', '=', self.leased_site.id)]) - old
        self.assertEqual((current.state, current.other_charges, current.payment_frequency, current.auto_bill),
                         ('active', 5000.0, 'quarterly', True))
        self.assertEqual(current.partner_id, self.landlord)

    def test_invoice_import_template(self):
        self.site.code = 'SITE-0001'
        self.leased_site.code = 'SITE-0002'
        self.site.flush_recordset(['code'])
        self.leased_site.flush_recordset(['code'])
        customer = self.env['res.partner'].create({'name': 'Acme Corporation'})
        booking = self.env['advertising.booking'].create({
            'name': 'OLD-2023-014', 'partner_id': customer.id,
            'line_ids': [(0, 0, {'site_id': self.site.id, 'date_start': date(2023, 1, 1),
                                 'date_end': date(2023, 12, 31)})]})
        self._run_template_import('account.move', 'Invoices', template_index=0,
                                  context={'default_move_type': 'out_invoice'})
        invoice = booking.invoice_ids
        self.assertEqual((invoice.move_type, invoice.partner_id, invoice.invoice_date),
                         ('out_invoice', customer, date(2023, 1, 1)))
        self.assertEqual(invoice.invoice_line_ids.advertising_site_id, self.site | self.leased_site)
        self.assertEqual(invoice.invoice_line_ids.mapped('discount'), [0.0, 5.0])
        invoice.action_post()
        self.assertEqual(invoice.name, 'INV/2023/0001')
        self.assertEqual(booking.amount_invoiced, invoice.amount_total)

    def test_vendor_bill_import_template(self):
        self.leased_site.code = 'SITE-0002'
        self.leased_site.flush_recordset(['code'])
        lease = self.env['advertising.lease'].create({
            'name': 'OLD-LS-2023-01', 'site_id': self.leased_site.id, 'amount': 40000.0,
            'date_start': date(2023, 1, 1), 'date_end': date(2023, 12, 31)})
        self._run_template_import('account.move', 'Vendor Bills', template_index=1,
                                  context={'default_move_type': 'in_invoice'})
        bill = lease.bill_ids
        self.assertEqual((bill.move_type, bill.partner_id, bill.ref), ('in_invoice', self.landlord, 'JAN-2023'))
        self.assertEqual(bill.invoice_line_ids.advertising_site_id, self.leased_site)
        bill.action_post()
        self.assertEqual(lease.amount_billed, bill.amount_total)
