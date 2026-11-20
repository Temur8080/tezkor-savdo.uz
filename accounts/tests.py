import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Branch, BranchInventory, CustomerDebt, Employee, Order, OrderItem, Product, Supplier,
)


class ServiceItemCheckoutTests(TestCase):
    """«Ornatib berish» kabi xizmat: kassada sotiladi, chekda chiqadi, ombor kamaymaydi."""

    def setUp(self):
        self.user = User.objects.create_superuser('kassir', password='x')
        self.branch = Branch.objects.create(name='Asosiy')
        Employee.objects.create(user=self.user, branch=self.branch, name='Kassir', role='Manager')
        supplier = Supplier.objects.create(name='Test', contract_expiration=date(2030, 1, 1))
        self.goods = Product.objects.create(
            supplier=supplier, product_name='Kamera', barcode='G-1',
            base_price=Decimal('500000'), cost_price=Decimal('10'),
        )
        self.service = Product.objects.create(
            supplier=supplier, product_name='Ornatib berish', barcode='XIZMAT-1',
            base_price=Decimal('150000'), cost_price=Decimal('0'), is_service=True,
        )
        BranchInventory.objects.create(branch=self.branch, product=self.goods, quantity=5)
        BranchInventory.objects.create(branch=self.branch, product=self.service, quantity=0)
        self.client.force_login(self.user)

    def _checkout(self, cart, cash=None):
        payload = {'cart': cart, 'currency': 'UZS'}
        if cash is not None:
            payload['cashReceived'] = cash
        return self.client.post(
            reverse('checkout_cash'), data=json.dumps(payload), content_type='application/json',
        )

    def test_service_sold_with_goods_and_visible_on_receipt(self):
        resp = self._checkout([
            {'id': self.goods.id, 'qty': 1},
            {'id': self.service.id, 'qty': 1, 'price': 180000},
        ])
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'], data)

        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.total_amount, Decimal('680000.00'))
        self.assertEqual(order.service_amount, Decimal('180000.00'))
        self.assertEqual(order.shop_amount, Decimal('500000.00'))
        self.assertTrue(order.orderitem_set.get(product=self.service).price_adjusted)
        self.assertEqual(order.orderitem_set.count(), 2)

        self.assertEqual(BranchInventory.objects.get(product=self.goods).quantity, 4)
        self.assertEqual(BranchInventory.objects.get(product=self.service).quantity, 0)

        receipt = self.client.get(reverse('emp_receipt', args=[order.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, 'Ornatib berish')

    def test_service_only_sale_works_with_zero_stock(self):
        resp = self._checkout([{'id': self.service.id, 'qty': 1, 'price': 150000}], cash='150000')
        self.assertTrue(resp.json()['success'], resp.content)
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.total_amount, Decimal('150000.00'))
        self.assertEqual(BranchInventory.objects.get(product=self.service).quantity, 0)

    def test_service_requires_manual_price(self):
        before = Order.objects.count()
        resp = self._checkout([{'id': self.service.id, 'qty': 1}])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), before)

    def test_service_fee_not_discounted(self):
        from .views import _price_lines_from_cart
        priced = _price_lines_from_cart(
            [{'id': self.goods.id, 'qty': 1}, {'id': self.service.id, 'qty': 1, 'price': 100000}],
            {'mode': 'discount', 'percent': 10},
        )
        self.assertEqual(priced['service_total'], Decimal('100000.00'))
        self.assertEqual(priced['net_total'], Decimal('550000.00'))  # 500000-10% + 100000
        self.assertEqual(priced['discount_amount'], Decimal('50000.00'))

    def test_reports_exclude_service_fee_from_profit(self):
        resp = self._checkout([
            {'id': self.goods.id, 'qty': 1},
            {'id': self.service.id, 'qty': 1, 'price': 200000},
        ])
        self.assertTrue(resp.json()['success'], resp.content)
        report = self.client.get(reverse('admin_reports'), {'period': 'all'})
        self.assertEqual(report.status_code, 200)
        ctx = report.context
        self.assertEqual(ctx['gross_revenue'], Decimal('500000'))
        self.assertEqual(ctx['net_profit'], ctx['gross_revenue'] - ctx['cost'])
        self.assertEqual(ctx['cost'], Decimal('125000'))  # $10 * kurs 12500
        self.assertEqual(ctx['service_fee_total'], Decimal('200000'))
        self.assertIn('Usta haqqi', report.content.decode())
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_regular_product_still_blocked_without_stock(self):
        resp = self._checkout([{'id': self.goods.id, 'qty': 6}])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(BranchInventory.objects.get(product=self.goods).quantity, 5)

    def test_scan_api_reports_unlimited_stock_for_service(self):
        resp = self.client.get(reverse('scan_product'), {'barcode': 'XIZMAT-1'})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['stock'])
        self.assertTrue(resp.json()['is_service'])

    def test_pos_grid_shows_service_without_disabling(self):
        resp = self.client.get(reverse('pos_terminal'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        card = html[html.index('data-barcode="XIZMAT-1"'):]
        card = card[:card.index('>')]
        self.assertIn('data-stock=""', card)
        self.assertNotIn('disabled', card)

    def test_ustanofka_category_makes_service_and_hides_product_fields(self):
        resp = self.client.post(reverse('inventory_product_save'), {
            'barcode': 'U-1', 'product_name': 'Kamera ustanovka', 'category': 'USTANOFKA',
            'entry_currency': 'UZS', 'store_currency': 'UZS',
            'cost_price': '999', 'base_price': '150000', 'qty': '5',
            'branch_id': self.branch.id,
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        product = Product.objects.get(barcode='U-1')
        self.assertTrue(product.is_service)
        self.assertEqual(product.cost_price, Decimal('0'))
        self.assertEqual(BranchInventory.objects.get(product=product).quantity, 0)
        page = self.client.get(reverse('inventory_intake')).content.decode()
        self.assertIn('USTANOFKA', page)
        self.assertIn('data-product-only', page)
        self.assertIn('service-banner', page)

    def test_intake_creates_service_without_stock(self):
        resp = self.client.post(reverse('inventory_product_save'), {
            'product_name': 'Montaj', 'category': 'Xizmat', 'is_service': '1',
            'entry_currency': 'UZS', 'store_currency': 'UZS',
            'cost_price': '0', 'base_price': '100000',
            'branch_id': self.branch.id,
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body['is_service'])
        product = Product.objects.get(pk=body['id'])
        self.assertTrue(product.is_service)
        self.assertTrue(product.barcode.startswith('XIZMAT-'))
        self.assertEqual(BranchInventory.objects.get(product=product).quantity, 0)


class SecurityAndIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='x')
        self.branch = Branch.objects.create(name='Asosiy')
        self.emp = Employee.objects.create(user=self.user, branch=self.branch, name='Admin', role='Manager')
        supplier = Supplier.objects.create(name='Test', contract_expiration=date(2030, 1, 1))
        self.product = Product.objects.create(
            supplier=supplier, product_name='Kamera', barcode='G-1',
            base_price=Decimal('1000'), cost_price=Decimal('1'),
        )
        BranchInventory.objects.create(branch=self.branch, product=self.product, quantity=2)
        self.order = Order.objects.create(
            employee=self.emp, branch=self.branch, total_amount=Decimal('1000'),
            payment_method='CASH', order_status='Completed',
        )

    def test_sales_edit_requires_login(self):
        url = reverse('sales_edit', args=[self.order.pk])
        resp = self.client.post(url, {'employee': self.emp.pk, 'order_status': 'Cancelled'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'Completed')

    def test_destructive_links_reject_get(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('delete_order', args=[self.order.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('delete_product', args=[self.product.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('restore_product', args=[self.product.pk])).status_code, 405)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_active)

    def test_failed_checkout_leaves_no_partial_order(self):
        self.client.force_login(self.user)
        before = Order.objects.count()
        resp = self.client.post(
            reverse('checkout_cash'),
            data=json.dumps({'cart': [{'id': self.product.id, 'qty': 5}], 'currency': 'UZS'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), before)

    def test_checkout_requires_login(self):
        resp = self.client.post(
            reverse('checkout_cash'),
            data=json.dumps({'cart': [{'id': self.product.id, 'qty': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 302)

    def test_profile_requires_login(self):
        resp = self.client.get(reverse('employee_profile'))
        self.assertEqual(resp.status_code, 302)

    def test_main_pages_render(self):
        """Shablon o‘zgarishlari (POST tugmalar, JSON) sahifalarni buzmasin."""
        self.client.force_login(self.user)
        for name in ('branch_inventory', 'sales_display', 'admin_reports', 'pos_terminal',
                     'inventory_intake', 'dashboard'):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, name)
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            unit_price=Decimal('1000'), cost_price=Decimal('1'),
        )
        resp = self.client.get(reverse('sales_display'))
        self.assertIn(
            f'action="{reverse("delete_order", args=[self.order.pk])}"',
            resp.content.decode(),
        )
        resp = self.client.get(reverse('sales_edit', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)


class ReceiptDisplaySettingsTests(TestCase):
    """Sozlama: chekda chegirma/ustama qatori ko‘rsatilsin yoki yashirilsin."""

    def setUp(self):
        from .models import AppSettings
        self.user = User.objects.create_superuser('boss', password='x')
        self.branch = Branch.objects.create(name='Asosiy')
        self.emp = Employee.objects.create(user=self.user, branch=self.branch, name='Boss', role='Manager')
        supplier = Supplier.objects.create(name='T', contract_expiration=date(2030, 1, 1))
        self.product = Product.objects.create(
            supplier=supplier, product_name='Kamera', barcode='K-1',
            base_price=Decimal('1000'), cost_price=Decimal('1'),
        )
        self.order = Order.objects.create(
            employee=self.emp, branch=self.branch, total_amount=Decimal('900'),
            list_total=Decimal('1000'), discount_percent=Decimal('10'),
            discount_amount=Decimal('100'), payment_method='CASH', order_status='Completed',
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=1,
            list_unit_price=Decimal('1000'), unit_price=Decimal('900'), cost_price=Decimal('1'),
        )
        self.settings = AppSettings.get_solo()
        self.client.force_login(self.user)

    def _receipt(self):
        resp = self.client.get(reverse('emp_receipt', args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_discount_shown_by_default(self):
        html = self._receipt()
        self.assertIn('CHEGIRMA', html)
        self.assertIn('ORALIQ', html)

    def test_discount_hidden_uses_final_prices(self):
        self.settings.receipt_show_discount = False
        self.settings.save()
        html = self._receipt()
        self.assertNotIn('CHEGIRMA', html)
        self.assertNotIn('ORALIQ', html)
        self.assertIn('900', html)

    def test_settings_page_saves_toggles(self):
        from .models import PriceTier
        tier_fields = {}
        for t in PriceTier.objects.all():
            tier_fields[f'tier_{t.id}_name'] = t.name
            tier_fields[f'tier_{t.id}_percent'] = str(t.discount_percent)
        resp = self.client.post(reverse('app_settings'), {
            **tier_fields,
            'vat_enabled': '0', 'vat_percent': '12',
            'pos_secret_code': 'chegirma10', 'pos_secret_discount_percent': '10',
            'pos_secret_markup_code': 'ustama10', 'pos_secret_markup_percent': '5',
            'receipt_show_discount': '0', 'receipt_show_markup': '1',
            'theme_mode': 'system',
        })
        self.assertEqual(resp.status_code, 302)
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.receipt_show_discount)
        self.assertTrue(self.settings.receipt_show_markup)
        self.assertEqual(self.client.get(reverse('app_settings')).status_code, 200)
        pos = self.client.get(reverse('pos_terminal')).content.decode()
        self.assertIn('RECEIPT_SHOW_DISCOUNT = false', pos)
        self.assertIn('RECEIPT_SHOW_MARKUP = true', pos)


class ServiceExcludedFromDebtTests(TestCase):
    """Ustanovka (usta haqqi) qarzdorlar ro‘yxatiga tushmaydi: qarz faqat tovar qismi."""

    def setUp(self):
        self.user = User.objects.create_superuser('kassir2', password='x')
        self.branch = Branch.objects.create(name='Asosiy')
        Employee.objects.create(user=self.user, branch=self.branch, name='Kassir', role='Manager')
        supplier = Supplier.objects.create(name='Test', contract_expiration=date(2030, 1, 1))
        self.goods = Product.objects.create(
            supplier=supplier, product_name='Kamera', barcode='G-9',
            base_price=Decimal('500000'), cost_price=Decimal('10'),
        )
        self.service = Product.objects.create(
            supplier=supplier, product_name='Ornatib berish', barcode='XIZMAT-9',
            base_price=Decimal('150000'), cost_price=Decimal('0'), is_service=True,
        )
        BranchInventory.objects.create(branch=self.branch, product=self.goods, quantity=10)
        self.client.force_login(self.user)

    def _checkout(self, cash):
        return self.client.post(
            reverse('checkout_cash'),
            data=json.dumps({
                'cart': [
                    {'id': self.goods.id, 'qty': 1},
                    {'id': self.service.id, 'qty': 1, 'price': 200000},
                ],
                'currency': 'UZS',
                'cashReceived': cash,
                'customerData': {'name': 'Test Mijoz', 'phone': '901234567'},
            }),
            content_type='application/json',
        )

    def test_cash_less_than_service_debt_is_goods_only(self):
        resp = self._checkout('100000')
        self.assertTrue(resp.json()['success'], resp.content)
        debt = CustomerDebt.objects.get()
        self.assertEqual(debt.original_amount, Decimal('500000.00'))  # tovar, xizmatsiz

    def test_cash_covers_service_then_goods(self):
        resp = self._checkout('500000')
        self.assertTrue(resp.json()['success'], resp.content)
        debt = CustomerDebt.objects.get()
        self.assertEqual(debt.original_amount, Decimal('200000.00'))  # 500000 - (500000-200000)

    def test_full_cash_has_no_debt(self):
        resp = self._checkout('700000')
        self.assertTrue(resp.json()['success'], resp.content)
        self.assertEqual(CustomerDebt.objects.count(), 0)

    def test_report_debt_and_sof_foyda_exclude_service(self):
        self._checkout('100000')
        ctx = self.client.get(reverse('admin_reports'), {'period': 'all'}).context
        self.assertEqual(ctx['outstanding_balance'], Decimal('500000.00'))
        self.assertEqual(ctx['service_fee_total'], Decimal('200000'))

    def test_strip_command_fixes_old_debts_and_keeps_paid_ones(self):
        from django.core.management import call_command
        from io import StringIO
        # Eski tartibda yaratilgan qarz: jami 700000, naqd 1000 -> qarz 699000 (xizmat ichida)
        resp = self._checkout('1000')
        self.assertTrue(resp.json()['success'], resp.content)
        debt = CustomerDebt.objects.get()
        debt.original_amount = Decimal('699000.00')
        debt.remaining_balance = Decimal('699000.00')
        debt.save()
        # dry-run hech narsani o‘zgartirmaydi
        call_command('strip_service_from_debts', stdout=StringIO())
        debt.refresh_from_db()
        self.assertEqual(debt.original_amount, Decimal('699000.00'))
        # apply: to‘lanmagan xizmat (200000-1000=199000) olib tashlanadi
        call_command('strip_service_from_debts', '--apply', stdout=StringIO())
        debt.refresh_from_db()
        self.assertEqual(debt.original_amount, Decimal('500000.00'))
        self.assertEqual(debt.remaining_balance, Decimal('500000.00'))
        # qayta yurgizilsa o‘zgarmaydi (idempotent)
        call_command('strip_service_from_debts', '--apply', stdout=StringIO())
        debt.refresh_from_db()
        self.assertEqual(debt.original_amount, Decimal('500000.00'))
        self.assertEqual(debt.remaining_balance, Decimal('500000.00'))
