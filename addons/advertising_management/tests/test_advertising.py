from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase

from ..models.utils import compute_period_count
from .common import TemplateImportMixin


@tagged('post_install', '-at_install')
class TestAdvertising(TemplateImportMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site_type = cls.env.ref('advertising_management.site_type_billboard')
        cls.site = cls.env['advertising.site'].create({
            'name': 'Main Boulevard',
            'site_type_id': cls.site_type.id,
            'default_price': 1000.0,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Customer A'})
        cls.partner_b = cls.env['res.partner'].create({'name': 'Customer B'})

    def _booking(self, partner, start, end, site=None, confirm=True):
        booking = self.env['advertising.booking'].create({
            'partner_id': partner.id,
            'line_ids': [(0, 0, {
                'site_id': (site or self.site).id,
                'date_start': start,
                'date_end': end,
            })],
        })
        if confirm:
            booking.action_confirm()
        return booking

    def test_period_count(self):
        self.assertEqual(compute_period_count(date(2026, 1, 1), date(2026, 3, 31), 'monthly'), 3.0)
        self.assertEqual(compute_period_count(date(2026, 1, 1), date(2026, 12, 31), 'quarterly'), 4.0)
        self.assertEqual(compute_period_count(date(2026, 1, 1), date(2026, 1, 14), 'weekly'), 2.0)
        self.assertEqual(compute_period_count(date(2026, 1, 1), date(2026, 2, 14), 'monthly'), 1.5)
        self.assertEqual(compute_period_count(date(2026, 2, 1), date(2026, 1, 1), 'monthly'), 0.0)

    def test_site_code_sequence_and_line_defaults(self):
        self.assertTrue(self.site.code.startswith('SITE-'))
        booking = self._booking(self.partner, date(2030, 1, 1), date(2030, 6, 30), confirm=False)
        line = booking.line_ids
        self.assertEqual(line.price_unit, 1000.0)
        self.assertEqual(line.billing_frequency, 'monthly')
        self.assertEqual(line.period_count, 6.0)
        self.assertEqual(booking.amount_untaxed, 6000.0)

    def test_confirmed_bookings_cannot_overlap(self):
        self._booking(self.partner, date(2030, 1, 1), date(2030, 3, 31))
        with self.assertRaises(ValidationError):
            self._booking(self.partner_b, date(2030, 3, 31), date(2030, 5, 31))
        # Adjacent periods and draft bookings are fine
        self._booking(self.partner_b, date(2030, 4, 1), date(2030, 5, 31))
        self._booking(self.partner_b, date(2030, 1, 15), date(2030, 2, 15), confirm=False)

    def test_site_status_and_availability(self):
        today = fields.Date.context_today(self.site)
        self.assertEqual(self.site.status, 'available')
        booking = self._booking(self.partner, today + timedelta(days=10), today + timedelta(days=40))
        self.assertEqual(self.site.status, 'reserved')
        availability = self.site.get_availability(today, today + timedelta(days=60))
        self.assertEqual(availability['occupied'], [(today + timedelta(days=10), today + timedelta(days=40))])
        self.assertEqual(availability['free'], [
            (today, today + timedelta(days=9)),
            (today + timedelta(days=41), today + timedelta(days=60)),
        ])
        booking.line_ids.date_start = today
        self.assertEqual(self.site.status, 'rented')
        booking.action_cancel()
        self.assertEqual(self.site.status, 'available')
        self.site.is_under_maintenance = True
        self.assertEqual(self.site.status, 'maintenance')

    def test_quotation_converts_to_booking(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [
                (0, 0, {
                    'advertising_site_id': self.site.id,
                    'advertising_date_start': date(2031, 1, 1),
                    'advertising_date_end': date(2031, 3, 31),
                    'discount': 10.0,
                }),
                (0, 0, {
                    'product_id': self.env.ref('advertising_management.product_site_rental').product_variant_id.id,
                    'name': 'Installation fee',
                    'price_unit': 200.0,
                }),
            ],
        })
        self.assertTrue(order.is_advertising)
        site_line = order.order_line[0]
        self.assertEqual(site_line.product_uom_qty, 3.0)
        self.assertEqual(site_line.price_unit, 1000.0)

        order.action_convert_to_booking()
        booking = order.advertising_booking_id
        self.assertEqual(booking.state, 'confirmed')
        self.assertEqual(booking.partner_id, self.partner)
        self.assertEqual(booking.line_ids.period_count, 3.0)
        self.assertEqual(booking.line_ids.discount, 10.0)
        self.assertEqual(booking.charge_ids.price_unit, 200.0)
        self.assertEqual(order.state, 'sale')
        with self.assertRaises(UserError):
            order.action_convert_to_booking()

    def test_quotation_line_form_onchange(self):
        order_form = Form(self.env['sale.order'])
        order_form.partner_id = self.partner
        with order_form.order_line.new() as line:
            line.advertising_site_id = self.site
            line.advertising_date_start = date(2032, 1, 1)
            line.advertising_date_end = date(2032, 6, 30)
        order = order_form.save()
        site_line = order.order_line
        self.assertEqual(site_line.product_id, self.env.ref('advertising_management.product_site_rental').product_variant_id)
        self.assertEqual(site_line.price_unit, 1000.0)
        self.assertEqual(site_line.product_uom_qty, 6.0)
        self.assertEqual(site_line.price_subtotal, 6000.0)

        with Form(order) as order_form:
            with order_form.order_line.edit(0) as line:
                line.price_unit = 900.0
                line.advertising_date_end = date(2032, 3, 31)
        self.assertEqual(site_line.product_uom_qty, 3.0)
        self.assertEqual(site_line.price_unit, 900.0)
        self.assertEqual(site_line.price_subtotal, 2700.0)

    def test_booking_import_template_history(self):
        self.site.code = 'SITE-0001'
        self.site.flush_recordset(['code'])
        site_2 = self.env['advertising.site'].create({
            'name': 'Second Site', 'code': 'SITE-0002', 'site_type_id': self.site_type.id})
        customer = self.env['res.partner'].create({'name': 'Acme Corporation'})
        self._run_template_import('advertising.booking', 'Bookings')
        old = self.env['advertising.booking'].search([('contract_ref', '=', 'CTR-014')])
        self.assertEqual(old.name, 'OLD-2023-014')
        self.assertEqual(old.partner_id, customer)
        self.assertEqual(old.state, 'completed')
        self.assertEqual(old.line_ids.site_id, self.site | site_2)
        first_line = old.line_ids.filtered(lambda l: l.site_id == self.site)
        self.assertEqual(first_line.period_count, 12.0)
        self.assertEqual(first_line.price_unit, 150000.0)
        self.assertEqual(old.charge_ids.price_unit, 20000.0)
        second_line = old.line_ids - first_line
        self.assertEqual((second_line.period_count, second_line.discount), (6.0, 5.0))
        second = self.env['advertising.booking'].search([('contract_ref', '=', 'CTR-021')])
        self.assertTrue(second.name.startswith('BK/'))
        self.assertEqual(second.line_ids.period_count, 2.0)
        # Past data never blocks the site or other bookings
        self.assertEqual(self.site.status, 'available')
        self.env['advertising.booking'].create({
            'partner_id': customer.id, 'state': 'completed',
            'line_ids': [(0, 0, {'site_id': self.site.id, 'date_start': date(2023, 6, 1),
                                 'date_end': date(2023, 9, 30)})],
        })

    def test_site_import_template(self):
        self._run_template_import('advertising.site', 'Sites')
        site = self.env.ref('__import__.site_main_boulevard')
        self.assertEqual(site.name, 'Main Boulevard Billboard')
        self.assertEqual(site.site_type_id, self.site_type)
        self.assertEqual(site.default_price, 150000.0)
        self.assertEqual(site.default_billing_frequency, 'monthly')
        self.assertEqual(site.ownership, 'owned')
        self.assertTrue(site.code.startswith('SITE-'))

    def test_quotation_conflict_warning(self):
        self._booking(self.partner, date(2031, 1, 1), date(2031, 3, 31))
        order = self.env['sale.order'].create({
            'partner_id': self.partner_b.id,
            'order_line': [(0, 0, {
                'advertising_site_id': self.site.id,
                'advertising_date_start': date(2031, 3, 1),
                'advertising_date_end': date(2031, 4, 30),
            })],
        })
        self.assertIn(self.site.name, order.advertising_conflict_message)
        with self.assertRaises(ValidationError):
            order.action_convert_to_booking()
