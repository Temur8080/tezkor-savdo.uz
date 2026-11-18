import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Branch, BranchInventory, Employee, Order, OrderItem, Product, Supplier,
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
            {'id': self.service.id, 'qty': 1},
        ])
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'], data)

        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.total_amount, Decimal('650000.00'))
        self.assertEqual(order.orderitem_set.count(), 2)

        self.assertEqual(BranchInventory.objects.get(product=self.goods).quantity, 4)
        self.assertEqual(BranchInventory.objects.get(product=self.service).quantity, 0)

        receipt = self.client.get(reverse('emp_receipt', args=[order.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, 'Ornatib berish')

    def test_service_only_sale_works_with_zero_stock(self):
        resp = self._checkout([{'id': self.service.id, 'qty': 1}], cash='150000')
        self.assertTrue(resp.json()['success'], resp.content)
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.total_amount, Decimal('150000.00'))
        self.assertEqual(BranchInventory.objects.get(product=self.service).quantity, 0)

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
