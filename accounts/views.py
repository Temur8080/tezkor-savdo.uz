from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test

from .decorators import (
    unauthenticated_user,
    post_login_redirect_name,
    get_active_employee,
    is_app_manager,
    is_consultant,
    can_complete_sale,
    can_process_return,
    manager_required,
    ManagerRequiredMixin,
    PortalCapRequiredMixin,
    portal_cap_required,
    ROLE_CONSULTANT,
    ROLE_SALES,
)
from .portal_perms import assign_role_permissions, has_portal_cap
from .admin_branch import (
    get_admin_branch_ids,
    scope_queryset_by_branch,
    user_can_access_branch,
)
from .models import Product, Employee, Branch, BranchInventory, Customer, Order, OrderItem, Payment, CashPayment, \
    Invoice, WarrantyClaims, DefectiveInventory, ReplacementRecord, AuditTrail, \
    Organization, Supplier, ProductCategory, AppSettings, CustomerDebt, DebtPayment, Expense, PriceTier, \
    SalesAgent, ProductReservation, ProductReservationItem, SaleReturn, SaleReturnItem
from .loyalty import apply_discount, apply_markup, customer_payload, money as money_dec
from .money import (
    CURRENCY_UZS, CURRENCY_USD, parse_decimal, convert_amount, format_money, format_qty,
)
from .filters import InventoryFilter, salesFilter, product_category_choices
from django.core.paginator import Paginator
from django.views.generic.edit import UpdateView, CreateView
from django.urls import reverse, reverse_lazy
from .forms import EmployeeForm, EmployeeAdminForm, InventoryEditForm
from django.views.generic import ListView
from django.contrib.messages.views import SuccessMessageMixin

from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from datetime import timedelta, datetime
from django.utils import timezone

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.dateparse import parse_date
from django.utils.text import slugify

from django.db.models import (
    Sum, F, ExpressionWrapper, Count, Q, DecimalField,
    Case, When, Value, IntegerField, Max,
)
from django.db.models.functions import Coalesce
from django.db import models

import re
from decimal import Decimal
import json
import uuid
import csv


_ZERO_MONEY = Decimal('0.00')


def _list_page_size(request, default=15, minimum=7, maximum=50):
    """Ekran balandligiga moslashuvchi ro‘yxat: ?per_page=N (JS belgilaydi)."""
    raw = request.GET.get('per_page')
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(maximum, n))


def _allowed_branches_qs(request):
    """StaffAccess / employee bo‘yicha ruxsat etilgan faol filiallar."""
    ids = get_admin_branch_ids(request)
    qs = Branch.objects.filter(is_active=True).order_by('name')
    if ids is None:
        return qs
    if ids is False:
        return qs.none()
    return qs.filter(pk__in=ids)


def _branch_scope_label(request):
    ids = get_admin_branch_ids(request)
    if ids is None:
        return 'Barcha filiallar'
    if ids is False or not ids:
        return 'Tayinlanmagan'
    if len(ids) == 1:
        b = Branch.objects.filter(pk=ids[0]).first()
        return b.name if b else 'Filial'
    return f'{len(ids)} ta filial'


def _active_order_stats_qs():
    return (
        Order.objects.filter(is_active=True, deleted_at__isnull=True)
        .exclude(order_status__in=['AwaitingApproval', 'Cancelled', 'Returned'])
    )


def _user_can_access_order_return(user, order):
    if not can_process_return(user):
        return False
    if is_app_manager(user):
        return True
    emp = get_active_employee(user)
    if emp is None:
        return False
    return order.branch_id == emp.branch_id


def _parse_return_lines(order, raw_items):
    """
    raw_items: [{order_item_id, quantity}, ...]
    Returns list of (OrderItem, qty Decimal) and raises ValueError on bad input.
    """
    if not raw_items:
        raise ValueError('Qaytariladigan mahsulot tanlanmagan.')

    order_items = {
        oi.id: oi
        for oi in order.orderitem_set.select_related('product').all()
    }
    parsed = []
    seen = set()
    for row in raw_items:
        try:
            item_id = int(row.get('order_item_id') or row.get('id'))
        except (TypeError, ValueError):
            raise ValueError('Noto‘g‘ri mahsulot ID.')
        if item_id in seen:
            raise ValueError('Bir xil band ikki marta yuborilgan.')
        seen.add(item_id)
        oi = order_items.get(item_id)
        if oi is None:
            raise ValueError(f'Buyurtmada #{item_id} bandi yo‘q.')
        try:
            qty = parse_decimal(row.get('quantity'))
        except Exception:
            raise ValueError(f'{oi.product.product_name}: miqdor noto‘g‘ri.')
        if qty <= 0:
            raise ValueError(f'{oi.product.product_name}: miqdor 0 dan katta bo‘lishi kerak.')
        returnable = oi.returnable_quantity()
        if qty > returnable:
            raise ValueError(
                f'{oi.product.product_name}: faqat {format_qty(returnable)} qaytarish mumkin '
                f'(so‘ralgan {format_qty(qty)}).'
            )
        parsed.append((oi, qty))
    if not parsed:
        raise ValueError('Qaytariladigan mahsulot tanlanmagan.')
    return parsed


@transaction.atomic
def _execute_sale_return(*, order, employee, lines, reason=''):
    """
    Ishonchli qaytarish: stock +, qarz kamaytirish, naqd qaytarish, komissiya tuzatish.
    lines: [(OrderItem, qty), ...]
    """
    order = (
        Order.objects
        .select_for_update()
        .select_related('branch', 'customer', 'employee')
        .prefetch_related('orderitem_set', 'debts')
        .get(pk=order.pk)
    )
    if not order.is_active or order.deleted_at:
        raise ValueError('Buyurtma arxivlangan — qaytarish mumkin emas.')
    if order.order_status in ('AwaitingApproval', 'Cancelled', 'Returned'):
        raise ValueError('Bu buyurtma holatida qaytarish mumkin emas.')

    # Re-validate under lock
    total = Decimal('0.00')
    prepared = []
    for oi, qty in lines:
        locked_oi = OrderItem.objects.select_for_update().get(pk=oi.pk, order=order)
        returnable = locked_oi.returnable_quantity()
        if qty > returnable:
            raise ValueError(
                f'{locked_oi.product.product_name}: faqat {format_qty(returnable)} qaytarish mumkin.'
            )
        line_total = (qty * locked_oi.unit_price).quantize(Decimal('0.01'))
        total += line_total
        prepared.append((locked_oi, qty, line_total))

    if total <= 0:
        raise ValueError('Qaytarish summasi 0.')

    # Debt first, then cash refund
    debt = order.get_primary_debt()
    debt_remaining = debt.remaining_balance if debt and debt.remaining_balance > 0 else Decimal('0.00')
    debt_reduced = min(total, debt_remaining)
    cash_refunded = (total - debt_reduced).quantize(Decimal('0.01'))

    receipt_number = f"RT-{uuid.uuid4().hex[:10].upper()}"
    sale_return = SaleReturn.objects.create(
        order=order,
        branch=order.branch,
        employee=employee,
        customer=order.customer,
        total_amount=total,
        cash_refunded=cash_refunded,
        debt_reduced=debt_reduced,
        currency=order.currency,
        reason=(reason or '')[:255],
        status='Completed',
        receipt_number=receipt_number,
    )

    for locked_oi, qty, line_total in prepared:
        SaleReturnItem.objects.create(
            sale_return=sale_return,
            order_item=locked_oi,
            product=locked_oi.product,
            quantity=qty,
            unit_price=locked_oi.unit_price,
            line_total=line_total,
        )
        inventory, _created = BranchInventory.objects.select_for_update().get_or_create(
            branch=order.branch,
            product=locked_oi.product,
            defaults={'quantity': Decimal('0')},
        )
        inventory.quantity = (inventory.quantity or Decimal('0')) + qty
        inventory.save(update_fields=['quantity'])

    if debt_reduced > 0 and debt:
        debt = CustomerDebt.objects.select_for_update().get(pk=debt.pk)
        debt.remaining_balance = (debt.remaining_balance - debt_reduced).quantize(Decimal('0.01'))
        if debt.remaining_balance < 0:
            debt.remaining_balance = Decimal('0.00')
        debt.refresh_status()
        debt.save(update_fields=['remaining_balance', 'status', 'updated_at'])

    # Fully returned?
    remaining_any = False
    for oi in order.orderitem_set.all():
        if oi.returnable_quantity() > 0:
            remaining_any = True
            break
    if not remaining_any:
        order.order_status = 'Returned'
        order.save(update_fields=['order_status'])

    # Reverse sales-agent commission on return total
    try:
        agent = order.employee.salesagent
        agent.total_sales = max(Decimal('0.00'), (agent.total_sales or Decimal('0')) - total)
        commission_cut = (total * (agent.commission_rate or Decimal('0'))).quantize(Decimal('0.01'))
        agent.total_commission_earned = max(
            Decimal('0.00'),
            (agent.total_commission_earned or Decimal('0')) - commission_cut,
        )
        agent.save(update_fields=['total_sales', 'total_commission_earned'])
    except Exception:
        pass

    return sale_return


def _customer_purchase_stats(customer):
    orders = _active_order_stats_qs().filter(customer=customer)
    agg = orders.aggregate(
        orders_count=Count('id'),
        total_spent=Coalesce(Sum('total_amount'), _ZERO_MONEY),
        total_discount=Coalesce(Sum('discount_amount'), _ZERO_MONEY),
        last_purchase=Max('order_date'),
    )
    return {
        'orders_count': agg['orders_count'] or 0,
        'total_spent': agg['total_spent'] or _ZERO_MONEY,
        'total_discount': agg['total_discount'] or _ZERO_MONEY,
        'last_purchase': agg['last_purchase'],
    }


def _suggest_bonus_percent(total_spent, orders_count, current_bonus):
    """Reyting asosida shaxsiy aksiya tavsiyasi (foiz)."""
    spent = total_spent or _ZERO_MONEY
    count = orders_count or 0
    suggested = Decimal('0.00')
    if spent >= Decimal('50000000') or count >= 30:
        suggested = Decimal('15.00')
    elif spent >= Decimal('20000000') or count >= 15:
        suggested = Decimal('12.00')
    elif spent >= Decimal('10000000') or count >= 8:
        suggested = Decimal('10.00')
    elif spent >= Decimal('5000000') or count >= 4:
        suggested = Decimal('8.00')
    elif spent >= Decimal('1000000') or count >= 2:
        suggested = Decimal('5.00')
    current = current_bonus or _ZERO_MONEY
    if suggested > current:
        return suggested
    return None


def _checkout_discount_percent(customer, secret_code):
    """Legacy helper: returns discount % only (no markup)."""
    adjust = _checkout_price_adjust(customer, secret_code)
    if adjust['mode'] == 'discount':
        return money_dec(adjust['percent'])
    return money_dec(customer.get_discount_percent() if customer else Decimal('0.00'))


def _checkout_price_adjust(customer, secret_code):
    """
    Returns {'mode': 'discount'|'markup'|'none', 'percent': Decimal}.
    Markup secret code wins over discount code when both match (should be different codes).
    """
    loyalty_pct = money_dec(customer.get_discount_percent() if customer else Decimal('0.00'))
    code = (secret_code or '').strip()
    settings_obj = AppSettings.get_solo()
    if code:
        markup_code = (settings_obj.pos_secret_markup_code or '').strip()
        if markup_code and code == markup_code:
            markup_pct = money_dec(settings_obj.pos_secret_markup_percent or 0)
            if markup_pct > 0:
                return {'mode': 'markup', 'percent': markup_pct}
        discount_code = (settings_obj.pos_secret_code or '').strip()
        if discount_code and code == discount_code:
            secret_pct = money_dec(settings_obj.pos_secret_discount_percent or 0)
            if secret_pct > loyalty_pct:
                return {'mode': 'discount', 'percent': secret_pct}
    if loyalty_pct > 0:
        return {'mode': 'discount', 'percent': loyalty_pct}
    return {'mode': 'none', 'percent': money_dec(0)}


def _parse_cart_qty(raw, product=None):
    """Savat miqdorini Decimal qilib olish (m/kg uchun kasr ruxsat)."""
    qty = parse_decimal(raw)
    if qty <= 0:
        raise ValueError('Miqdor 0 dan katta bo‘lishi kerak')
    fractional = product.allows_fractional_qty() if product else True
    if not fractional:
        if qty != qty.to_integral_value():
            raise ValueError('Bu mahsulot uchun butun son kerak')
        qty = qty.to_integral_value()
    return qty.quantize(Decimal('0.001'))


def _product_price_payload(product):
    """POS / scan API uchun narx + skidka maydonlari."""
    base = product.base_price or Decimal('0.00')
    effective = product.get_effective_price()
    sale_on = product.is_sale_active()
    return {
        'price': str(effective),
        'list_price': str(base),
        'sale_active': sale_on,
        'sale_discount_percent': str(product.get_sale_discount_percent() if sale_on else Decimal('0.00')),
    }


def _price_lines_from_cart(cart, adjust):
    priced_lines = []
    list_total = Decimal('0.00')
    net_total = Decimal('0.00')
    mode = adjust.get('mode') or 'none'
    percent = money_dec(adjust.get('percent') or 0)
    for item in cart:
        product = Product.objects.get(id=item['id'])
        qty = _parse_cart_qty(item.get('qty'), product)
        price_adjusted = bool(item.get('priceAdjusted') or item.get('price_adjusted'))
        catalog_price = money_dec(product.base_price)
        if price_adjusted:
            # Qo‘lda tahrir — mijoz yuborgan narx (original = katalog)
            sale_base = money_dec(item.get('price', product.get_effective_price()))
            client_list = money_dec(
                item.get('originalPrice', item.get('original_price', catalog_price))
            )
            stored_list = client_list
        else:
            # Server truth: mahsulot skidkasi
            sale_base = money_dec(product.get_effective_price())
            stored_list = catalog_price
        # list_price for order totals = before cart-wide loyalty/secret
        list_price = sale_base
        if mode == 'markup':
            unit_price = apply_markup(list_price, percent)
        elif mode == 'discount':
            unit_price = apply_discount(list_price, percent)
        else:
            unit_price = list_price
        priced_lines.append((product, qty, stored_list, unit_price, price_adjusted))
        list_total += list_price * qty
        net_total += unit_price * qty
    list_total = money_dec(list_total)
    net_total = money_dec(net_total)
    if mode == 'markup':
        discount_percent = money_dec(0)
        discount_amount = money_dec(0)
        markup_percent = percent
        markup_amount = money_dec(net_total - list_total)
    elif mode == 'discount':
        discount_percent = percent
        discount_amount = money_dec(list_total - net_total)
        markup_percent = money_dec(0)
        markup_amount = money_dec(0)
    else:
        discount_percent = money_dec(0)
        discount_amount = money_dec(0)
        markup_percent = money_dec(0)
        markup_amount = money_dec(0)
    return {
        'priced_lines': priced_lines,
        'list_total': list_total,
        'net_total': net_total,
        'discount_percent': discount_percent,
        'discount_amount': discount_amount,
        'markup_percent': markup_percent,
        'markup_amount': markup_amount,
    }


@login_required(login_url='login')
@portal_cap_required('btn_product_edit')
def inventory_update(request, pk):
    if is_consultant(request.user):
        return redirect('pos_terminal')

    inventory = get_object_or_404(
        BranchInventory.objects.select_related('product', 'product__supplier', 'branch'),
        pk=pk,
        product__is_active=True,
        branch__is_active=True,
    )

    if not _is_inventory_manager(request.user):
        emp_branch = getattr(getattr(request.user, 'employee', None), 'branch', None)
        if not emp_branch or emp_branch.id != inventory.branch_id:
            raise PermissionDenied('Bu filial omborini tahrirlash huquqi yo‘q')

    if request.method == 'POST':
        form = InventoryEditForm(request.POST, request.FILES, inventory=inventory)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"«{inventory.product.product_name}» ma’lumotlari yangilandi "
                f"({inventory.branch.name}, qoldiq: {inventory.quantity})",
            )
            return redirect('branch_inventory')
    else:
        form = InventoryEditForm(inventory=inventory)

    return render(request, 'accounts/inventory_update.html', {
        'form': form,
        'inventory': inventory,
        'object': inventory,
        'usd_rate': str(AppSettings.get_solo().usd_to_uzs),
        'is_manager': _is_inventory_manager(request.user),
    })

class salesUpdateView(UpdateView):
    model = Order
    fields = ['employee', 'order_status']
    template_name = 'components/sales_edit.html'
    success_url = reverse_lazy('sales_display')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['invoice'] = Invoice.objects.filter(order=self.object).first()
        return context

@login_required(login_url='login')
@portal_cap_required('btn_sale_delete')
def delete_order(request, pk):
    order = get_object_or_404(Order, pk=pk)

    order.soft_delete()

    messages.success(request, f"Buyurtma{order.id} arxivlandi")

    return redirect('sales_display')

def _reports_resolve_period(request):

    now = timezone.localtime(timezone.now())
    today = now.date()
    preset = (request.GET.get('period') or '30d').strip().lower()
    start_raw = (request.GET.get('start_date') or '').strip()
    end_raw = (request.GET.get('end_date') or '').strip()
    start_d = parse_date(start_raw) if start_raw else None
    end_d = parse_date(end_raw) if end_raw else None

    if start_d or end_d:
        preset = 'custom'
        if start_d and end_d and start_d > end_d:
            start_d, end_d = end_d, start_d
        if not start_d:
            start_d = today - timedelta(days=30)
        if not end_d:
            end_d = today
    elif preset == 'week':
        start_d = (now - timedelta(days=now.weekday())).date()
        end_d = today
    elif preset == 'month':
        start_d = today.replace(day=1)
        end_d = today
    elif preset == 'year':
        start_d = today.replace(month=1, day=1)
        end_d = today
    elif preset == 'all':
        start_d = None
        end_d = today
    else:
        preset = '30d'
        start_d = today - timedelta(days=30)
        end_d = today

    tz = timezone.get_current_timezone()
    if start_d:
        start_dt = timezone.make_aware(datetime.combine(start_d, datetime.min.time()), tz)
    else:
        start_dt = None
    end_dt = timezone.make_aware(
        datetime.combine(end_d or today, datetime.max.time().replace(microsecond=0)),
        tz,
    )

    labels = {
        'week': 'Shu hafta',
        'month': 'Shu oy',
        'year': 'Shu yil',
        '30d': 'So‘nggi 30 kun',
        'all': 'Barcha vaqt',
        'custom': 'Maxsus davr',
    }
    if preset == 'custom' and start_d and end_d:
        period_label = f"{start_d.strftime('%d.%m.%Y')} — {end_d.strftime('%d.%m.%Y')}"
    elif preset == 'all':
        period_label = 'Barcha vaqt'
    else:
        period_label = labels.get(preset, 'So‘nggi 30 kun')

    return {
        'preset': preset,
        'start_d': start_d,
        'end_d': end_d or today,
        'start_dt': start_dt,
        'end_dt': end_dt,
        'period_label': period_label,
        'start_str': start_d.isoformat() if start_d else '',
        'end_str': (end_d or today).isoformat(),
    }

def _reports_build_context(request):

    period = _reports_resolve_period(request)

    zero = Decimal('0.00')
    usd_rate = AppSettings.get_solo().usd_to_uzs
    start_dt = period['start_dt']
    end_dt = period['end_dt']
    start_d = period['start_d']
    end_d = period['end_d']

    def to_uzs(amount, currency):
        amount = amount or zero
        if (currency or CURRENCY_UZS) == CURRENCY_USD:
            return convert_amount(amount, CURRENCY_USD, CURRENCY_UZS, usd_rate)
        return Decimal(amount)

    def sum_order_items_uzs(item_qs):
        revenue = zero
        cost_sum = zero
        units = 0
        order_ids = set()
        cash = zero
        for item in item_qs.select_related('order').iterator():
            order = item.order
            cur = getattr(order, 'currency', None) or CURRENCY_UZS
            line = (item.unit_price or zero) * (item.quantity or 0)
            line_cost = (item.cost_price or zero) * (item.quantity or 0)
            line_uzs = to_uzs(line, cur)
            cost_uzs = to_uzs(line_cost, cur)
            revenue += line_uzs
            cost_sum += cost_uzs
            units += float(item.quantity or 0)
            if item.order_id:
                order_ids.add(item.order_id)
            if order and order.payment_method == 'CASH':
                cash += line_uzs
        return {
            'revenue': revenue,
            'cost': cost_sum,
            'units': units,
            'orders': len(order_ids),
            'cash': cash,
        }

    def sum_return_items_uzs(return_item_qs):
        """Qaytarilgan mahsulotlar: savdo/tannarx/dona kamaytirish uchun."""
        revenue = zero
        cost_sum = zero
        units = 0
        return_ids = set()
        cash_refund = zero
        debt_reduced = zero
        for ri in return_item_qs.select_related(
            'sale_return', 'order_item', 'product'
        ).iterator():
            ret = ri.sale_return
            if not ret or ret.status != 'Completed' or not ret.is_active:
                continue
            cur = getattr(ret, 'currency', None) or CURRENCY_UZS
            line = ri.line_total if ri.line_total is not None else (
                (ri.unit_price or zero) * (ri.quantity or 0)
            )
            oi = ri.order_item
            line_cost = (getattr(oi, 'cost_price', None) or zero) * (ri.quantity or 0)
            revenue += to_uzs(line, cur)
            cost_sum += to_uzs(line_cost, cur)
            units += float(ri.quantity or 0)
            if ret.id:
                return_ids.add(ret.id)
        # Naqd/qarz qaytarish — SaleReturn header bo‘yicha (takrorlanmasin)
        for ret in SaleReturn.objects.filter(id__in=return_ids).iterator():
            cur = getattr(ret, 'currency', None) or CURRENCY_UZS
            cash_refund += to_uzs(ret.cash_refunded or zero, cur)
            debt_reduced += to_uzs(ret.debt_reduced or zero, cur)
        return {
            'revenue': revenue,
            'cost': cost_sum,
            'units': units,
            'returns': len(return_ids),
            'cash_refunded': cash_refund,
            'debt_reduced': debt_reduced,
        }

    def apply_returns_net(sales, returns):
        return {
            'revenue': (sales['revenue'] or zero) - (returns['revenue'] or zero),
            'cost': (sales['cost'] or zero) - (returns['cost'] or zero),
            'units': float(sales['units'] or 0) - float(returns['units'] or 0),
            'orders': sales['orders'],
            'cash': (sales['cash'] or zero) - (returns['cash_refunded'] or zero),
        }

    def returns_in_range(start=None, end=None):
        qs = scope_queryset_by_branch(
            SaleReturnItem.objects.filter(
                sale_return__status='Completed',
                sale_return__is_active=True,
            ),
            request,
            field='sale_return__branch_id',
        )
        if end is not None:
            qs = qs.filter(sale_return__return_date__lte=end)
        if start is not None:
            qs = qs.filter(sale_return__return_date__gte=start)
        return sum_return_items_uzs(qs)

    def sum_orders_field_uzs(order_qs, field='total_amount'):
        total = zero
        for order in order_qs.only('currency', field).iterator():
            total += to_uzs(getattr(order, field, zero) or zero, order.currency)
        return total

    def sum_money_rows_uzs(qs, amount_field, currency_field='currency'):
        total = zero
        for row in qs.only(amount_field, currency_field).iterator():
            total += to_uzs(
                getattr(row, amount_field, zero) or zero,
                getattr(row, currency_field, CURRENCY_UZS),
            )
        return total

    stock_units = 0
    stock_cost_uzs = zero
    stock_retail_uzs = zero
    low_stock_count = 0
    inv_rows = scope_queryset_by_branch(
        BranchInventory.objects
        .filter(branch__is_active=True, product__is_active=True),
        request,
    ).select_related('product')
    for row in inv_rows.iterator():
        qty = parse_decimal(row.quantity or 0)
        if qty <= 0:
            continue
        stock_units += qty
        cost_cur = getattr(row.product, 'cost_currency', None) or row.product.currency
        stock_cost_uzs += to_uzs(row.product.cost_price * qty, cost_cur)
        stock_retail_uzs += to_uzs(row.product.base_price * qty, row.product.currency)
        min_lvl = parse_decimal(row.product.min_stock_level or 0)
        if qty <= min_lvl:
            low_stock_count += 1

    period_orders = scope_queryset_by_branch(
        Order.objects.filter(
            order_date__lte=end_dt,
            employee__is_active=True,
            branch__is_active=True,
            is_active=True,
        ).exclude(order_status__in=['AwaitingApproval', 'Cancelled']),
        request,
    )
    if start_dt:
        period_orders = period_orders.filter(order_date__gte=start_dt)
    active_order_ids = list(period_orders.values_list('id', flat=True))

    sales_gross = sum_order_items_uzs(OrderItem.objects.filter(order_id__in=active_order_ids))
    returns_period = returns_in_range(start_dt, end_dt)
    stats_uzs = apply_returns_net(sales_gross, returns_period)
    stats = {
        'total_revenue': stats_uzs['revenue'],
        'total_cost': stats_uzs['cost'],
        'sold_units': stats_uzs['units'],
        'total_count': stats_uzs['orders'],
    }

    # Tanlangan davr = asosiy hisobot; "barcha vaqt / hafta / oy" alohida emas
    all_sales = stats_uzs
    week = stats_uzs
    month = stats_uzs
    year = stats_uzs

    # Operatsiya hisoblari (davr)
    ops_awaiting = scope_queryset_by_branch(Order.objects.filter(
        is_active=True, order_status='AwaitingApproval', order_date__lte=end_dt,
    ), request)
    ops_cancelled = scope_queryset_by_branch(Order.objects.filter(
        is_active=True, order_status='Cancelled', order_date__lte=end_dt,
    ), request)
    ops_returned_full = scope_queryset_by_branch(Order.objects.filter(
        is_active=True, order_status='Returned', order_date__lte=end_dt,
    ), request)
    if start_dt:
        ops_awaiting = ops_awaiting.filter(order_date__gte=start_dt)
        ops_cancelled = ops_cancelled.filter(order_date__gte=start_dt)
        ops_returned_full = ops_returned_full.filter(order_date__gte=start_dt)
    ops_awaiting_count = ops_awaiting.count()
    ops_cancelled_count = ops_cancelled.count()
    ops_returned_full_count = ops_returned_full.count()
    period_returns_qs = scope_queryset_by_branch(SaleReturn.objects.filter(
        status='Completed', is_active=True, return_date__lte=end_dt,
    ), request)
    if start_dt:
        period_returns_qs = period_returns_qs.filter(return_date__gte=start_dt)
    top_returns = (
        period_returns_qs
        .select_related('order', 'branch', 'employee', 'customer')
        .order_by('-return_date')[:8]
    )

    # Qarzlar — faqat tanlangan davr (yaratilgan / to‘langan)
    debts_period = scope_queryset_by_branch(
        CustomerDebt.objects.filter(created_at__lte=end_dt), request
    )
    if start_dt:
        debts_period = debts_period.filter(created_at__gte=start_dt)
    open_debts = debts_period.exclude(status='Paid')
    paid_debts_period = debts_period.filter(status='Paid')
    debt_stats = {
        'open_remaining': sum_money_rows_uzs(open_debts, 'remaining_balance'),
        'open_original': sum_money_rows_uzs(open_debts, 'original_amount'),
        'total_paid_on_debts': sum_money_rows_uzs(debts_period, 'paid_amount'),
        'open_count': open_debts.count(),
        'paid_count': paid_debts_period.count(),
        'all_count': debts_period.count(),
    }
    debt_pay_qs = scope_queryset_by_branch(
        DebtPayment.objects.filter(paid_at__lte=end_dt).select_related('debt'),
        request,
        field='debt__branch_id',
    )
    if start_dt:
        debt_pay_qs = debt_pay_qs.filter(paid_at__gte=start_dt)

    def sum_debt_payments_uzs(qs):
        total = zero
        for pay in qs.iterator():
            cur = getattr(getattr(pay, 'debt', None), 'currency', None) or CURRENCY_UZS
            total += to_uzs(pay.amount or zero, cur)
        return total

    debt_collected_period = sum_debt_payments_uzs(debt_pay_qs)
    debt_collected = debt_collected_period
    debt_collected_month = debt_collected_period

    exp_period = scope_queryset_by_branch(
        Expense.objects.filter(is_active=True, expense_date__lte=end_d), request
    )
    if start_d:
        exp_period = exp_period.filter(expense_date__gte=start_d)
    expense_period = sum_money_rows_uzs(exp_period, 'amount')
    expense_count = exp_period.count()
    expense_total = expense_period
    expense_month = expense_period
    top_expenses = exp_period.select_related('branch').order_by('-expense_date', '-id')[:8]

    cash_received = zero
    for cp in CashPayment.objects.filter(
        payment__order_id__in=active_order_ids,
        payment__order__is_active=True,
    ).select_related('payment__order').iterator():
        cur = getattr(getattr(cp.payment, 'order', None), 'currency', None) or CURRENCY_UZS
        cash_received += to_uzs(cp.cash_received or zero, cur)
    cash_refunded = returns_period['cash_refunded'] or zero
    cash_net = cash_received - cash_refunded

    payments = {'cash': stats_uzs['cash']}

    branch_totals_map = {}
    employee_totals_map = {}
    for order in Order.objects.filter(id__in=active_order_ids).select_related('branch', 'employee'):
        amount = to_uzs(order.total_amount or zero, order.currency)
        bname = order.branch.name if order.branch_id else "Asosiy do‘kon"
        ename = order.employee.name if order.employee_id else "Tizim administratori"
        branch_totals_map[bname] = branch_totals_map.get(bname, zero) + amount
        employee_totals_map[ename] = employee_totals_map.get(ename, zero) + amount
    for ret in period_returns_qs.select_related('branch', 'employee').iterator():
        amount = to_uzs(ret.total_amount or zero, ret.currency)
        bname = ret.branch.name if ret.branch_id else "Asosiy do‘kon"
        ename = ret.employee.name if ret.employee_id else "Tizim administratori"
        branch_totals_map[bname] = branch_totals_map.get(bname, zero) - amount
        employee_totals_map[ename] = employee_totals_map.get(ename, zero) - amount
    branch_names = []
    branch_totals = []
    for name, total in sorted(branch_totals_map.items(), key=lambda x: x[1], reverse=True):
        branch_names.append(name)
        branch_totals.append(float(total))
    employee_names = []
    employee_totals = []
    for name, total in sorted(employee_totals_map.items(), key=lambda x: x[1], reverse=True):
        employee_names.append(name)
        employee_totals.append(float(total))

    product_qty_map = {}
    for row in (
        OrderItem.objects.filter(order_id__in=active_order_ids)
        .values('product__product_name')
        .annotate(total=Sum('quantity'))
    ):
        name = row['product__product_name'] or "Noma’lum"
        product_qty_map[name] = float(row['total'] or 0)
    ret_product_qs = scope_queryset_by_branch(
        SaleReturnItem.objects.filter(
            sale_return__status='Completed',
            sale_return__is_active=True,
            sale_return__return_date__lte=end_dt,
        ),
        request,
        field='sale_return__branch_id',
    )
    if start_dt:
        ret_product_qs = ret_product_qs.filter(sale_return__return_date__gte=start_dt)
    for row in ret_product_qs.values('product__product_name').annotate(total=Sum('quantity')):
        name = row['product__product_name'] or "Noma’lum"
        product_qty_map[name] = product_qty_map.get(name, 0.0) - float(row['total'] or 0)
    product_ranked = sorted(product_qty_map.items(), key=lambda x: x[1], reverse=True)[:5]
    product_name = [n for n, _ in product_ranked]
    product_totals = [t for _, t in product_ranked]

    sales_gross_revenue = sales_gross['revenue'] or zero
    returns_revenue = returns_period['revenue'] or zero
    returns_cost = returns_period['cost'] or zero
    returns_units = returns_period['units'] or 0
    returns_count = returns_period['returns'] or 0
    returns_debt_reduced = returns_period['debt_reduced'] or zero

    gross_revenue = stats['total_revenue'] or zero  # sof savdo (yalpi − qaytarish)
    cost = stats['total_cost'] or zero
    total_count = stats['total_count'] or 0
    sold_units = stats['sold_units'] or 0
    if sold_units < 0:
        sold_units = 0
    net_profit = gross_revenue - cost
    net_after_expenses = net_profit - (expense_period or zero)
    summary_sof_foyda = (
        (net_profit or zero)
        - (debt_stats['open_remaining'] or zero)
        - (expense_period or zero)
    )
    cash_total = payments['cash'] or zero
    aov = (gross_revenue / total_count) if total_count > 0 else zero

    top_debts = (
        open_debts
        .select_related('customer', 'branch')
        .order_by('-remaining_balance')[:8]
    )

    reservation_period = scope_queryset_by_branch(
        ProductReservation.objects.filter(created_at__lte=end_dt), request
    )
    if start_dt:
        reservation_period = reservation_period.filter(created_at__gte=start_dt)
    active_reservations = reservation_period.filter(status='Active')
    reservation_period_units = reservation_period.aggregate(
        u=Coalesce(Sum('unit_count'), 0)
    )['u'] or 0
    reservation_period_total = sum_money_rows_uzs(reservation_period, 'total_amount')
    reservation_stats = {
        'active_count': active_reservations.count(),
        'active_units': active_reservations.aggregate(
            u=Coalesce(Sum('unit_count'), 0)
        )['u'] or 0,
        'active_items': active_reservations.aggregate(
            i=Coalesce(Sum('item_count'), 0)
        )['i'] or 0,
        'active_total': sum_money_rows_uzs(active_reservations, 'total_amount'),
        'period_count': reservation_period.count(),
        'period_units': reservation_period_units,
        'period_total': reservation_period_total,
    }
    top_reservations = (
        reservation_period.select_related('customer', 'branch', 'employee')
        .order_by('-created_at')[:8]
    )

    transactions = scope_queryset_by_branch(Order.objects.filter(
        employee__is_active=True,
        branch__is_active=True,
        is_active=True,
        order_date__lte=end_dt,
    ), request)
    if start_dt:
        transactions = transactions.filter(order_date__gte=start_dt)
    transactions = (
        transactions
        .select_related('customer', 'branch', 'employee')
        .prefetch_related('orderitem_set__product', 'debts')
        .order_by('-order_date')
    )

    query_string = request.GET.urlencode()

    partner_orders = period_orders.filter(partner__isnull=False)
    partner_sales_total = sum_orders_field_uzs(partner_orders, 'total_amount')
    partner_discount_total = sum_orders_field_uzs(partner_orders, 'discount_amount')
    loyalty_discount_total = sum_orders_field_uzs(
        period_orders.filter(discount_percent__gt=0), 'discount_amount'
    )

    partner_map = {}
    for order in partner_orders.select_related('partner').iterator():
        pid = order.partner_id
        if not pid:
            continue
        row = partner_map.setdefault(pid, {
            'partner_id': pid,
            'partner__name': order.partner.name if order.partner_id else '',
            'partner__phone': order.partner.phone if order.partner_id else '',
            'orders': 0,
            'total': zero,
            'discount': zero,
        })
        row['orders'] += 1
        row['total'] += to_uzs(order.total_amount or zero, order.currency)
        row['discount'] += to_uzs(order.discount_amount or zero, order.currency)
    top_partners = sorted(partner_map.values(), key=lambda r: r['total'], reverse=True)[:10]

    discount_kinds = list(
        PriceTier.objects.exclude(kind=PriceTier.KIND_REGULAR)
        .filter(is_active=True)
        .values_list('kind', flat=True)
    )
    if not discount_kinds:
        discount_kinds = [Customer.TYPE_LOYAL, Customer.TYPE_PARTNER]
    customer_period_orders = period_orders.filter(
        customer__isnull=False,
        customer__customer_type__in=discount_kinds,
    )
    loyal_map = {}
    for order in customer_period_orders.select_related('customer').iterator():
        cid = order.customer_id
        if not cid:
            continue
        c = order.customer
        row = loyal_map.setdefault(cid, {
            'customer_id': cid,
            'customer__name': c.name,
            'customer__phone': c.phone or '',
            'customer__customer_type': c.customer_type,
            'customer__bonus_discount_percent': c.bonus_discount_percent or zero,
            'orders': 0,
            'total': zero,
            'discount': zero,
        })
        row['orders'] += 1
        row['total'] += to_uzs(order.total_amount or zero, order.currency)
        row['discount'] += to_uzs(order.discount_amount or zero, order.currency)
    top_loyal_customers = sorted(loyal_map.values(), key=lambda r: r['total'], reverse=True)[:15]
    tier_name_map = {
        t.kind: t.name
        for t in PriceTier.objects.filter(kind__in=discount_kinds)
    }
    top_loyal_rows = []
    for i, row in enumerate(top_loyal_customers, start=1):
        ctype = row['customer__customer_type']
        top_loyal_rows.append({
            'rank': i,
            'customer_id': row['customer_id'],
            'name': row['customer__name'],
            'phone': row['customer__phone'] or '—',
            'type_label': tier_name_map.get(ctype, ctype),
            'orders': row['orders'],
            'total': row['total'],
            'discount': row['discount'],
            'bonus': row['customer__bonus_discount_percent'] or zero,
            'suggested_bonus': _suggest_bonus_percent(
                row['total'], row['orders'], row['customer__bonus_discount_percent']
            ),
        })
    # Mijoz sonlari — faqat davrdagi savdosi bo‘lganlar
    period_customer_ids = period_orders.exclude(customer_id=None).values_list('customer_id', flat=True).distinct()
    loyal_count = Customer.objects.filter(
        id__in=period_customer_ids, customer_type=Customer.TYPE_LOYAL
    ).count()
    partner_count = Customer.objects.filter(
        id__in=period_customer_ids, customer_type=Customer.TYPE_PARTNER
    ).count()
    loyalty_customers_count = Customer.objects.filter(
        id__in=period_customer_ids, customer_type__in=discount_kinds
    ).count()

    return {
        'period_label': period['period_label'],
        'period_preset': period['preset'],
        'start_date_str': period['start_str'],
        'end_date_str': period['end_str'],
        'query_string': query_string,
        'sales_gross_revenue': sales_gross_revenue,
        'gross_revenue': gross_revenue,
        'returns_revenue': returns_revenue,
        'returns_cost': returns_cost,
        'returns_units': returns_units,
        'returns_count': returns_count,
        'returns_cash_refunded': cash_refunded,
        'returns_debt_reduced': returns_debt_reduced,
        'top_returns': top_returns,
        'ops_awaiting_count': ops_awaiting_count,
        'ops_cancelled_count': ops_cancelled_count,
        'ops_returned_full_count': ops_returned_full_count,
        'partner_sales_total': partner_sales_total,
        'partner_discount_total': partner_discount_total,
        'loyalty_discount_total': loyalty_discount_total,
        'top_partners': top_partners,
        'top_loyal_customers': top_loyal_rows,
        'loyal_count': loyal_count,
        'partner_count': partner_count,
        'loyalty_customers_count': loyalty_customers_count,
        'cost': cost,
        'net_profit': net_profit,
        'aov': aov,
        'sold_units': sold_units,
        'total_transactions': total_count,
        'cash_total': cash_total,
        'cash_received': cash_received,
        'cash_refunded': cash_refunded,
        'cash_net': cash_net,
        'stock_units': stock_units,
        'stock_cost_uzs': stock_cost_uzs,
        'stock_retail_uzs': stock_retail_uzs,
        'stock_potential_profit': stock_retail_uzs - stock_cost_uzs,
        'low_stock_count': low_stock_count,
        'all_revenue': all_sales['revenue'],
        'all_cost': all_sales['cost'],
        'all_profit': (all_sales['revenue'] or zero) - (all_sales['cost'] or zero),
        'all_units': max(0, all_sales['units'] or 0),
        'all_orders': all_sales['orders'],
        'weekly_total': week['revenue'],
        'weekly_cost': week['cost'],
        'weekly_units': max(0, week['units'] or 0),
        'monthly_total': month['revenue'],
        'monthly_cost': month['cost'],
        'monthly_units': max(0, month['units'] or 0),
        'yearly_total': year['revenue'],
        'yearly_cost': year['cost'],
        'yearly_units': max(0, year['units'] or 0),
        'outstanding_balance': debt_stats['open_remaining'],
        'debt_open_original': debt_stats['open_original'],
        'debt_total_paid': debt_stats['total_paid_on_debts'],
        'debt_collected': debt_collected,
        'debt_collected_period': debt_collected_period,
        'debt_collected_month': debt_collected_month,
        'debt_open_count': debt_stats['open_count'],
        'debt_paid_count': debt_stats['paid_count'],
        'debt_all_count': debt_stats['all_count'],
        'top_debts': top_debts,
        'reservation_active_count': reservation_stats['active_count'],
        'reservation_active_units': reservation_stats['active_units'],
        'reservation_active_items': reservation_stats['active_items'],
        'reservation_active_total': reservation_stats['active_total'],
        'reservation_period_count': reservation_stats['period_count'],
        'reservation_period_units': reservation_stats['period_units'],
        'reservation_period_total': reservation_stats['period_total'],
        'top_reservations': top_reservations,
        'expense_total': expense_total,
        'expense_month': expense_month,
        'expense_period': expense_period,
        'expense_count': expense_count,
        'net_after_expenses': net_after_expenses,
        'summary_sof_foyda': summary_sof_foyda,
        'top_expenses': top_expenses,
        'transactions_qs': transactions,
        'branch_names': json.dumps(branch_names, ensure_ascii=False),
        'branch_totals': json.dumps(branch_totals),
        'employee_names': json.dumps(employee_names, ensure_ascii=False),
        'employee_totals': json.dumps(employee_totals),
        'product_name': json.dumps(product_name, ensure_ascii=False),
        'product_totals': json.dumps(product_totals),
    }

@login_required(login_url='login')
@portal_cap_required('reports')
def admin_reports(request):

    context = _reports_build_context(request)
    transactions = context.pop('transactions_qs')
    context['page_obj'] = Paginator(transactions, 8).get_page(request.GET.get('page'))
    return render(request, 'accounts/admin_reports.html', context)

@login_required(login_url='login')
@portal_cap_required('btn_export')
def admin_reports_export_csv(request):

    ctx = _reports_build_context(request)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    fname = f"hisobot_{ctx['start_date_str'] or 'all'}_{ctx['end_date_str']}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.write('\ufeff')
    writer = csv.writer(response)

    writer.writerow(['Hisobot', ctx['period_label']])
    writer.writerow(['Boshlanish', ctx['start_date_str'] or '—'])
    writer.writerow(['Tugash', ctx['end_date_str']])
    writer.writerow([])
    writer.writerow(['Ko‘rsatkich', 'Summa'])
    writer.writerow(['Yalpi sotuv', ctx['sales_gross_revenue']])
    writer.writerow(['Qaytarish summasi', ctx['returns_revenue']])
    writer.writerow(['Sof sotuv', ctx['gross_revenue']])
    writer.writerow(['Tannarx (sof)', ctx['cost']])
    writer.writerow(['Foyda', ctx['net_profit']])
    writer.writerow(['Ochiq qarz', ctx['outstanding_balance']])
    writer.writerow(['Xarajat (davr)', ctx['expense_period']])
    writer.writerow(['Sof foyda (foyda−qarz−xarajat)', ctx['summary_sof_foyda']])
    writer.writerow(['Sof dona', ctx['sold_units']])
    writer.writerow(['Qaytarilgan dona', ctx['returns_units']])
    writer.writerow(['Qaytarishlar soni', ctx['returns_count']])
    writer.writerow(['Naqd qaytarilgan', ctx['cash_refunded']])
    writer.writerow(['Qarz kamaytirilgan (qaytarish)', ctx['returns_debt_reduced']])
    writer.writerow(['Buyurtmalar', ctx['total_transactions']])
    writer.writerow(['Tasdiq kutilmoqda', ctx['ops_awaiting_count']])
    writer.writerow(['Bekor qilingan', ctx['ops_cancelled_count']])
    writer.writerow(['To‘liq qaytarilgan buyurtma', ctx['ops_returned_full_count']])
    writer.writerow(['Naqd savdo (sof)', ctx['cash_total']])
    writer.writerow(['Kassaga tushgan', ctx['cash_received']])
    writer.writerow(['Sof kassa', ctx['cash_net']])
    writer.writerow(['Ombor dona', ctx['stock_units']])
    writer.writerow(['Ombor tannarx', ctx['stock_cost_uzs']])
    writer.writerow(['Ombor sotish narxi', ctx['stock_retail_uzs']])
    writer.writerow(['Davrda undirilgan qarz', ctx['debt_collected_period']])
    writer.writerow(['Davr ochiq qarz', ctx['outstanding_balance']])
    writer.writerow(['Davr qarzlari (soni)', ctx['debt_all_count']])
    writer.writerow(['Davr bronlari (soni)', ctx['reservation_period_count']])
    writer.writerow(['Davr bronlari (summa)', ctx['reservation_period_total']])
    writer.writerow(['Davrdan hali faol bron', ctx['reservation_active_count']])
    writer.writerow([])
    writer.writerow([
        'Buyurtma ID', 'Sana', 'Mijoz', 'Xodim', 'Filial',
        'Summa', 'Valyuta', 'Qarz qoldiq', 'Holat',
    ])
    for tx in ctx['transactions_qs'][:2000]:
        debt = tx.get_primary_debt()
        writer.writerow([
            tx.id,
            tx.order_date.strftime('%Y-%m-%d %H:%M') if tx.order_date else '',
            tx.customer.name if tx.customer else '—',
            tx.employee.name if tx.employee else '—',
            tx.branch.name if tx.branch else '—',
            tx.total_amount,
            tx.currency,
            debt.remaining_balance if debt and debt.remaining_balance > 0 else '',
            tx.get_order_status_display(),
        ])
    return response

@login_required(login_url='login')
def emp_receipt(request, pk):

    order = get_object_or_404(
        Order.objects.select_related('branch', 'customer', 'employee__user')
        .prefetch_related('debts', 'payment_set__cashpayment', 'orderitem_set__product'),
        pk=pk,
    )
    if not is_app_manager(request.user):
        emp = get_active_employee(request.user)
        if not emp or order.employee_id != emp.id:
            messages.error(request, 'Bu chek sizga tegishli emas.')
            return redirect('sales_display')
    invoice = Invoice.objects.filter(order=order).first()
    grand_total = order.total_amount or Decimal('0.00')
    if invoice:
        vat_amount = invoice.vat_amount or Decimal('0.00')
        subtotal = (grand_total - vat_amount).quantize(Decimal('0.01'))
    else:
        app_settings = AppSettings.get_solo()
        factor = app_settings.vat_factor()
        subtotal = (grand_total / factor).quantize(Decimal('0.01')) if factor else grand_total
        vat_amount = (grand_total - subtotal).quantize(Decimal('0.01'))

    vat_label = 'QQS'
    if vat_amount > 0 and subtotal > 0:
        pct = (vat_amount / subtotal * Decimal('100')).quantize(Decimal('0.01'))
        vat_label = f'QQS {pct}%'

    org = getattr(order.branch, 'organization', None) or Organization.get_default()
    org_logo = None
    if org and org.logo:
        try:
            org_logo = org.logo.url
        except Exception:
            org_logo = None

    awaiting_approval = order.order_status == 'AwaitingApproval'
    cash_received = order.get_cash_received()
    if cash_received is None and not awaiting_approval and order.order_status == 'Completed':
        cash_received = grand_total
    if cash_received is None:
        cash_received = Decimal('0.00')
    change_given = order.get_change_given()
    debt = order.get_primary_debt()
    debt_remaining = debt.remaining_balance if debt else Decimal('0.00')
    debt_original = debt.original_amount if debt else Decimal('0.00')
    has_debt = bool(debt and debt_remaining > 0)
    is_paid = (not awaiting_approval) and order.payment_set.exists() and not has_debt

    list_total = order.list_total or Decimal('0.00')
    if list_total <= 0:
        list_total = subtotal
    discount_amount = order.discount_amount or Decimal('0.00')
    if discount_amount <= 0 and list_total > subtotal:
        discount_amount = (list_total - subtotal).quantize(Decimal('0.01'))
    discount_percent = order.discount_percent or Decimal('0.00')
    markup_amount = Decimal('0.00')
    markup_percent = Decimal('0.00')
    if subtotal > list_total and discount_amount <= 0:
        markup_amount = (subtotal - list_total).quantize(Decimal('0.01'))
        if list_total > 0:
            markup_percent = (markup_amount / list_total * Decimal('100')).quantize(Decimal('0.01'))

    context = {
        'order': order,
        'invoice': invoice,
        'subtotal': subtotal,
        'list_total': list_total,
        'discount_amount': discount_amount,
        'discount_percent': discount_percent,
        'markup_amount': markup_amount,
        'markup_percent': markup_percent,
        'vat_amount': vat_amount,
        'vat_label': vat_label,
        'grand_total': grand_total,
        'cash_received': cash_received,
        'change_given': change_given,
        'debt': debt,
        'debt_remaining': debt_remaining,
        'debt_original': debt_original,
        'has_debt': has_debt,
        'is_paid': is_paid,
        'awaiting_approval': awaiting_approval,
        'organization_name': order.branch.organization_name if order.branch_id else org.name,
        'brand_name': org.brand_name if org else settings.COMPANY_BRAND,
        'org_logo': org_logo,
    }

    return render(request, 'accounts/emp_receipt.html', context)

@login_required(login_url='login')
def home(request):

    dest = post_login_redirect_name(request.user)
    if dest == 'login':
        logout(request)
        messages.error(
            request,
            'Xodim profili topilmadi. Foydalanuvchini «Xodimlar» orqali yarating '
            '(login + filial + lavozim).',
        )
        return redirect('login')
    return redirect(dest)

@unauthenticated_user
def loginPage(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            emp = get_active_employee(user)

            if emp is None and not user.is_superuser:
                messages.error(
                    request,
                    'Bu login uchun xodim profili yo‘q yoki faol emas. '
                    'Menejer sifatida «Xodimlar» orqali (filial + lavozim) yarating — '
                    'Superuser shart emas. Django /admin/ esa faqat superuser uchun.',
                )
                return render(request, 'accounts/login.html')

            login(request, user)
            if emp is not None:
                try:
                    emp.is_logged_in = True
                    emp.last_login_time = timezone.now()
                    emp.save(update_fields=['is_logged_in', 'last_login_time'])
                except Exception:
                    pass

            dest = post_login_redirect_name(user)
            if dest == 'login':
                logout(request)
                messages.error(
                    request,
                    'Xodim profili topilmadi. «Xodimlar» bo‘limidan qayta yarating.',
                )
                return render(request, 'accounts/login.html')
            return redirect(dest)

        # authenticate() faol emas user uchun ham None qaytaradi — alohida xabar
        candidate = User.objects.filter(username=username).first()
        if (
            candidate is not None
            and candidate.check_password(password)
            and not candidate.is_active
        ):
            messages.error(
                request,
                'Hisob o‘chirilgan (Active yoqilmagan). Kirish uchun admin '
                'foydalanuvchi sahifasida «Active» ni belgilang.',
            )
        else:
            messages.error(request, 'Login yoki parol noto‘g‘ri.')

    return render(request, 'accounts/login.html')

def logoutPage(request):
    if request.user.is_authenticated:
        try:
            emp = request.user.employee
            emp.is_logged_in = False
            emp.last_logout_time = timezone.now()
            emp.save()
        except Exception as e:
            print(f"Logout status update skipped: {e}")

    logout(request)
    return redirect('login')

@login_required(login_url='login')
@portal_cap_required('sales')
def salesDisplay(request):
    is_manager = is_app_manager(request.user)
    emp = get_active_employee(request.user)
    sales_prefetch = ('order__debts', 'order__payment_set__cashpayment')
    if is_manager:
        queryset = scope_queryset_by_branch(
            OrderItem.objects.filter(order__is_active=True),
            request,
            field='order__branch_id',
        ).select_related(
            'order', 'order__customer', 'product', 'order__employee', 'order__branch'
        ).prefetch_related(*sales_prefetch)
        debt_base = scope_queryset_by_branch(
            CustomerDebt.objects.filter(order__is_active=True), request
        )
        cash_base = scope_queryset_by_branch(
            Order.objects.filter(payment_method='CASH', is_active=True).exclude(
                order_status__in=['AwaitingApproval', 'Cancelled', 'Returned']
            ),
            request,
        )
    elif emp:
        queryset = (
            OrderItem.objects.filter(order__employee=emp, order__is_active=True)
            .select_related('order', 'order__customer', 'product', 'order__branch')
            .prefetch_related(*sales_prefetch)
        )
        debt_base = CustomerDebt.objects.filter(order__employee=emp, order__is_active=True)
        cash_base = Order.objects.filter(employee=emp, payment_method='CASH', is_active=True).exclude(
            order_status__in=['AwaitingApproval', 'Cancelled', 'Returned']
        )
    else:
        queryset = OrderItem.objects.none()
        debt_base = CustomerDebt.objects.none()
        cash_base = Order.objects.none()

    queryset = queryset.annotate(
        _await_rank=Case(
            When(order__order_status='AwaitingApproval', then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by('_await_rank', '-order__order_date')

    myFilter = salesFilter(request.GET, queryset=queryset)
    filtered_items = myFilter.qs
    debt_order_count = debt_base.exclude(status='Paid').values('order_id').distinct().count()
    cash_sales = cash_base.count()
    usd_rate = AppSettings.get_solo().usd_to_uzs
    grand_total = Decimal('0.00')
    # prefetch_related + iterator() requires chunk_size on Django 4+
    for item in filtered_items.select_related('order').iterator(chunk_size=500):
        cur = getattr(item.order, 'currency', None) or CURRENCY_UZS
        line = (item.unit_price or Decimal('0.00')) * (item.quantity or 0)
        if cur == CURRENCY_USD:
            grand_total += convert_amount(line, CURRENCY_USD, CURRENCY_UZS, usd_rate)
        else:
            grand_total += Decimal(line)
    per_page = _list_page_size(request, default=15)
    paginator = Paginator(filtered_items, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    sales_agent_stats = None
    if emp and not is_manager:
        sales_agent_stats = SalesAgent.objects.filter(employee=emp).first()
    return render(request, 'accounts/sales_display.html', {
        'myFilter': myFilter,
        'is_manager': is_manager,
        'sales': page_obj,
        'grand_total': grand_total,
        'inst': debt_order_count,
        'cash_sales': cash_sales,
        'sales_agent_stats': sales_agent_stats,
        'per_page': per_page,
    })

@login_required(login_url='login')
@portal_cap_required('btn_export')
def export_sales_csv(request):
    is_manager = request.user.is_superuser or hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'

    if is_manager:
        queryset = scope_queryset_by_branch(
            OrderItem.objects.filter(order__is_active=True),
            request,
            field='order__branch_id',
        ).select_related('order', 'order__customer', 'product', 'order__employee')
    else:
        try:
            assigned_branch = request.user.employee.branch

            queryset = OrderItem.objects.filter(order__branch=assigned_branch, order__is_active=True).select_related('order', 'product')
        except Employee.DoesNotExist:
            queryset = OrderItem.objects.none

    queryset = queryset.order_by('-order__order_date')

    myFilter = salesFilter(request.GET, queryset=queryset)
    filtered_items = myFilter.qs.select_related('order', 'order__customer', 'product', 'order__employee')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_data.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            'Sana', 'Buyurtma ID', 'Mijoz', 'Mahsulot', 'Miqdor', 'Birlik narxi', 'Jami',
            'To‘langan', 'Qarz qoldiq', 'To‘lov', 'Filial', 'Sotuvchi',
        ]
    )

    filtered_items = filtered_items.prefetch_related('order__debts', 'order__payment_set__cashpayment')
    for item in filtered_items:
        paid = item.order.get_cash_received()
        debt = item.order.get_primary_debt()
        debt_left = debt.remaining_balance if debt else ''
        writer.writerow(
            [
                item.order.order_date.strftime("%Y-%m-%d %H:%M"),
                item.order.id,
                item.order.customer.name if item.order.customer else 'Oddiy mijoz',
                item.product.product_name,
                format_qty(item.quantity),
                item.unit_price,
                item.quantity * item.unit_price,
                paid if paid is not None else '',
                debt_left,
                item.order.payment_summary_label(),
                item.order.branch.name if item.order.branch else "Mavjud emas",
                item.order.employee.name if item.order.employee else "Tizim",
            ]
        )

    return response

@login_required(login_url='login')
@portal_cap_required('btn_product_delete')
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    product.soft_delete()
    messages.success(request, f"«{product.product_name}» o‘chirildi (arxivlandi).")
    return redirect('branch_inventory')


@login_required(login_url='login')
@portal_cap_required('btn_product_edit')
def restore_product(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=False)
    product.is_active = True
    product.deleted_at = None
    product.save(update_fields=['is_active', 'deleted_at'])
    messages.success(request, f"«{product.product_name}» qayta faollashtirildi.")
    return redirect(f"{reverse('branch_inventory')}?archived=1")


@login_required(login_url='login')
@portal_cap_required('inventory')
def branchInventory(request):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    is_manager = request.user.is_superuser or hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'
    show_archived = request.GET.get('archived') == '1' and is_manager
    show_counts = request.GET.get('counts') == '1'

    if is_manager:
        count_base = scope_queryset_by_branch(BranchInventory.objects.all(), request)
        items = scope_queryset_by_branch(
            BranchInventory.objects.filter(product__is_active=(not show_archived)),
            request,
        ).select_related('branch', 'product', 'product__supplier')
        assigned_branch = _branch_scope_label(request)
    else:
        try:
            login_employee = Employee.objects.get(user=request.user)
            assigned_branch = login_employee.branch
            count_base = BranchInventory.objects.filter(branch=assigned_branch)
            items = BranchInventory.objects.filter(
                branch=assigned_branch,
                product__is_active=True,
            ).select_related('product', 'product__supplier')
        except Employee.DoesNotExist:
            count_base = BranchInventory.objects.none()
            items = BranchInventory.objects.none()
            assigned_branch = 'Tayinlanmagan'

    active_count = count_base.filter(product__is_active=True).count()
    archived_count = count_base.filter(product__is_active=False).count() if is_manager else 0
    total_count = active_count + archived_count
    in_stock_count = count_base.filter(product__is_active=True, quantity__gt=0).count()
    out_of_stock_count = count_base.filter(product__is_active=True, quantity__lte=0).count()

    myFilter = InventoryFilter(request.GET, queryset=items)
    filtered_items = myFilter.qs
    per_page = _list_page_size(request, default=15)
    paginator = Paginator(filtered_items, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/branch_inventory.html', {
        'myFilter': myFilter,
        'items': page_obj,
        'assigned_branch': assigned_branch,
        'is_manager': is_manager,
        'show_archived': show_archived,
        'show_counts': show_counts,
        'per_page': per_page,
        'active_count': active_count,
        'archived_count': archived_count,
        'total_count': total_count,
        'in_stock_count': in_stock_count,
        'out_of_stock_count': out_of_stock_count,
    })

@login_required(login_url='login')
@portal_cap_required('btn_export')
def export_branch_inventory_csv(request):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    is_manager = request.user.is_superuser or hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'

    if is_manager:
        items = scope_queryset_by_branch(
            BranchInventory.objects.filter(product__is_active=True),
            request,
        ).select_related('branch', 'product')
        assigned_branch = _branch_scope_label(request)
    else:
        try:
            login_employee = Employee.objects.get(user=request.user)
            assigned_branch = login_employee.branch

            items = BranchInventory.objects.filter(branch=assigned_branch, product__is_active=True).select_related('product', 'product__supplier')

        except Employee.DoesNotExist:
            items = BranchInventory.objects.none()
            assigned_branch = 'Tayinlanmagan'

    myFilter = InventoryFilter(request.GET, queryset=items)
    filtered_items = myFilter.qs.select_related('branch', 'product', 'product__supplier')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="branch_inventory.csv"'

    writer = csv.writer(response)
    writer.writerow(
        ['Filial', 'Yetkazib beruvchi', 'Mahsulot nomi', 'Kategoriya', 'Miqdor', 'Narx', 'Shtrix-kod', 'Holat']
    )

    for item in filtered_items:
        if item.quantity > 3:
            status = "Mavjud"
        elif item.quantity > 0 and item.quantity <= 3:
            status = "Kam qoldiq"
        else:
            status = "Tugagan"

        writer.writerow(
            [
                item.branch.name if item.branch else "Mavjud emas",
                item.product.supplier.name if item.product.supplier else "Mavjud emas",
                item.product.product_name,
                item.product.get_category_display(),
                format_qty(item.quantity),
                item.product.base_price,
                item.product.barcode,
                status
            ]
        )

    return response

def employeeProfile(request):
    sales_agent = request.user.employee
    form = EmployeeForm(instance=sales_agent)

    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=sales_agent)

        if form.is_valid():
            form.save()
            return redirect('employee_profile')

    context = {'form':form, 'sales_agent':sales_agent}
    return render(request, 'accounts/employee_profile.html', context)

@login_required(login_url='login')
@portal_cap_required('btn_export')
def employee_list_export_csv(request):
    employees = scope_queryset_by_branch(
        Employee.objects.filter(is_active=True), request
    ).order_by('-hire_date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="employee_list.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ['Xodim ismi', 'Filial', 'Lavozim', 'Aloqa', 'Holat', 'Ishga kirgan sana']
    )

    for emp in employees:
        if emp:
            status = "Faol xodim"
        else:
            status = "Faol emas"

        writer.writerow(
            [
                emp.name,
                emp.branch.name if emp.branch else "Mavjud emas",
                emp.role,
                emp.phone,
                status,
                emp.hire_date.strftime("%Y-%m-%d"),
            ]
        )

    return response

class EmployeeList(PortalCapRequiredMixin, ListView):
    portal_cap = 'employees'
    model = Employee
    template_name = 'accounts/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 10

    def get_queryset(self):
        return scope_queryset_by_branch(
            Employee.objects.filter(is_active=True),
            self.request,
        ).select_related('user', 'branch').order_by('-hire_date')

@login_required(login_url='login')
@portal_cap_required('btn_employee_block')
def employee_toggle_block(request, pk):
    if request.method != 'POST':
        return redirect('employee_list')

    employee = get_object_or_404(Employee, pk=pk, is_active=True)
    if not user_can_access_branch(request, employee.branch_id):
        raise PermissionDenied
    if employee.user_id == request.user.id:
        messages.error(request, "O‘zingizni bloklay olmaysiz.")
        return redirect('employee_list')

    user = employee.user
    if user.is_active:
        user.is_active = False
        user.save(update_fields=['is_active'])
        Employee.objects.filter(pk=employee.pk).update(is_logged_in=False)
        messages.success(request, f"{employee.name} bloklandi — tizimga kira olmaydi.")
    else:
        user.is_active = True
        user.save(update_fields=['is_active'])
        messages.success(request, f"{employee.name} blokdan chiqarildi.")

    return redirect('employee_list')

@login_required(login_url='login')
@portal_cap_required('btn_employee_delete')
def employee_delete(request, pk):
    if request.method != 'POST':
        return redirect('employee_list')

    employee = get_object_or_404(Employee, pk=pk, is_active=True)
    if not user_can_access_branch(request, employee.branch_id):
        raise PermissionDenied
    if employee.user_id == request.user.id:
        messages.error(request, "O‘zingizni o‘chira olmaysiz.")
        return redirect('employee_list')

    name = employee.name
    employee.delete()
    messages.success(request, f"{name} o‘chirildi (arxivlandi).")
    return redirect('employee_list')

def _sync_sales_agent_for_role(employee):
    """Ensure SalesAgent row exists only for Sotuvchi lavozimi."""
    if employee.role == ROLE_SALES:
        SalesAgent.objects.get_or_create(employee=employee)
    else:
        SalesAgent.objects.filter(employee=employee).delete()


class EmployeeCreate(PortalCapRequiredMixin, SuccessMessageMixin, CreateView):
    portal_cap = 'btn_employee_add'
    model = Employee
    form_class = EmployeeAdminForm
    success_url = reverse_lazy('employee_list')
    template_name = 'accounts/employee_form.html'
    success_message = "%(name)s xodimi muvaffaqiyatli yaratildi!"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        custom_username = form.cleaned_data.get('username')
        custom_password = form.cleaned_data.get('password')
        email = form.cleaned_data.get('email') or ''

        if User.objects.filter(username=custom_username).exists():
            form.add_error('username', 'Bu login allaqachon band.')
            return self.form_invalid(form)

        user = User.objects.create_user(
            username=custom_username,
            email=email,
            password=custom_password,
        )

        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=['is_staff', 'is_superuser'])

        employee = form.save(commit=False)
        employee.user = user
        employee.email = email or None
        employee.save()
        _sync_sales_agent_for_role(employee)
        assign_role_permissions(user, employee.role, replace=True)

        return redirect(self.success_url)

@login_required(login_url='login')
@portal_cap_required('btn_employee_edit')
def manageEmployee(request, pk):

    employee = get_object_or_404(Employee, pk=pk)
    if not user_can_access_branch(request, employee.branch_id):
        raise PermissionDenied
    if request.method == 'POST':
        form = EmployeeAdminForm(
            request.POST, request.FILES, instance=employee, request=request
        )

        if form.is_valid():
            old_role = employee.role
            employee = form.save(commit=False)
            user = employee.user

            # auth_user.email is NOT NULL — blank employee email must stay ''
            user.email = form.cleaned_data.get('email') or ''
            new_username = (form.cleaned_data.get('username') or '').strip()
            if new_username and new_username != user.username:
                if User.objects.filter(username=new_username).exclude(pk=user.pk).exists():
                    form.add_error('username', 'Bu login allaqachon band.')
                    return render(
                        request,
                        'accounts/employee_form.html',
                        {'employee': employee, 'form': form},
                    )
                user.username = new_username

            new_password = form.cleaned_data.get('password')
            if new_password:
                user.set_password(new_password)

            user.save()
            employee.save()
            _sync_sales_agent_for_role(employee)
            if employee.role != old_role:
                assign_role_permissions(user, employee.role, replace=True)

            return redirect('employee_list')

    else:
        form = EmployeeAdminForm(instance=employee, request=request)

    context = {'employee':employee, 'form':form}
    return render(request, 'accounts/employee_form.html', context)

@login_required(login_url='login')
@portal_cap_required('pos')
def posTerminal(request):
    employee = get_active_employee(request.user)
    if employee is None:
        if request.user.is_superuser:
            return redirect('dashboard')
        messages.error(
            request,
            'Kassa uchun faol xodim profili kerak. «Xodimlar» orqali qo‘shing (Superuser shart emas).',
        )
        logout(request)
        return redirect('login')
    branch_products = BranchInventory.objects.filter(
        branch=employee.branch,
        product__is_active=True,
    ).select_related('product')

    query = (request.GET.get('q') or '').strip()
    if query:
        branch_products = branch_products.filter(
            Q(product__product_name__icontains=query)
            | Q(product__barcode__icontains=query)
        )

    category = (request.GET.get('category') or '').strip()
    if category:
        branch_products = branch_products.filter(product__category=category)

    pos_categories = product_category_choices()

    app_settings = AppSettings.get_solo()
    tiers_qs = list(PriceTier.objects.filter(is_active=True).order_by('kind'))
    tier_map = {t.kind: float(t.discount_percent) for t in tiers_qs}
    tier_meta = {
        t.kind: {'name': t.name, 'code': t.code, 'percent': float(t.discount_percent)}
        for t in tiers_qs
    }
    context = {
        'employee': employee,
        'branch_products': branch_products,
        'pos_categories': pos_categories,
        'selected_category': category,
        'vat_enabled': app_settings.vat_enabled,
        'vat_percent': str(app_settings.vat_percent),
        'loyalty_tiers_json': json.dumps(tier_map),
        'loyalty_meta_json': json.dumps(tier_meta, ensure_ascii=False),
        'is_consultant': employee.role == ROLE_CONSULTANT,
        'can_complete_sale': can_complete_sale(request.user),
        'secret_discount_code': (app_settings.pos_secret_code or '').strip(),
        'secret_discount_percent': str(app_settings.pos_secret_discount_percent or 0),
        'secret_markup_code': (app_settings.pos_secret_markup_code or '').strip(),
        'secret_markup_percent': str(app_settings.pos_secret_markup_percent or 0),
    }

    return render(request, 'accounts/pos_terminal.html', context)

@login_required(login_url='login')
@portal_cap_required('settings')
def pos_vat_settings(request):

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST kerak'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Noto‘g‘ri JSON'}, status=400)

    settings_obj = AppSettings.get_solo()
    if 'vat_enabled' in data:
        settings_obj.vat_enabled = bool(data.get('vat_enabled'))

    if 'vat_percent' in data:
        rate = parse_decimal(data.get('vat_percent'))
        if rate < 0 or rate > 100:
            return JsonResponse({'success': False, 'message': 'QQS 0–100 oralig‘ida bo‘lishi kerak'}, status=400)
        settings_obj.vat_percent = rate

    settings_obj.save()
    return JsonResponse({
        'success': True,
        'vat_enabled': settings_obj.vat_enabled,
        'vat_percent': str(settings_obj.vat_percent),
        'message': 'QQS sozlamasi saqlandi',
    })

@login_required(login_url='login')
def scanProduct(request):
    barcode = request.GET.get('barcode')

    employee = get_object_or_404(Employee, user=request.user)

    inventory_item = BranchInventory.objects.filter(
        product__barcode__iexact=barcode,
        product__is_active=True,
        branch=employee.branch,
    ).select_related('product').first()

    if not inventory_item:
        return JsonResponse({'error': 'Mahsulot topilmadi'}, status=404)

    product = inventory_item.product
    image_url = product.image.url if product.image else ''

    payload = {
        'id': product.id,
        'name': product.product_name,
        'currency': product.currency,
        'unit': getattr(product, 'unit', None) or Product.UNIT_TA,
        'fractional': product.allows_fractional_qty(),
        'stock': format_qty(inventory_item.quantity),
        'category': product.get_category_display(),
        'image': image_url,
    }
    payload.update(_product_price_payload(product))
    return JsonResponse(payload)

@login_required(login_url='login')
def product_scan_info(request):

    barcode = (request.GET.get('barcode') or '').strip()
    if not barcode:
        return JsonResponse({'error': 'Shtrix-kod kiritilmagan', 'found': False}, status=400)

    product = Product.objects.filter(barcode__iexact=barcode, is_active=True).first()
    if not product:
        return JsonResponse({
            'found': False,
            'barcode': barcode,
            'message': 'Mahsulot katalogda yo‘q — Ombor orqali yangi kiriting',
        })

    stock = None
    branch_name = ''
    in_branch = False
    employee = getattr(request.user, 'employee', None)
    if employee and employee.branch_id:
        inv = BranchInventory.objects.filter(branch=employee.branch, product=product).first()
        stock = inv.quantity if inv else 0
        branch_name = employee.branch.name
        in_branch = inv is not None

    image_url = product.image.url if product.image else ''
    payload = {
        'found': True,
        'barcode': product.barcode or barcode,
        'id': product.id,
        'name': product.product_name,
        'currency': product.currency,
        'unit': getattr(product, 'unit', None) or Product.UNIT_TA,
        'fractional': product.allows_fractional_qty(),
        'stock': format_qty(stock) if stock is not None else None,
        'category': product.get_category_display(),
        'image': image_url,
        'branch_name': branch_name,
        'in_branch': in_branch,
    }
    payload.update(_product_price_payload(product))
    return JsonResponse(payload)

def _is_inventory_manager(user):
    return user.is_superuser or (
        hasattr(user, 'employee') and user.employee.role == 'Manager'
    )


def _product_cost_in_currency(product, to_currency, usd_rate=None):
    """Tannarxni kerakli valyutaga o‘girish (hisobot / buyurtma bandi uchun)."""
    from_cur = getattr(product, 'cost_currency', None) or product.currency or CURRENCY_UZS
    to_cur = (to_currency or CURRENCY_UZS).upper()
    if usd_rate is None:
        usd_rate = AppSettings.get_solo().usd_to_uzs
    return convert_amount(product.cost_price or 0, from_cur, to_cur, usd_rate)

def _resolve_intake_branch(request, branch_id=None):
    is_manager = _is_inventory_manager(request.user)
    employee_branch = None
    if hasattr(request.user, 'employee') and request.user.employee.branch_id:
        employee_branch = request.user.employee.branch

    if not is_manager:
        return employee_branch

    allowed = _allowed_branches_qs(request)
    if branch_id:
        return get_object_or_404(allowed, pk=branch_id)

    if employee_branch and allowed.filter(pk=employee_branch.pk).exists():
        return employee_branch

    return allowed.first()

def _ensure_product_categories():

    defaults = [label for _, label in Product.CATEGORIES]
    for name in defaults:
        ProductCategory.objects.get_or_create(name=name)

    key_to_label = dict(Product.CATEGORIES)
    for key, label in key_to_label.items():
        Product.objects.filter(category=key).update(category=label)

    for name in (
        Product.objects.exclude(category='')
        .values_list('category', flat=True)
        .distinct()
    ):
        if name:
            ProductCategory.objects.get_or_create(name=name)

def _product_payload(product, branch):
    inventory_item = BranchInventory.objects.filter(branch=branch, product=product).first()
    stock = inventory_item.quantity if inventory_item else 0
    min_stock = product.min_stock_level or 0
    image_url = product.image.url if product.image else ''
    return {
        'id': product.id,
        'name': product.product_name,
        'barcode': product.barcode,
        'price': str(product.base_price),
        'cost_price': str(product.cost_price),
        'cost_currency': getattr(product, 'cost_currency', None) or product.currency,
        'currency': product.currency,
        'unit': getattr(product, 'unit', None) or Product.UNIT_TA,
        'unit_label': product.unit_label() if hasattr(product, 'unit_label') else 'ta',
        'fractional': product.allows_fractional_qty() if hasattr(product, 'allows_fractional_qty') else False,
        'category': product.get_category_display(),
        'supplier_id': product.supplier_id,
        'supplier': product.supplier.name if product.supplier else '',
        'image': image_url,
        'stock': format_qty(stock),
        'min_stock_level': format_qty(min_stock),
        'warranty_days': product.warranty_days,
        'replacement_days': product.replacement_days,
        'service_warranty_days': product.service_warranty_days,
        'is_low_stock': stock <= min_stock,
        'branch_id': branch.id,
        'branch_name': branch.name,
        'in_branch': inventory_item is not None,
        'exists': True,
    }

@login_required(login_url='login')
@portal_cap_required('inventory_intake')
def inventory_intake(request):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    is_manager = _is_inventory_manager(request.user)
    branch = _resolve_intake_branch(request)
    branches = _allowed_branches_qs(request) if is_manager else Branch.objects.none()

    _ensure_product_categories()
    settings_obj = AppSettings.get_solo()
    categories = list(
        ProductCategory.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)
    )
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')

    context = {
        'is_manager': is_manager,
        'branch': branch,
        'branches': branches,
        'categories': categories,
        'suppliers': suppliers,
        'usd_rate': str(settings_obj.usd_to_uzs),
    }
    return render(request, 'accounts/inventory_intake.html', context)

@login_required(login_url='login')
def inventory_lookup(request):
    if is_consultant(request.user):
        return JsonResponse({'error': 'Ruxsat yo‘q'}, status=403)
    barcode = (request.GET.get('barcode') or '').strip()
    branch_id = request.GET.get('branch_id')

    if not barcode:
        return JsonResponse({'error': 'Shtrix-kod kiritilmagan'}, status=400)

    branch = _resolve_intake_branch(request, branch_id)
    if not branch:
        return JsonResponse({'error': 'Filial topilmadi'}, status=400)

    product = Product.objects.filter(barcode__iexact=barcode, is_active=True).select_related('supplier').first()
    if not product:
        return JsonResponse({
            'exists': False,
            'barcode': barcode,
            'branch_id': branch.id,
            'branch_name': branch.name,
            'message': 'Katalogda yo‘q — yangi mahsulot sifatida kiriting',
        }, status=404)

    return JsonResponse(_product_payload(product, branch))

@login_required(login_url='login')
@transaction.atomic
def inventory_stock_in(request):
    if is_consultant(request.user):
        return JsonResponse({'error': 'Ruxsat yo‘q'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Noto‘g‘ri so‘rov'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Noto‘g‘ri JSON'}, status=400)

    barcode = (data.get('barcode') or '').strip()
    note = (data.get('note') or '').strip()[:200]
    undo = bool(data.get('undo'))
    qty = parse_decimal(data.get('qty', 1))

    branch_id = data.get('branch_id')

    if not barcode:
        return JsonResponse({'error': 'Shtrix-kod kiritilmagan'}, status=400)
    if qty <= 0:
        return JsonResponse({'error': 'Miqdor 0 dan katta bo‘lishi kerak'}, status=400)
    qty = qty.quantize(Decimal('0.001'))

    branch = _resolve_intake_branch(request, branch_id)
    if not branch:
        return JsonResponse({'error': 'Filial topilmadi'}, status=400)

    product = Product.objects.filter(barcode__iexact=barcode, is_active=True).select_related('supplier').first()
    if not product:
        return JsonResponse({'error': 'Mahsulot katalogda topilmadi'}, status=404)

    inventory_item, created = BranchInventory.objects.select_for_update().get_or_create(
        branch=branch,
        product=product,
        defaults={'quantity': 0},
    )

    current = inventory_item.quantity or 0
    if undo:
        if qty > current:
            return JsonResponse({
                'error': f"Bekor qilib bo‘lmaydi: omborda faqat {current} dona bor",
            }, status=400)
        inventory_item.quantity = current - qty
        action_qty = -qty
        message = f"{product.product_name}: {qty} dona bekor qilindi"
    else:
        inventory_item.quantity = current + qty
        action_qty = qty
        message = f"{product.product_name}: +{qty} qo‘shildi"

    inventory_item.save(update_fields=['quantity'])

    return JsonResponse({
        'success': True,
        'message': message,
        'id': product.id,
        'name': product.product_name,
        'barcode': product.barcode,
        'qty_added': format_qty(action_qty),
        'stock': format_qty(inventory_item.quantity),
        'min_stock_level': format_qty(product.min_stock_level or 0),
        'is_low_stock': inventory_item.quantity <= (product.min_stock_level or 0),
        'supplier': product.supplier.name if product.supplier else '',
        'price': str(product.base_price),
        'cost_price': str(product.cost_price),
        'cost_currency': getattr(product, 'cost_currency', None) or product.currency,
        'currency': product.currency,
        'branch_id': branch.id,
        'branch_name': branch.name,
        'created': created,
        'undo': undo,
        'note': note,
        'time': timezone.localtime().strftime('%H:%M:%S'),
    })

@login_required(login_url='login')
@transaction.atomic
def inventory_product_save(request):
    if is_consultant(request.user):
        return JsonResponse({'error': 'Ruxsat yo‘q'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Noto‘g‘ri so‘rov'}, status=405)

    data = request.POST
    barcode = (data.get('barcode') or '').strip()
    product_name = (data.get('product_name') or '').strip()
    category = (data.get('category') or '').strip()
    note = (data.get('note') or '').strip()[:200]
    store_currency = (data.get('store_currency') or CURRENCY_UZS).upper()
    entry_currency = (data.get('entry_currency') or store_currency).upper()

    if store_currency not in (CURRENCY_UZS, CURRENCY_USD):
        store_currency = CURRENCY_UZS
    if entry_currency not in (CURRENCY_UZS, CURRENCY_USD):
        entry_currency = store_currency

    unit = (data.get('unit') or Product.UNIT_TA).strip().lower()
    valid_units = {c[0] for c in Product.UNIT_CHOICES}
    if unit not in valid_units:
        unit = Product.UNIT_TA

    qty = parse_decimal(data.get('qty', 1))
    min_stock = parse_decimal(data.get('min_stock_level', 3))
    if min_stock < 0:
        min_stock = Decimal('0')

    def _pos_int(key, default):
        try:
            return max(0, int(data.get(key, default)))
        except (TypeError, ValueError):
            return default

    warranty_days = _pos_int('warranty_days', 365)
    replacement_days = _pos_int('replacement_days', 7)
    service_warranty_days = _pos_int('service_warranty_days', 90)

    sale_active = data.get('sale_active') in ('1', 'true', 'True', 'on', 'yes')
    try:
        sale_discount_percent = parse_decimal(data.get('sale_discount_percent') or 0)
    except Exception:
        sale_discount_percent = Decimal('0.00')
    if sale_discount_percent < 0:
        sale_discount_percent = Decimal('0.00')
    if sale_discount_percent > 100:
        sale_discount_percent = Decimal('100.00')
    raw_sale_start = (data.get('sale_starts_at') or '').strip()
    raw_sale_end = (data.get('sale_ends_at') or '').strip()
    sale_starts_at = parse_date(raw_sale_start) if raw_sale_start else None
    sale_ends_at = parse_date(raw_sale_end) if raw_sale_end else None
    if sale_starts_at and sale_ends_at and sale_ends_at < sale_starts_at:
        return JsonResponse({'error': 'Skidka tugash sanasi noto‘g‘ri'}, status=400)
    if sale_active and sale_discount_percent <= 0:
        return JsonResponse({'error': 'Skidka foizini kiriting'}, status=400)

    if not barcode:
        return JsonResponse({'error': 'Shtrix-kod kiritilmagan'}, status=400)
    if not product_name:
        return JsonResponse({'error': 'Mahsulot nomi majburiy'}, status=400)
    if not category:
        return JsonResponse({'error': 'Kategoriya tanlang yoki yarating'}, status=400)
    if qty <= 0:
        return JsonResponse({'error': 'Miqdor 0 dan katta bo‘lishi kerak'}, status=400)
    if unit not in Product.FRACTIONAL_UNITS and qty != qty.to_integral_value():
        return JsonResponse({'error': 'Bu birlik uchun butun son kerak'}, status=400)
    qty = qty.quantize(Decimal('0.001'))

    branch = _resolve_intake_branch(request, data.get('branch_id'))
    if not branch:
        return JsonResponse({'error': 'Filial topilmadi'}, status=400)

    supplier_id = data.get('supplier_id')
    supplier = None
    if supplier_id:
        supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first()
    if not supplier:
        supplier = Supplier.objects.filter(is_active=True).order_by('name').first()
    if not supplier:
        return JsonResponse({
            'error': 'Yetkazib beruvchi topilmadi. Avval admin panelda yetkazib beruvchi yarating.',
        }, status=400)

    settings_obj = AppSettings.get_solo()
    rate = parse_decimal(data.get('usd_rate') or settings_obj.usd_to_uzs)
    if rate <= 0:
        return JsonResponse({'error': 'Valyuta kursi noto‘g‘ri'}, status=400)

    if data.get('save_rate') in ('1', 'true', 'True', 'on'):
        settings_obj.usd_to_uzs = rate
        settings_obj.save(update_fields=['usd_to_uzs', 'updated_at'])

    try:
        cost_entered = parse_decimal(data.get('cost_price'))
        sell_entered = parse_decimal(data.get('base_price'))
        # Tannarx kirim valyutasida saqlanadi; sotish narxi — saqlash valyutasida
        cost_price = cost_entered
        cost_currency = entry_currency
        base_price = convert_amount(sell_entered, entry_currency, store_currency, rate)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if cost_price < 0 or base_price < 0:
        return JsonResponse({'error': 'Narxlar manfiy bo‘lishi mumkin emas'}, status=400)

    ProductCategory.objects.get_or_create(name=category, defaults={'is_active': True})

    product = Product.objects.filter(barcode__iexact=barcode).select_related('supplier').first()
    created_product = False
    if product:
        if not product.is_active:
            product.is_active = True
            product.deleted_at = None
        product.product_name = product_name
        product.category = category
        product.supplier = supplier
        product.unit = unit
        product.currency = store_currency
        product.cost_currency = cost_currency
        product.cost_price = cost_price
        product.base_price = base_price
        product.min_stock_level = min_stock
        product.warranty_days = warranty_days
        product.replacement_days = replacement_days
        product.service_warranty_days = service_warranty_days
        if 'sale_active' in data or 'sale_discount_percent' in data:
            product.sale_active = sale_active
            product.sale_discount_percent = sale_discount_percent
            product.sale_starts_at = sale_starts_at
            product.sale_ends_at = sale_ends_at
        if request.FILES.get('image'):
            product.image = request.FILES['image']
        product.save()
    else:
        created_product = True
        product = Product(
            barcode=barcode,
            product_name=product_name,
            category=category,
            supplier=supplier,
            unit=unit,
            currency=store_currency,
            cost_currency=cost_currency,
            cost_price=cost_price,
            base_price=base_price,
            min_stock_level=min_stock,
            warranty_days=warranty_days,
            replacement_days=replacement_days,
            service_warranty_days=service_warranty_days,
            sale_active=sale_active,
            sale_discount_percent=sale_discount_percent,
            sale_starts_at=sale_starts_at,
            sale_ends_at=sale_ends_at,
            is_active=True,
        )
        if request.FILES.get('image'):
            product.image = request.FILES['image']
        product.save()

    inventory_item, inv_created = BranchInventory.objects.select_for_update().get_or_create(
        branch=branch,
        product=product,
        defaults={'quantity': 0},
    )
    inventory_item.quantity = (inventory_item.quantity or 0) + qty
    inventory_item.save(update_fields=['quantity'])

    cost_alt = convert_amount(
        cost_price,
        cost_currency,
        CURRENCY_USD if cost_currency == CURRENCY_UZS else CURRENCY_UZS,
        rate,
    )
    sell_alt = convert_amount(
        base_price,
        store_currency,
        CURRENCY_USD if store_currency == CURRENCY_UZS else CURRENCY_UZS,
        rate,
    )

    resp = {
        'success': True,
        'message': (
            f"{'Yangi mahsulot yaratildi va' if created_product else 'Mahsulot yangilandi va'}"
            f" +{qty} omborga qo‘shildi"
        ),
        'id': product.id,
        'name': product.product_name,
        'barcode': product.barcode,
        'qty_added': format_qty(qty),
        'stock': format_qty(inventory_item.quantity),
        'min_stock_level': format_qty(product.min_stock_level or 0),
        'is_low_stock': inventory_item.quantity <= (product.min_stock_level or 0),
        'supplier': product.supplier.name if product.supplier else '',
        'cost_price': str(product.cost_price),
        'cost_currency': product.cost_currency,
        'currency': product.currency,
        'unit': product.unit,
        'unit_label': product.unit_label(),
        'category': product.get_category_display(),
        'image': product.image.url if product.image else '',
        'branch_id': branch.id,
        'branch_name': branch.name,
        'created': created_product or inv_created,
        'product_created': created_product,
        'note': note,
        'usd_rate': str(rate),
        'converted_hint': (
            f"Saqlangan: tannarx {format_money(cost_price, cost_currency)}, "
            f"sotish {format_money(base_price, store_currency)} "
            f"(≈ {format_money(cost_alt, CURRENCY_USD if cost_currency == CURRENCY_UZS else CURRENCY_UZS)} / "
            f"{format_money(sell_alt, CURRENCY_USD if store_currency == CURRENCY_UZS else CURRENCY_UZS)})"
        ),
        'time': timezone.localtime().strftime('%H:%M:%S'),
        'undo': False,
    }
    resp.update(_product_price_payload(product))
    return JsonResponse(resp)

@login_required(login_url='login')
def inventory_add_category(request):
    if is_consultant(request.user):
        return JsonResponse({'error': 'Ruxsat yo‘q'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Noto‘g‘ri so‘rov'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Kategoriya nomi bo‘sh'}, status=400)
    if len(name) > 100:
        return JsonResponse({'error': 'Kategoriya nomi juda uzun'}, status=400)

    cat, created = ProductCategory.objects.get_or_create(
        name=name,
        defaults={'is_active': True},
    )
    if not cat.is_active:
        cat.is_active = True
        cat.save(update_fields=['is_active'])

    categories = list(
        ProductCategory.objects.filter(is_active=True).order_by('name').values_list('name', flat=True)
    )
    return JsonResponse({
        'success': True,
        'created': created,
        'name': cat.name,
        'categories': categories,
        'message': 'Kategoriya qo‘shildi' if created else 'Kategoriya allaqachon mavjud',
    })

@login_required(login_url='login')
def inventory_save_rate(request):
    if is_consultant(request.user):
        return JsonResponse({'error': 'Ruxsat yo‘q'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Noto‘g‘ri so‘rov'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    rate = parse_decimal(data.get('usd_rate'))
    if rate <= 0:
        return JsonResponse({'error': 'Kurs 0 dan katta bo‘lishi kerak'}, status=400)

    settings_obj = AppSettings.get_solo()
    settings_obj.usd_to_uzs = rate
    settings_obj.save(update_fields=['usd_to_uzs', 'updated_at'])
    return JsonResponse({
        'success': True,
        'usd_rate': str(settings_obj.usd_to_uzs),
        'message': f'Kurs saqlandi: 1 USD = {settings_obj.usd_to_uzs} so‘m',
    })

@transaction.atomic
def checkout_cash(request):
        if request.method == 'POST':
            try:
                data = json.loads(request.body)

                cart = data.get('cart', [])
                cash_raw = data.get('cashReceived')
                customer_data = data.get('customerData', {}) or {}

                if not cart:
                    return JsonResponse({'success': False, 'message': 'Savat bo‘sh'}, status=400)

                try:
                    employee = request.user.employee
                    branch = employee.branch
                except Exception:
                    return JsonResponse({'success': False, 'message': 'Foydalanuvchi vakolatli xodim emas'}, status=403)

                if not can_complete_sale(request.user):
                    return JsonResponse({
                        'success': False,
                        'message': 'Maslahatchi sotuvni yakunlay olmaydi. «Tasdiqlashga yuborish»dan foydalaning.',
                        'use_quote': True,
                    }, status=403)

                name = (customer_data.get('name') or '').strip()
                phone = (customer_data.get('phone') or '').strip()
                email = (customer_data.get('email') or '').strip()
                address = (customer_data.get('address') or '').strip()
                cust_type = (customer_data.get('customer_type') or Customer.TYPE_REGULAR).strip()
                if not PriceTier.objects.filter(kind=cust_type, is_active=True).exists():
                    cust_type = Customer.TYPE_REGULAR
                partner_id = customer_data.get('partner_id')

                customer = None
                if phone:
                    customer, _created = Customer.objects.get_or_create(
                        phone=phone,
                        defaults={
                            'name': name or 'Oddiy mijoz',
                            'email': email,
                            'address': address,
                            'customer_type': cust_type,
                        }
                    )
                    updated = False
                    if name and customer.name != name:
                        customer.name = name
                        updated = True
                    if email and customer.email != email:
                        customer.email = email
                        updated = True
                    if address and customer.address != address:
                        customer.address = address
                        updated = True

                    if _created or customer.customer_type == Customer.TYPE_REGULAR:
                        if cust_type != customer.customer_type:
                            customer.customer_type = cust_type
                            customer.price_tier = (
                                PriceTier.objects.filter(kind=cust_type, is_active=True).first()
                                or PriceTier.objects.filter(code=cust_type, is_active=True).first()
                            )
                            updated = True
                    if updated:
                        customer.save()

                partner = None
                if partner_id:
                    partner = Customer.objects.filter(
                        pk=partner_id, is_active=True, customer_type=Customer.TYPE_PARTNER
                    ).first()

                adjust = _checkout_price_adjust(customer, data.get('secretCode'))
                priced = _price_lines_from_cart(cart, adjust)
                priced_lines = priced['priced_lines']
                list_total = priced['list_total']
                net_total = priced['net_total']
                discount_percent = priced['discount_percent']
                discount_amount = priced['discount_amount']
                total_amount = net_total

                if cash_raw is None or str(cash_raw).strip() == '':
                    cash_received = total_amount
                else:
                    cash_received = parse_decimal(cash_raw)
                if cash_received < 0:
                    return JsonResponse({'success': False, 'message': 'Naqd summa manfiy bo‘lishi mumkin emas'}, status=400)

                debt_amount = max(Decimal('0.00'), total_amount - cash_received)
                if debt_amount > 0 and (not name or not phone):
                    return JsonResponse({
                        'success': False,
                        'message': 'Qarz uchun mijoz ismi va telefon majburiy',
                    }, status=400)

                order_currency = (data.get('currency') or 'UZS').upper()
                if order_currency not in ('UZS', 'USD'):
                    order_currency = 'UZS'

                payment_method = 'CASH'
                # Naqd sotuv yakunlangan — Pending emas (Pending = hali ochiq / eski quirk)
                order_status = 'Completed'
                change_given = max(Decimal('0.00'), cash_received - total_amount)

                order = Order.objects.create(
                    employee=employee,
                    branch=branch,
                    customer=customer,
                    partner=partner,
                    total_amount=total_amount,
                    list_total=list_total,
                    discount_percent=discount_percent,
                    discount_amount=discount_amount,
                    currency=order_currency,
                    payment_method=payment_method,
                    order_status=order_status,
                )

                usd_rate = AppSettings.get_solo().usd_to_uzs
                for product, qty, list_price, unit_price, price_adjusted in priced_lines:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        list_unit_price=list_price,
                        unit_price=unit_price,
                        discount_percent=discount_percent,
                        price_adjusted=price_adjusted,
                        cost_price=_product_cost_in_currency(product, order_currency, usd_rate),
                        warranty_days=product.warranty_days,
                        replacement_days=product.replacement_days,
                        service_warranty_days=product.service_warranty_days,
                    )

                    try:
                        inventory = BranchInventory.objects.get(branch=branch, product=product)
                    except BranchInventory.DoesNotExist:
                        raise ValueError(f"{product.product_name} mahsuloti ushbu filialda ro‘yxatdan o‘tmagan.")

                    if inventory.quantity < qty:
                        raise ValueError(
                            f"{product.product_name}: omborda yetarli emas (qoldiq {inventory.quantity})"
                        )

                    inventory.quantity -= qty
                    inventory.save()

                payment = Payment.objects.create(
                    order=order,
                    amount_paid=cash_received,
                    payment_type=payment_method,
                    date_paid=order.order_date
                )

                CashPayment.objects.create(
                    payment=payment,
                    cash_received=cash_received,
                    change_given=change_given,
                )

                debt = None
                if debt_amount > 0 and customer:
                    debt = CustomerDebt.objects.create(
                        customer=customer,
                        order=order,
                        branch=branch,
                        created_by=employee,
                        currency=order_currency,
                        original_amount=debt_amount,
                        paid_amount=Decimal('0.00'),
                        remaining_balance=debt_amount,
                        status='Open',
                        note=f'Buyurtma #{order.id} bo‘yicha qarz',
                    )

                app_settings = AppSettings.get_solo()
                vat_enabled = bool(app_settings.vat_enabled)
                vat_percent = app_settings.vat_percent or Decimal('0')
                if vat_percent < 0:
                    vat_percent = Decimal('0')
                if vat_percent > 100:
                    vat_percent = Decimal('100')

                cart_subtotal = total_amount
                if vat_enabled and vat_percent > 0:
                    vat_amount = (cart_subtotal * vat_percent / Decimal('100')).quantize(Decimal('0.01'))
                else:
                    vat_amount = Decimal('0.00')

                invoice = Invoice.objects.create(
                    order=order,
                    or_number=f"OR-{uuid.uuid4().hex[:8].upper()}",
                    vat_amount=vat_amount,
                    grand_total=order.total_amount,
                    issued_by=order.employee,
                    invoice_date=order.order_date
                )

                try:
                    agent_profile = order.employee.salesagent
                    agent_profile.total_sales += order.total_amount
                    commission_for_this_order = order.total_amount * agent_profile.commission_rate
                    agent_profile.total_commission_earned += commission_for_this_order
                    agent_profile.save()
                except Exception:
                    pass

                if order.customer and order.customer.email:
                    try:
                        email_subtotal = (order.total_amount - vat_amount).quantize(Decimal('0.01'))
                        if vat_amount > 0 and email_subtotal > 0:
                            email_vat_label = f"QQS {(vat_amount / email_subtotal * Decimal('100')).quantize(Decimal('0.01'))}%"
                        else:
                            email_vat_label = 'QQS'
                        org = order.branch.organization or Organization.get_default()
                        context = {
                            'order': order,
                            'invoice': invoice,
                            'subtotal': email_subtotal,
                            'vat_amount': vat_amount,
                            'vat_label': email_vat_label,
                            'cash_received': cash_received,
                            'change_given': change_given,
                            'debt': debt,
                            'debt_remaining': debt.remaining_balance if debt else Decimal('0.00'),
                            'debt_original': debt.original_amount if debt else Decimal('0.00'),
                            'has_debt': bool(debt and debt.remaining_balance > 0),
                            'brand_name': org.brand_name,
                            'organization_name': order.branch.organization_name,
                        }

                        html_content = render_to_string('emails/cash_receipt.html', context)

                        email_msg = EmailMessage(
                            subject=f"Naqd chek - {invoice.or_number}",
                            body=html_content,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            to=[order.customer.email],
                        )
                        email_msg.content_subtype = "html"
                        email_msg.send(fail_silently=False)
                    except Exception as email_err:
                        print(f"❌ HTML Email Error: {email_err}")

                payload = {
                    'success': True,
                    'order_id': order.id,
                }
                if debt:
                    payload['debt_id'] = debt.id
                    payload['debt_amount'] = str(debt.remaining_balance)
                    payload['message'] = f'Qarz yozildi: {debt.remaining_balance} {debt.currency}'
                return JsonResponse(payload)

            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)

        return JsonResponse({'success': False, 'message': 'Noto‘g‘ri so‘rov'}, status=405)

@login_required(login_url='login')
@transaction.atomic
def checkout_quote(request):

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Noto‘g‘ri so‘rov'}, status=405)
    try:
        data = json.loads(request.body)
        cart = data.get('cart', [])
        customer_data = data.get('customerData', {}) or {}
        if not cart:
            return JsonResponse({'success': False, 'message': 'Savat bo‘sh'}, status=400)
        emp = get_active_employee(request.user)
        if emp is None or emp.role != ROLE_CONSULTANT:
            return JsonResponse({'success': False, 'message': 'Faqat maslahatchi buyurtma yuboradi.'}, status=403)
        branch = emp.branch
        name = (customer_data.get('name') or '').strip()
        phone = (customer_data.get('phone') or '').strip()
        email = (customer_data.get('email') or '').strip()
        address = (customer_data.get('address') or '').strip()
        cust_type = (customer_data.get('customer_type') or Customer.TYPE_REGULAR).strip()
        if not PriceTier.objects.filter(kind=cust_type, is_active=True).exists():
            cust_type = Customer.TYPE_REGULAR
        partner_id = customer_data.get('partner_id')

        customer = None
        if phone:
            customer, created = Customer.objects.get_or_create(
                phone=phone,
                defaults={'name': name or 'Oddiy mijoz', 'email': email, 'address': address, 'customer_type': cust_type},
            )
            if name and customer.name != name:
                customer.name = name
            if email:
                customer.email = email
            if address:
                customer.address = address
            if created or customer.customer_type == Customer.TYPE_REGULAR:
                customer.customer_type = cust_type
                customer.price_tier = (
                    PriceTier.objects.filter(kind=cust_type, is_active=True).first()
                    or PriceTier.objects.filter(code=cust_type, is_active=True).first()
                )
            customer.save()
        elif name:
            customer = Customer.objects.create(name=name, email=email, address=address, customer_type=cust_type)

        partner = None
        if partner_id:
            partner = Customer.objects.filter(pk=partner_id, is_active=True, customer_type=Customer.TYPE_PARTNER).first()

        adjust = _checkout_price_adjust(customer, data.get('secretCode'))
        priced = _price_lines_from_cart(cart, adjust)
        priced_lines = priced['priced_lines']
        list_total = priced['list_total']
        net_total = priced['net_total']
        discount_percent = priced['discount_percent']
        discount_amount = priced['discount_amount']

        for product, qty, _lp, _up, _adj in priced_lines:
            inv = BranchInventory.objects.filter(branch=branch, product=product).first()
            if not inv:
                raise ValueError(f"{product.product_name} ushbu filialda yo‘q.")
            if inv.quantity < qty:
                raise ValueError(f"{product.product_name}: omborda yetarli emas (qoldiq {inv.quantity})")

        order_currency = (data.get('currency') or 'UZS').upper()
        if order_currency not in ('UZS', 'USD'):
            order_currency = 'UZS'

        order = Order.objects.create(
            employee=emp,
            branch=branch,
            customer=customer,
            partner=partner,
            total_amount=net_total,
            list_total=list_total,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            currency=order_currency,
            payment_method='CASH',
            order_status='AwaitingApproval',
        )
        usd_rate = AppSettings.get_solo().usd_to_uzs
        for product, qty, list_price, unit_price, price_adjusted in priced_lines:
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=qty,
                list_unit_price=list_price,
                unit_price=unit_price,
                discount_percent=discount_percent,
                price_adjusted=price_adjusted,
                cost_price=_product_cost_in_currency(product, order_currency, usd_rate),
                warranty_days=product.warranty_days,
                replacement_days=product.replacement_days,
                service_warranty_days=product.service_warranty_days,
            )

        app_settings = AppSettings.get_solo()
        vat_percent = app_settings.vat_percent or Decimal('0')
        if app_settings.vat_enabled and vat_percent > 0:
            vat_amount = (net_total * vat_percent / Decimal('100')).quantize(Decimal('0.01'))
        else:
            vat_amount = Decimal('0.00')
        Invoice.objects.create(
            order=order,
            or_number=f"QT-{uuid.uuid4().hex[:8].upper()}",
            vat_amount=vat_amount,
            grand_total=order.total_amount,
            issued_by=order.employee,
            invoice_date=order.order_date,
        )
        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'awaiting_approval': True,
            'message': 'Buyurtma menejerga yuborildi — tasdiqlash kutilmoqda.',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


def _release_reservation_stock(reservation):
    if not reservation.stock_held or reservation.status != 'Active':
        return
    for item in reservation.items.select_related('product'):
        inv = BranchInventory.objects.filter(
            branch=reservation.branch, product=item.product
        ).first()
        if inv:
            inv.quantity = int(inv.quantity or 0) + int(item.quantity or 0)
            inv.save(update_fields=['quantity'])
    reservation.stock_held = False


@login_required(login_url='login')
@transaction.atomic
def checkout_reserve(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST kerak'}, status=405)
    try:
        data = json.loads(request.body or '{}')
        cart = data.get('cart') or []
        customer_name = (data.get('customerName') or data.get('customer_name') or '').strip()
        phone = (data.get('phone') or '').strip()
        if not cart:
            return JsonResponse({'success': False, 'message': 'Savat bo‘sh'}, status=400)
        if not customer_name:
            return JsonResponse({'success': False, 'message': 'Mijoz nomi majburiy'}, status=400)

        employee = get_active_employee(request.user)
        if employee is None:
            return JsonResponse({'success': False, 'message': 'Faol xodim profili kerak'}, status=403)
        branch = employee.branch

        currency = (data.get('currency') or 'UZS').upper()
        if currency not in ('UZS', 'USD'):
            currency = 'UZS'

        customer = None
        if phone:
            customer = Customer.objects.filter(phone__iexact=phone, is_active=True).first()
            if customer is None:
                customer = Customer.objects.create(
                    name=customer_name,
                    phone=phone,
                    customer_type=Customer.TYPE_REGULAR,
                    is_active=True,
                )
            elif customer_name and customer.name != customer_name:
                customer.name = customer_name
                customer.save(update_fields=['name'])

        lines = []
        total = Decimal('0.00')
        unit_count = 0
        for raw in cart:
            product_id = raw.get('id')
            qty = int(raw.get('qty') or 0)
            if not product_id or qty <= 0:
                continue
            product = Product.objects.filter(pk=product_id, is_active=True).first()
            if product is None:
                raise ValueError(f'Mahsulot topilmadi (id={product_id})')
            try:
                inventory = BranchInventory.objects.select_for_update().get(
                    branch=branch, product=product
                )
            except BranchInventory.DoesNotExist:
                raise ValueError(f'{product.product_name} ushbu filialda yo‘q')
            if inventory.quantity < qty:
                raise ValueError(
                    f'{product.product_name}: omborda yetarli emas (qoldiq {inventory.quantity})'
                )
            unit_price = parse_decimal(raw.get('price'))
            if unit_price <= 0:
                unit_price = product.base_price or Decimal('0.00')
            line_total = (unit_price * qty).quantize(Decimal('0.01'))
            lines.append((product, qty, unit_price, line_total, inventory))
            total += line_total
            unit_count += qty

        if not lines:
            return JsonResponse({'success': False, 'message': 'Bronlash uchun mahsulot yo‘q'}, status=400)

        reservation = ProductReservation.objects.create(
            branch=branch,
            employee=employee,
            customer=customer,
            customer_name=customer_name,
            phone=phone,
            currency=currency,
            total_amount=total,
            item_count=len(lines),
            unit_count=unit_count,
            status='Active',
            stock_held=True,
        )
        for product, qty, unit_price, line_total, inventory in lines:
            ProductReservationItem.objects.create(
                reservation=reservation,
                product=product,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
            inventory.quantity -= qty
            inventory.save(update_fields=['quantity'])

        return JsonResponse({
            'success': True,
            'reservation_id': reservation.id,
            'message': f'Bronlandi: {customer_name} — {unit_count} dona',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required(login_url='login')
def reservations_active_api(request):
    emp = get_active_employee(request.user)
    qs = ProductReservation.objects.filter(status='Active').prefetch_related('items__product')
    if is_app_manager(request.user):
        qs = scope_queryset_by_branch(qs, request)
    elif emp:
        qs = qs.filter(branch=emp.branch)
    else:
        qs = qs.none()
    rows = []
    for r in qs.order_by('-created_at')[:30]:
        rows.append({
            'id': r.id,
            'customer_name': r.customer_name,
            'phone': r.phone or '',
            'total_amount': float(r.total_amount or 0),
            'currency': r.currency,
            'item_count': r.item_count,
            'unit_count': r.unit_count,
            'created_at': r.created_at.isoformat() if r.created_at else '',
            'items': [
                {
                    'id': it.product_id,
                    'name': it.product.product_name if it.product_id else '',
                    'qty': it.quantity,
                    'price': float(it.unit_price or 0),
                    'currency': r.currency,
                    'img': it.product.image.url if it.product_id and it.product.image else '',
                }
                for it in r.items.all()
            ],
        })
    return JsonResponse({'reservations': rows})


@login_required(login_url='login')
@transaction.atomic
def reservation_to_cart(request, pk):
    """Release held stock and return cart lines so POS can open this bron."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST kerak'}, status=405)

    reservation = get_object_or_404(
        ProductReservation.objects.select_related('branch').prefetch_related('items__product'),
        pk=pk,
    )
    emp = get_active_employee(request.user)
    if not is_app_manager(request.user):
        if emp is None or reservation.branch_id != emp.branch_id:
            raise PermissionDenied
    if reservation.status != 'Active':
        return JsonResponse({'success': False, 'message': 'Bu bron allaqachon yopilgan.'}, status=400)

    cart_items = []
    for it in reservation.items.all():
        product = it.product
        # After release, available stock will include this qty again
        held_qty = int(it.quantity or 1)
        inv = BranchInventory.objects.filter(
            branch=reservation.branch, product=product
        ).first()
        avail = int(inv.quantity or 0) + (held_qty if reservation.stock_held else 0)
        cart_items.append({
            'id': product.id,
            'name': product.product_name,
            'price': float(it.unit_price or 0),
            'originalPrice': float(it.unit_price or 0),
            'priceAdjusted': False,
            'currency': reservation.currency or 'UZS',
            'qty': held_qty,
            'img': product.image.url if product.image else '',
            'stock': avail,
        })

    _release_reservation_stock(reservation)
    reservation.status = 'Completed'
    reservation.save(update_fields=['status', 'stock_held', 'updated_at'])

    return JsonResponse({
        'success': True,
        'reservation_id': reservation.id,
        'customer_name': reservation.customer_name,
        'phone': reservation.phone or '',
        'currency': reservation.currency,
        'cart': cart_items,
        'message': f'Bron #{reservation.id} savatga yuklandi.',
    })


@login_required(login_url='login')
@portal_cap_required('reservations')
def reservations_list(request):
    is_manager = is_app_manager(request.user)
    qs = ProductReservation.objects.select_related(
        'branch', 'employee', 'customer'
    ).prefetch_related('items__product')
    if is_manager:
        qs = scope_queryset_by_branch(qs, request)
    else:
        emp = get_active_employee(request.user)
        if emp:
            qs = qs.filter(branch=emp.branch)
        else:
            qs = qs.none()

    status = request.GET.get('status') or 'Active'
    if status != 'All':
        qs = qs.filter(status=status)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(customer_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(note__icontains=q)
        )
    qs = qs.order_by('-created_at')
    active_qs = ProductReservation.objects.filter(status='Active')
    if is_manager:
        active_qs = scope_queryset_by_branch(active_qs, request)
    else:
        emp = get_active_employee(request.user)
        active_qs = active_qs.filter(branch=emp.branch) if emp else active_qs.none()
    if not is_manager:
        emp = get_active_employee(request.user)
        if emp:
            active_qs = active_qs.filter(branch=emp.branch)
    active_total = active_qs.aggregate(
        total=Coalesce(Sum('total_amount'), Decimal('0.00'))
    )['total']
    active_units = active_qs.aggregate(
        units=Coalesce(Sum('unit_count'), 0)
    )['units']
    page_obj = Paginator(qs, 15).get_page(request.GET.get('page'))
    return render(request, 'accounts/reservations_list.html', {
        'page_obj': page_obj,
        'is_manager': is_manager,
        'status_filter': status,
        'q': q,
        'active_count': active_qs.count(),
        'active_total': active_total,
        'active_units': active_units or 0,
    })


@login_required(login_url='login')
@portal_cap_required('btn_reservation_cancel')
@transaction.atomic
def reservation_cancel(request, pk):
    wants_json = (
        request.headers.get('Content-Type', '').startswith('application/json')
        or 'application/json' in (request.headers.get('Accept') or '')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )
    if request.method != 'POST':
        if wants_json:
            return JsonResponse({'success': False, 'message': 'POST kerak'}, status=405)
        return redirect('reservations_list')

    reservation = get_object_or_404(
        ProductReservation.objects.select_related('branch').prefetch_related('items__product'),
        pk=pk,
    )
    emp = get_active_employee(request.user)
    if not is_app_manager(request.user):
        if emp is None or reservation.branch_id != emp.branch_id:
            raise PermissionDenied
    if reservation.status != 'Active':
        msg = 'Bu bron allaqachon yopilgan.'
        if wants_json:
            return JsonResponse({'success': False, 'message': msg}, status=400)
        messages.error(request, msg)
        return redirect('reservations_list')

    _release_reservation_stock(reservation)
    reservation.status = 'Cancelled'
    reservation.save(update_fields=['status', 'stock_held', 'updated_at'])

    if wants_json:
        return JsonResponse({'success': True, 'message': 'Bron bekor qilindi.'})
    messages.success(request, f'Bron #{reservation.id} bekor qilindi.')
    return redirect('reservations_list')


@portal_cap_required('btn_order_approve')
@transaction.atomic
def order_approve(request, pk):
    if request.method != 'POST':
        return redirect('sales_display')
    order = get_object_or_404(
        Order.objects.select_related('branch', 'employee').prefetch_related('orderitem_set__product'),
        pk=pk, is_active=True,
    )
    if order.order_status != 'AwaitingApproval':
        messages.error(request, 'Bu buyurtma tasdiqlash holatida emas.')
        return redirect('sales_display')
    for item in order.orderitem_set.all():
        try:
            inventory = BranchInventory.objects.select_for_update().get(branch=order.branch, product=item.product)
        except BranchInventory.DoesNotExist:
            messages.error(request, f'{item.product.product_name} omborda topilmadi.')
            return redirect('sales_display')
        if inventory.quantity < item.quantity:
            messages.error(request, f'{item.product.product_name}: yetarli emas.')
            return redirect('sales_display')
        inventory.quantity -= item.quantity
        inventory.save(update_fields=['quantity'])
    payment = Payment.objects.create(
        order=order, amount_paid=order.total_amount, payment_type='CASH', date_paid=timezone.now(),
    )
    CashPayment.objects.create(payment=payment, cash_received=order.total_amount, change_given=Decimal('0.00'))
    order.order_status = 'Completed'
    order.save(update_fields=['order_status'])
    try:
        agent = order.employee.salesagent
        agent.total_sales += order.total_amount
        agent.total_commission_earned += order.total_amount * agent.commission_rate
        agent.save()
    except Exception:
        pass
    messages.success(request, f'Buyurtma #{order.id} tasdiqlandi.')
    return redirect('emp_receipt', pk=order.id)

@portal_cap_required('btn_order_approve')
@transaction.atomic
def order_reject(request, pk):
    if request.method != 'POST':
        return redirect('sales_display')
    order = get_object_or_404(Order, pk=pk, is_active=True)
    if order.order_status != 'AwaitingApproval':
        messages.error(request, 'Bu buyurtma bekor qilinadigan holatda emas.')
        return redirect('sales_display')
    order.order_status = 'Cancelled'
    order.save(update_fields=['order_status'])
    messages.success(request, f'Buyurtma #{order.id} bekor qilindi.')
    return redirect('sales_display')


@login_required(login_url='login')
def order_return(request, pk):
    """GET: qaytarish formasi. POST: qaytarishni bajarish."""
    order = get_object_or_404(
        Order.objects.select_related('branch', 'customer', 'employee').prefetch_related(
            'orderitem_set__product', 'debts', 'returns__items',
        ),
        pk=pk,
        is_active=True,
    )
    if not _user_can_access_order_return(request.user, order):
        raise PermissionDenied('Qaytarish uchun ruxsat yo‘q.')

    emp = get_active_employee(request.user)
    if emp is None and not request.user.is_superuser:
        raise PermissionDenied('Xodim profili topilmadi.')

    items = []
    for oi in order.orderitem_set.all():
        returnable = oi.returnable_quantity()
        items.append({
            'order_item': oi,
            'returnable': returnable,
            'returned': oi.returned_quantity(),
        })

    debt = order.get_primary_debt()
    prior_returns = order.returns.filter(status='Completed', is_active=True).order_by('-return_date')

    if request.method == 'POST':
        wants_json = (
            'application/json' in (request.content_type or '')
            or 'application/json' in (request.headers.get('Accept') or '')
            or request.headers.get('x-requested-with') == 'XMLHttpRequest'
        )
        try:
            if wants_json or (request.content_type or '').startswith('application/json'):
                data = json.loads(request.body or '{}')
                reason = (data.get('reason') or '').strip()
                raw_items = data.get('items') or []
            else:
                reason = (request.POST.get('reason') or '').strip()
                raw_items = []
                for oi in order.orderitem_set.all():
                    raw_qty = request.POST.get(f'qty_{oi.id}', '').strip()
                    if not raw_qty:
                        continue
                    qty = parse_decimal(raw_qty)
                    if qty > 0:
                        raw_items.append({'order_item_id': oi.id, 'quantity': str(qty)})

            if not order.can_be_returned():
                raise ValueError('Bu buyurtmadan qaytarish mumkin emas.')

            lines = _parse_return_lines(order, raw_items)
            processor = emp
            if processor is None and request.user.is_superuser:
                processor = order.employee
            sale_return = _execute_sale_return(
                order=order, employee=processor, lines=lines, reason=reason,
            )
        except ValueError as exc:
            if wants_json:
                return JsonResponse({'success': False, 'message': str(exc)}, status=400)
            messages.error(request, str(exc))
            return redirect('order_return', pk=order.id)
        except Exception as exc:
            if wants_json:
                return JsonResponse({'success': False, 'message': str(exc)}, status=500)
            messages.error(request, f'Qaytarish xatosi: {exc}')
            return redirect('order_return', pk=order.id)

        if wants_json:
            return JsonResponse({
                'success': True,
                'return_id': sale_return.id,
                'receipt_number': sale_return.receipt_number,
                'total_amount': str(sale_return.total_amount),
                'cash_refunded': str(sale_return.cash_refunded),
                'debt_reduced': str(sale_return.debt_reduced),
                'redirect': reverse('return_receipt', kwargs={'pk': sale_return.id}),
            })
        msg = (
            f'Qaytarish #{sale_return.receipt_number}: '
            f'{format_money(sale_return.total_amount, sale_return.currency)} '
            f'(naqd {format_money(sale_return.cash_refunded, sale_return.currency)}'
        )
        if sale_return.debt_reduced:
            msg += f', qarz −{format_money(sale_return.debt_reduced, sale_return.currency)}'
        msg += ').'
        messages.success(request, msg)
        return redirect('return_receipt', pk=sale_return.id)

    return render(request, 'accounts/order_return.html', {
        'order': order,
        'items': items,
        'debt': debt,
        'prior_returns': prior_returns,
        'can_return': order.can_be_returned(),
        'is_manager': is_app_manager(request.user),
    })


@login_required(login_url='login')
def return_receipt(request, pk):
    sale_return = get_object_or_404(
        SaleReturn.objects.select_related(
            'order', 'order__branch', 'order__customer', 'employee', 'customer', 'branch',
        ).prefetch_related('items__product'),
        pk=pk,
        is_active=True,
    )
    if not _user_can_access_order_return(request.user, sale_return.order):
        raise PermissionDenied
    org = getattr(sale_return.branch, 'organization', None) or Organization.get_default()
    org_logo = None
    if org and org.logo:
        try:
            org_logo = org.logo.url
        except Exception:
            org_logo = None
    return render(request, 'accounts/return_receipt.html', {
        'sale_return': sale_return,
        'order': sale_return.order,
        'brand_name': (org.brand_name if org else None) or 'Tezkor Savdo',
        'organization_name': sale_return.branch.organization_name,
        'org_logo': org_logo,
        'autoprint': request.GET.get('autoprint') == '1',
    })


@login_required(login_url='login')
@portal_cap_required('returns')
def returns_list(request):
    if not can_process_return(request.user):
        raise PermissionDenied('Qaytarishlar ro‘yxati uchun ruxsat yo‘q.')
    is_manager = is_app_manager(request.user)
    emp = get_active_employee(request.user)
    qs = (
        SaleReturn.objects
        .filter(is_active=True, status='Completed')
        .select_related('order', 'branch', 'employee', 'customer')
        .prefetch_related('items')
        .order_by('-return_date')
    )
    if is_manager:
        qs = scope_queryset_by_branch(qs, request)
    elif emp is None:
        qs = SaleReturn.objects.none()
    else:
        qs = qs.filter(branch=emp.branch)
    per_page = _list_page_size(request, default=15)
    page_obj = Paginator(qs, per_page).get_page(request.GET.get('page'))
    return render(request, 'accounts/returns_list.html', {
        'returns': page_obj,
        'is_manager': is_manager,
        'per_page': per_page,
    })


@login_required(login_url='login')
def warranty(request, pk):

    sales = get_object_or_404(Order, pk=pk)

    is_manager = request.user.is_superuser or hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'

    if not is_manager:
        raise PermissionDenied

    if request.method == 'POST':
        item_id =  request.POST.get('order_item_id')
        order_item = get_object_or_404(OrderItem, order=sales, id=item_id)
        product = order_item.product
        claim_type = request.POST.get('claim_type')

        if request.user.is_superuser:
            inventory_item = BranchInventory.objects.filter(product=product).first()
            if not inventory_item:
                messages.error(request, 'Mahsulot hech qaysi filial omborida topilmadi')
                return redirect('warranty', pk=pk)

            branch = inventory_item.branch
            handle_by_profile = getattr(request.user, 'employee', None)
        else:
            try:
                employee_profile = request.user.employee
                branch = employee_profile.branch
                inventory_item = BranchInventory.objects.filter(branch=branch, product=product).first()
                handle_by_profile = employee_profile
            except AttributeError:
                messages.error(request, "Sizga bog‘langan xodim profili yo‘q.")
                return redirect('warranty', pk=pk)

        faulty_serial = request.POST.get(f'faulty_serial_{item_id}')
        issue_description = request.POST.get('issue_description')
        days_since_purchase = (timezone.localdate() - sales.order_date.date()).days
        warranty_limit = order_item.effective_warranty_days()
        replacement_limit = order_item.effective_replacement_days()

        prior_service = (
            WarrantyClaims.objects.filter(
                order_item=order_item,
                claim_type='Repair',
                service_warranty_until__isnull=False,
                service_warranty_until__gte=timezone.localdate(),
            )
            .order_by('-service_warranty_until')
            .first()
        )
        under_service_warranty = prior_service is not None

        if claim_type == 'Replacement' and days_since_purchase > replacement_limit:
            messages.error(
                request,
                f"Almashtirish rad etildi. Mahsulot {days_since_purchase} kunlik "
                f"(Limit: {replacement_limit} kun).",
            )
            return redirect('warranty', pk=pk)

        if claim_type == 'Repair' and days_since_purchase > warranty_limit and not under_service_warranty:
            messages.error(
                request,
                f"Mahsulot kafolati tugagan. {days_since_purchase} kun o‘tgan "
                f"(Limit: {warranty_limit} kun). Ish kafolati ham amal qilmaydi.",
            )
            return redirect('warranty', pk=pk)

        if claim_type == 'Replacement':
            cost_impact = order_item.product.cost_price
            if inventory_item is None:
                messages.error(request, "Filialda bu mahsulot yo‘q.")
                return redirect('warranty', pk=pk)
            elif inventory_item.quantity < 1:
                messages.error(request, "Mahsulot omborda tugagan.")
                return redirect('warranty', pk=pk)
        elif claim_type == 'Repair':
            cost_impact = 1500.00
        else:
            cost_impact = 0.00

        existing_claim = WarrantyClaims.objects.filter(order_item=order_item, status__in=['Completed', 'Released']).exists()
        if existing_claim:
            messages.error(request, "Kafolat arizasi allaqachon berilgan.")
            return redirect('warranty', pk=pk)

        try:
            with transaction.atomic():
                claim = WarrantyClaims.objects.create(
                    order_item=order_item,
                    claim_type=claim_type,
                    faulty_serial=faulty_serial if faulty_serial else "Mavjud emas",
                    handled_by=handle_by_profile,
                    issue_description=issue_description,
                    cost_impact=cost_impact,
                    status='Completed' if claim_type == 'Replacement' else 'Pending'
                )

                if claim_type == 'Replacement':
                    inventory_item.refresh_from_db()
                    inventory_item.quantity = F('quantity') - 1
                    inventory_item.save()

                    DefectiveInventory.objects.create(
                        product=product,
                        branch=branch,
                        faulty_serial=faulty_serial,
                        reason=issue_description,
                        is_disposed=False
                    )

                    new_serial_input = request.POST.get(f'new_serial_{item_id}', 'Mavjud emas')

                    ReplacementRecord.objects.create(
                        warranty_claims=claim,
                        old_serial=faulty_serial,
                        new_serial=new_serial_input,
                    )
        except Exception as e:
            messages.error(request, f"Ma’lumotlar bazasi xatosi: {e}")
            return redirect('warranty', pk=pk)

        if claim_type == 'Repair' and under_service_warranty:
            messages.success(
                request,
                f'Muvaffaqiyatli! Ish kafolati doirasida qabul qilindi '
                f'(gacha: {prior_service.service_warranty_until}).',
            )
        else:
            messages.success(request, 'Kafolat arizasi muvaffaqiyatli yaratildi.')
        return redirect('warranty_list')

    items_info = []
    today = timezone.localdate()
    for item in sales.orderitem_set.select_related('product').all():
        days = (today - sales.order_date.date()).days
        w = item.effective_warranty_days()
        r = item.effective_replacement_days()
        s = item.effective_service_warranty_days()
        prior = (
            WarrantyClaims.objects.filter(
                order_item=item,
                claim_type='Repair',
                service_warranty_until__isnull=False,
            )
            .order_by('-service_warranty_until')
            .first()
        )
        items_info.append({
            'item': item,
            'days_since': days,
            'warranty_days': w,
            'replacement_days': r,
            'service_warranty_days': s,
            'repair_left': max(w - days, 0),
            'replace_left': max(r - days, 0),
            'service_until': prior.service_warranty_until if prior else None,
            'under_service': bool(prior and prior.service_warranty_until and prior.service_warranty_until >= today),
        })

    context = {
        'sales': sales,
        'items_info': items_info,
    }
    return render(request, 'accounts/warranty.html', context)

@login_required(login_url='login')
@portal_cap_required('dashboard')
def dashboard(request):

    now = timezone.localtime(timezone.now())

    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    def get_total(start_date):
        qs = scope_queryset_by_branch(
            OrderItem.objects.filter(
                order__order_date__gte=start_date,
                order__is_active=True,
                product__is_active=True,
            ),
            request,
            field='order__branch_id',
        )
        return qs.aggregate(
            total=Coalesce(
                Sum(F('unit_price') * F('quantity')),
                Decimal('0.00'),
                output_field=DecimalField()
            )
        )['total']

    weekly_total = get_total(start_of_week)
    monthly_total = get_total(start_of_month)
    yearly_total = get_total(start_of_year)

    claims_base = scope_queryset_by_branch(
        WarrantyClaims.objects.all(),
        request,
        field='order_item__order__branch_id',
    )
    pending_claims = claims_base.filter(status='Pending').count()
    in_progress_claims = claims_base.filter(status='In-Progress').count()
    completed_claims = claims_base.filter(status='Completed').count()
    released_claims = claims_base.filter(status='Released').count()
    repair = claims_base.filter(claim_type='Repair').count()
    replacement = claims_base.filter(claim_type='Replacement').count()
    claims = claims_base.select_related(
        'order_item__product', 'order_item__order__customer'
    )

    total_cost_impact = claims.aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    repair_cost_impact = claims.filter(
        claim_type='Repair',
    ).aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    replacement_cost_impact = claims.filter(
        claim_type='Replacement',
    ).aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    inv_scope = scope_queryset_by_branch(BranchInventory.objects.all(), request)
    low_stock = inv_scope.filter(quantity__lte=F('product__min_stock_level'), quantity__gt=0, product__is_active=True).count()

    out_of_stocks = inv_scope.filter(quantity=0, product__is_active=True).count()

    healthy_stocks = inv_scope.filter(quantity__gt=F('product__min_stock_level'), product__is_active=True).count()

    last_24_hrs = timezone.now() - timedelta(days=1)

    recent_stock = inv_scope.filter(date_added__gte=last_24_hrs).count()

    today = timezone.localtime(timezone.now()).date()

    yesterday = timezone.localtime(timezone.now()).date() - timedelta(days=1)

    today_oi = scope_queryset_by_branch(
        OrderItem.objects.filter(order__order_date=today, order__is_active=True),
        request,
        field='order__branch_id',
    )
    yesterday_oi = scope_queryset_by_branch(
        OrderItem.objects.filter(order__order_date=yesterday, order__is_active=True),
        request,
        field='order__branch_id',
    )
    today_total = today_oi.aggregate(
        total=Coalesce(Sum(F('order__total_amount') * F('quantity')), Decimal('0.00'))
    )['total']

    yesterday_total = yesterday_oi.aggregate(
        total=Coalesce(Sum(F('unit_price') * F('quantity')), Decimal('0.00'))
    )['total']

    if yesterday_total > 0:
        growth_percent = ((today_total - yesterday_total) / yesterday_total) * 100
    elif today_total > 0:
        growth_percent = 100.0
    else:
        growth_percent = 0.0

    active_staff = scope_queryset_by_branch(
        Employee.objects.filter(is_logged_in=True), request
    )

    context = {
        'active_staff': active_staff,
        'weekly_total': weekly_total,
        'monthly_total': monthly_total,
        'yearly_total': yearly_total,
        'pending_claims': pending_claims,
        'in_progress_claims': in_progress_claims,
        'completed_claims': completed_claims,
        'released_claims': released_claims,
        'repair': repair,
        'replacement': replacement,
        'total_cost_impact': total_cost_impact,
        'repair_cost_impact': repair_cost_impact,
        'replacement_cost_impact': replacement_cost_impact,
        'low_stock': low_stock,
        'out_of_stocks': out_of_stocks,
        'healthy_stocks': healthy_stocks,
        'recent_stock': recent_stock,
        'growth_percent': growth_percent,
        'today_total': today_total,
        'yesterday_total': yesterday_total
    }

    return render(request, 'accounts/dashboard.html', context)

@login_required(login_url='login')
@portal_cap_required('warranty')
def warranty_list(request):

    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'All':
        claims = WarrantyClaims.objects.filter(status=status_filter).select_related('order_item__product', 'order_item__order__customer').order_by('-date_filed')
    else:
        claims = WarrantyClaims.objects.all().select_related('order_item__product', 'order_item__order__customer').order_by('-date_filed')

    search_query = request.GET.get('q')
    if search_query:
        claims = claims.filter(
            Q(faulty_serial__icontains=search_query) |
            Q(order_item__order__customer__name__icontains=search_query)
        )

    total_cost_impact = claims.aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    repair_cost_impact = claims.filter(
        claim_type='Repair',
    ).aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    replacement_cost_impact = claims.filter(
        claim_type='Replacement',
    ).aggregate(
        total=Coalesce(Sum('cost_impact'), Decimal('0.00'))
    )['total']

    paginator = Paginator(claims, 5)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'claims': claims, 'total_cost_impact': total_cost_impact, 'repair_cost_impact': repair_cost_impact, 'replacement_cost_impact': replacement_cost_impact, 'page_obj': page_obj}

    return render(request, 'accounts/warranty_list.html', context)

@login_required(login_url='login')
@portal_cap_required('btn_export')
def warranty_list_export_csv(request):
    status_filter = request.GET.get('status')
    search_query = request.GET.get('q')

    claims = WarrantyClaims.objects.all().select_related('order_item__product', 'order_item__order__customer').order_by('-date_filed')

    if status_filter and status_filter != 'All':
        claims = claims.filter(status=status_filter)

    if search_query:
        claims = claims.filter(
            Q(faulty_serial__icontains=search_query) |
            Q(order_item__order__customer__name__icontains=search_query)
        )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="warranty_list.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ['Ariza ID', 'Mijoz', 'Mahsulot', 'Tur', 'Holat', 'Ariza sanasi']
    )

    for claim in claims:
        try:
            customer_name = claim.order_item.order.customer.name if claim.order_item.order.customer else "Oddiy mijoz"
        except AttributeError:
            customer_name = "Mavjud emas"

        product_name = claim.order_item.product.product_name if claim.order_item.product else "Noma’lum"

        writer.writerow(
            [
                claim.pk,
                customer_name,
                product_name,
                claim.get_claim_type_display(),
                claim.get_status_display(),
                claim.date_filed.strftime("%Y-%m-%d %H:%M") if claim.date_filed else "Mavjud emas"
            ]
        )

    return response

@login_required(login_url='login')
def update_claim_status(request, pk):
    if request.method == 'POST':
        claim = get_object_or_404(
            WarrantyClaims.objects.select_related('order_item', 'order_item__product'),
            pk=pk,
        )
        new_status = request.POST.get('status')

        if new_status:
            claim.status = new_status

            if new_status in ['Released', 'Completed'] and not claim.resolution_date:
                claim.resolution_date = timezone.now()

            if (
                claim.claim_type == 'Repair'
                and new_status in ['Released', 'Completed']
                and not claim.service_warranty_until
            ):
                claim.activate_service_warranty()

            claim.save()
            status_labels = {
                "Pending": "Kutilmoqda",
                "In-Progress": "Jarayonda",
                "Completed": "Yakunlangan",
                "Released": "Berilgan",
            }
            msg = f"Ariza #{claim.id} holati {status_labels.get(new_status, new_status)} ga yangilandi"
            if claim.service_warranty_until and new_status in ['Released', 'Completed']:
                msg += f". Ish kafolati: {claim.service_warranty_until} gacha"
            messages.success(request, msg)

    return redirect('warranty_list')

@login_required(login_url='login')
@portal_cap_required('audit')
def audit_logs(request):

    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    action_type = request.GET.get('action_type')

    logs = AuditTrail.objects.all().order_by('-timestamp')

    if start_date_str:
        start_date = parse_date(start_date_str)
        if start_date:
            logs = logs.filter(timestamp__date__gte=start_date)

    if end_date_str:
        end_date = parse_date(end_date_str)
        if end_date:
            logs = logs.filter(timestamp__date__lte=end_date)

    if action_type:
        logs = logs.filter(action=action_type)

    paginator = Paginator(logs, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'logs': page_obj,
        'start_date_str': start_date_str,
        'end_date_str': end_date_str,
        'action_type': action_type,
    }

    return render(request, 'accounts/audit_logs.html', context)

@login_required(login_url='login')
@portal_cap_required('btn_export')
def audit_logs_export_csv(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    action_type = request.GET.get('action_type')

    logs = AuditTrail.objects.all().order_by('-timestamp')

    if start_date_str:
        start_date = parse_date(start_date_str)
        if start_date:
            logs = logs.filter(timestamp__date__gte=start_date)

    if end_date_str:
        end_date = parse_date(end_date_str)
        if end_date:
            logs = logs.filter(timestamp__date__lte=end_date)

    if action_type:
        logs = logs.filter(action=action_type)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ['Vaqt', 'Foydalanuvchi', 'Amal', 'Model', 'IP manzil', 'Tavsif']
    )

    for log in logs:
        description = ""
        if isinstance(log.change_log, dict):
            description = ", ".join([f"{k}: {v}" for k, v in log.change_log.items()])
        else:
            description = str(log.change_log)

        writer.writerow(
            [
                log.timestamp,
                log.user.name,
                log.action,
                log.content_type.model,
                log.ip_address,
                description
            ]
        )

    return response

@login_required(login_url='login')
@portal_cap_required('debtors')
def debtors_list(request):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    is_manager = request.user.is_superuser or (
        hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'
    )
    debts = CustomerDebt.objects.select_related(
        'customer', 'branch', 'order', 'created_by'
    ).prefetch_related(
        'order__orderitem_set__product'
    ).all()

    if is_manager:
        debts = scope_queryset_by_branch(debts, request)
    elif hasattr(request.user, 'employee'):
        debts = debts.filter(branch=request.user.employee.branch)

    status = request.GET.get('status') or 'Active'
    if status == 'All':
        pass
    elif status == 'Active':
        debts = debts.exclude(status='Paid')
    else:
        debts = debts.filter(status=status)

    q = (request.GET.get('q') or '').strip()
    if q:
        debts = debts.filter(
            Q(customer__name__icontains=q) |
            Q(customer__phone__icontains=q) |
            Q(note__icontains=q) |
            Q(order__orderitem__product__product_name__icontains=q)
        ).distinct()

    debts = debts.order_by('-created_at')

    open_qs = CustomerDebt.objects.exclude(status='Paid')
    if is_manager:
        open_qs = scope_queryset_by_branch(open_qs, request)
    elif hasattr(request.user, 'employee'):
        open_qs = open_qs.filter(branch=request.user.employee.branch)

    total_remaining = open_qs.aggregate(
        total=Coalesce(Sum('remaining_balance'), Decimal('0.00'))
    )['total']
    open_count = open_qs.count()

    paginator = Paginator(debts, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/debtors_list.html', {
        'page_obj': page_obj,
        'debts': page_obj,
        'is_manager': is_manager,
        'total_remaining': total_remaining,
        'open_count': open_count,
        'status_filter': status,
        'q': q,
    })

@login_required(login_url='login')
@portal_cap_required('btn_debt_pay')
@transaction.atomic
def debt_pay(request, pk):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    if request.method != 'POST':
        return redirect('debtors_list')

    debt = get_object_or_404(CustomerDebt, pk=pk)
    is_manager = request.user.is_superuser or (
        hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'
    )
    if is_manager:
        allowed = get_admin_branch_ids(request)
        if allowed is False or (allowed is not None and debt.branch_id not in allowed):
            raise PermissionDenied
    elif hasattr(request.user, 'employee'):
        if debt.branch_id != request.user.employee.branch_id:
            raise PermissionDenied

    amount = parse_decimal(request.POST.get('amount'))
    note = (request.POST.get('note') or '').strip()

    if amount <= 0:
        messages.error(request, 'To‘lov summasi 0 dan katta bo‘lishi kerak.')
        return redirect('debtors_list')

    if amount > debt.remaining_balance:
        amount = debt.remaining_balance

    employee = getattr(request.user, 'employee', None)
    DebtPayment.objects.create(
        debt=debt,
        amount=amount,
        received_by=employee,
        note=note,
    )
    debt.paid_amount = (debt.paid_amount or Decimal('0')) + amount
    debt.remaining_balance = (debt.remaining_balance or Decimal('0')) - amount
    debt.refresh_status()
    debt.save()

    messages.success(request, f'{debt.customer.name}: {amount} {debt.currency} qabul qilindi.')
    return redirect('/debtors/?status=Active')


@login_required(login_url='login')
@portal_cap_required('btn_debt_edit')
def debt_edit(request, pk):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    debt = get_object_or_404(
        CustomerDebt.objects.select_related('customer', 'branch', 'order').prefetch_related(
            'order__orderitem_set__product',
            'payments__received_by',
        ),
        pk=pk,
    )
    is_manager = is_app_manager(request.user)
    if is_manager:
        allowed = get_admin_branch_ids(request)
        if allowed is False or (allowed is not None and debt.branch_id not in allowed):
            raise PermissionDenied
    elif hasattr(request.user, 'employee'):
        if debt.branch_id != request.user.employee.branch_id:
            raise PermissionDenied

    if request.method == 'POST':
        note = (request.POST.get('note') or '').strip()
        status = (request.POST.get('status') or debt.status).strip()
        if status not in dict(CustomerDebt.STATUS_CHOICES):
            status = debt.status
        original = parse_decimal(request.POST.get('original_amount'))
        paid = parse_decimal(request.POST.get('paid_amount'))
        if original < 0 or paid < 0:
            messages.error(request, 'Summalar manfiy bo‘lishi mumkin emas.')
            return redirect('debt_edit', pk=debt.pk)
        if paid > original:
            paid = original
        debt.original_amount = original
        debt.paid_amount = paid
        debt.remaining_balance = (original - paid).quantize(Decimal('0.01'))
        debt.note = note
        debt.status = status
        debt.refresh_status()
        debt.save()
        messages.success(request, f'Qarz #{debt.id} yangilandi.')
        return redirect('debtors_list')

    order_items = []
    if debt.order_id:
        order_items = list(debt.order.orderitem_set.all())

    return render(request, 'accounts/debt_edit.html', {
        'debt': debt,
        'is_manager': is_manager,
        'status_choices': CustomerDebt.STATUS_CHOICES,
        'order_items': order_items,
    })


@login_required(login_url='login')
@portal_cap_required('btn_debt_delete')
@transaction.atomic
def debt_delete(request, pk):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    if request.method != 'POST':
        return redirect('debtors_list')
    debt = get_object_or_404(CustomerDebt, pk=pk)
    is_manager = is_app_manager(request.user)
    if is_manager:
        allowed = get_admin_branch_ids(request)
        if allowed is False or (allowed is not None and debt.branch_id not in allowed):
            raise PermissionDenied
    elif hasattr(request.user, 'employee'):
        if debt.branch_id != request.user.employee.branch_id:
            raise PermissionDenied
    name = debt.customer.name if debt.customer_id else f'#{debt.id}'
    debt.delete()
    messages.success(request, f'Qarz o‘chirildi: {name}')
    return redirect('debtors_list')


@login_required(login_url='login')
@portal_cap_required('btn_customer_delete')
def customer_delete(request, pk):
    if request.method != 'POST':
        return redirect('customers_loyalty')
    customer = get_object_or_404(Customer, pk=pk)
    customer.is_active = False
    customer.save(update_fields=['is_active'])
    messages.success(request, f'Mijoz arxivlandi: {customer.name}')
    return redirect('customers_loyalty')


@login_required(login_url='login')
@portal_cap_required('btn_export')
def debtors_export_csv(request):
    if is_consultant(request.user):
        return redirect('pos_terminal')
    is_manager = request.user.is_superuser or (
        hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'
    )
    debts = CustomerDebt.objects.select_related('customer', 'branch').all()
    if is_manager:
        debts = scope_queryset_by_branch(debts, request)
    elif hasattr(request.user, 'employee'):
        debts = debts.filter(branch=request.user.employee.branch)

    status = request.GET.get('status') or 'Active'
    if status == 'All':
        pass
    elif status == 'Active':
        debts = debts.exclude(status='Paid')
    else:
        debts = debts.filter(status=status)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="qarzdorlar.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Mijoz', 'Telefon', 'Filial', 'Valyuta',
        'Dastlabki', 'To‘langan', 'Qoldiq', 'Holat', 'Sana',
    ])
    for d in debts.order_by('-created_at'):
        writer.writerow([
            d.id,
            d.customer.name,
            d.customer.phone,
            d.branch.name if d.branch else '',
            d.currency,
            d.original_amount,
            d.paid_amount,
            d.remaining_balance,
            d.get_status_display(),
            d.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response

def _expense_queryset_for(request):
    is_manager = request.user.is_superuser or (
        hasattr(request.user, 'employee') and request.user.employee.role == 'Manager'
    )
    qs = Expense.objects.filter(is_active=True).select_related('branch', 'created_by')
    if is_manager:
        qs = scope_queryset_by_branch(qs, request)
    elif hasattr(request.user, 'employee'):
        qs = qs.filter(branch=request.user.employee.branch)
    return qs, is_manager

@login_required(login_url='login')
@portal_cap_required('expenses')
def expenses_list(request):

    qs, is_manager = _expense_queryset_for(request)

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        category = request.POST.get('category') or 'other'
        amount = parse_decimal(request.POST.get('amount'))
        currency = (request.POST.get('currency') or CURRENCY_UZS).upper()
        note = (request.POST.get('note') or '').strip()
        date_raw = (request.POST.get('expense_date') or '').strip()
        expense_date = parse_date(date_raw) or timezone.localdate()

        if currency not in (CURRENCY_UZS, CURRENCY_USD):
            currency = CURRENCY_UZS
        if category not in dict(Expense.CATEGORY_CHOICES):
            category = 'other'

        if not title:
            messages.error(request, 'Xarajat nomini kiriting.')
            return redirect('expenses_list')
        if amount <= 0:
            messages.error(request, 'Summa 0 dan katta bo‘lishi kerak.')
            return redirect('expenses_list')

        branch = None
        if is_manager:
            allowed = _allowed_branches_qs(request)
            branch_id = request.POST.get('branch')
            if branch_id:
                branch = allowed.filter(pk=branch_id).first()
            if not branch:
                branch = allowed.first()
        else:
            emp = getattr(request.user, 'employee', None)
            branch = emp.branch if emp else None

        if not branch:
            messages.error(request, 'Filial topilmadi.')
            return redirect('expenses_list')

        Expense.objects.create(
            branch=branch,
            category=category,
            title=title,
            amount=amount,
            currency=currency,
            expense_date=expense_date,
            note=note,
            created_by=getattr(request.user, 'employee', None),
        )
        messages.success(request, f'Xarajat qo‘shildi: {title}')
        return redirect('expenses_list')

    category = request.GET.get('category') or ''
    q = (request.GET.get('q') or '').strip()
    if category and category in dict(Expense.CATEGORY_CHOICES):
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(note__icontains=q))

    qs = qs.order_by('-expense_date', '-created_at')

    now = timezone.localtime(timezone.now())
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()
    month_qs = qs.filter(expense_date__gte=start_month)

    total_all = qs.aggregate(t=Coalesce(Sum('amount'), Decimal('0.00')))['t']
    total_month = month_qs.aggregate(t=Coalesce(Sum('amount'), Decimal('0.00')))['t']
    count_all = qs.count()

    by_category = (
        qs.values('category')
        .annotate(total=Sum('amount'), cnt=Count('id'))
        .order_by('-total')
    )

    branches = list(_allowed_branches_qs(request)) if is_manager else []
    page_obj = Paginator(qs, 15).get_page(request.GET.get('page'))

    return render(request, 'accounts/expenses_list.html', {
        'page_obj': page_obj,
        'is_manager': is_manager,
        'branches': branches,
        'categories': Expense.CATEGORY_CHOICES,
        'category_filter': category,
        'q': q,
        'total_all': total_all,
        'total_month': total_month,
        'count_all': count_all,
        'by_category': by_category,
        'today': timezone.localdate().isoformat(),
    })

@login_required(login_url='login')
@portal_cap_required('btn_expense_delete')
def expense_delete(request, pk):
    if request.method != 'POST':
        return redirect('expenses_list')

    qs, is_manager = _expense_queryset_for(request)
    expense = get_object_or_404(qs, pk=pk)
    expense.soft_delete()
    messages.success(request, f'Xarajat o‘chirildi: {expense.title}')
    return redirect('expenses_list')

@login_required(login_url='login')
def customer_lookup(request):

    phone = (request.GET.get('phone') or '').strip()
    if len(phone) < 5:
        return JsonResponse({'found': False, 'message': 'Telefon qisqa'})
    customer = Customer.objects.filter(phone__iexact=phone, is_active=True).first()
    if not customer:

        customer = Customer.objects.filter(phone__icontains=phone[-9:], is_active=True).first()
    if not customer:
        return JsonResponse({'found': False})
    return JsonResponse({'found': True, 'customer': customer_payload(customer)})

def _make_price_tier_kind(name):
    base = slugify(name) or ''
    if not base:
        chars = ''.join(ch for ch in name.lower() if ch.isascii() and ch.isalnum())
        base = chars[:28] if chars else 'tur'
    base = base[:28]
    kind = base
    n = 2
    while PriceTier.objects.filter(Q(kind=kind) | Q(code=kind)).exists():
        kind = f'{base[:26]}-{n}'
        n += 1
    return kind


@login_required(login_url='login')
@portal_cap_required('settings')
def app_settings(request):
    app = AppSettings.get_solo()
    tiers_list = list(
        PriceTier.objects.exclude(kind=PriceTier.KIND_REGULAR).order_by('kind')
    )

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save_all').strip()

        if action == 'add_tier':
            name = (request.POST.get('new_tier_name') or '').strip()
            pct_raw = (request.POST.get('new_tier_percent') or '').strip().replace(',', '.')
            if not name:
                messages.error(request, 'Yangi tur uchun nom majburiy.')
                return redirect('app_settings')
            if pct_raw == '':
                pct = Decimal('0.00')
            else:
                try:
                    pct = Decimal(pct_raw)
                except Exception:
                    messages.error(request, f'Noto‘g‘ri foiz: {pct_raw}')
                    return redirect('app_settings')
                if pct < 0 or pct > 100:
                    messages.error(request, 'Chegirma 0–100% oralig‘ida bo‘lishi kerak.')
                    return redirect('app_settings')
            kind = _make_price_tier_kind(name)
            PriceTier.objects.create(
                kind=kind,
                code=kind,
                name=name,
                discount_percent=pct,
                is_active=True,
            )
            messages.success(request, f'Yangi tur qo‘shildi: {name}')
            return redirect('app_settings')

        if action == 'delete_tier':
            tier_id = request.POST.get('tier_id')
            tier = get_object_or_404(PriceTier, pk=tier_id)
            if tier.kind in PriceTier.SYSTEM_KINDS:
                messages.error(request, 'Tizim turlarini o‘chirib bo‘lmaydi.')
                return redirect('app_settings')
            in_use = Customer.objects.filter(customer_type=tier.kind).exists()
            if in_use:
                messages.error(
                    request,
                    f'«{tier.name}» turida mijozlar bor — avval ularning turini o‘zgartiring.',
                )
                return redirect('app_settings')
            label = tier.name
            tier.delete()
            messages.success(request, f'Tur o‘chirildi: {label}')
            return redirect('app_settings')

        vat_enabled = request.POST.get('vat_enabled') == '1'
        vat_raw = (request.POST.get('vat_percent') or '').strip()
        if vat_raw == '':
            vat_pct = app.vat_percent
        else:
            vat_pct = parse_decimal(vat_raw)
            if vat_pct < 0 or vat_pct > 100:
                messages.error(request, 'QQS 0–100 oralig‘ida bo‘lishi kerak.')
                return redirect('app_settings')
        secret_code = (request.POST.get('pos_secret_code') or '').strip()
        if secret_code and not any(ch.isalpha() for ch in secret_code):
            messages.error(
                request,
                'Chegirma kodida kamida bitta harf bo‘lishi shart (faqat raqam bo‘lishi mumkin emas).',
            )
            return redirect('app_settings')
        secret_raw = (request.POST.get('pos_secret_discount_percent') or '').strip()
        if secret_raw == '':
            secret_pct = app.pos_secret_discount_percent
        else:
            secret_pct = parse_decimal(secret_raw)
            if secret_pct < 0 or secret_pct > 100:
                messages.error(request, 'Chegirma 0–100% oralig‘ida bo‘lishi kerak.')
                return redirect('app_settings')
        markup_code = (request.POST.get('pos_secret_markup_code') or '').strip()
        if markup_code and not any(ch.isalpha() for ch in markup_code):
            messages.error(
                request,
                'Ustama kodida kamida bitta harf bo‘lishi shart (faqat raqam bo‘lishi mumkin emas).',
            )
            return redirect('app_settings')
        if secret_code and markup_code and secret_code == markup_code:
            messages.error(request, 'Chegirma va ustama kodlari bir xil bo‘lmasligi kerak.')
            return redirect('app_settings')
        markup_raw = (request.POST.get('pos_secret_markup_percent') or '').strip()
        if markup_raw == '':
            markup_pct = app.pos_secret_markup_percent
        else:
            markup_pct = parse_decimal(markup_raw)
            if markup_pct < 0 or markup_pct > 1000:
                messages.error(request, 'Ustama 0–1000% oralig‘ida bo‘lishi kerak.')
                return redirect('app_settings')
        theme_mode = (request.POST.get('theme_mode') or AppSettings.THEME_SYSTEM).strip()
        if theme_mode not in dict(AppSettings.THEME_MODE_CHOICES):
            theme_mode = AppSettings.THEME_SYSTEM
        day_raw = (request.POST.get('theme_day_start') or '').strip()
        night_raw = (request.POST.get('theme_night_start') or '').strip()
        if theme_mode == AppSettings.THEME_AUTO:
            try:
                day_start = int(day_raw)
                night_start = int(night_raw)
            except (TypeError, ValueError):
                messages.error(request, 'Tema soatlari noto‘g‘ri.')
                return redirect('app_settings')
            if day_start < 0 or day_start > 23 or night_start < 0 or night_start > 23:
                messages.error(request, 'Soatlar 0–23 oralig‘ida bo‘lishi kerak.')
                return redirect('app_settings')
        else:
            day_start = app.theme_day_start
            night_start = app.theme_night_start

        for tier in tiers_list:
            prefix = f'tier_{tier.id}_'
            name = (request.POST.get(prefix + 'name') or '').strip()
            pct_raw = (request.POST.get(prefix + 'percent') or '').strip().replace(',', '.')
            if not name:
                messages.error(request, f'«{tier.get_kind_display()}» uchun nom majburiy.')
                return redirect('app_settings')
            if pct_raw == '':
                pct = tier.discount_percent
            else:
                try:
                    pct = Decimal(pct_raw)
                except Exception:
                    messages.error(request, f'Noto‘g‘ri foiz: {pct_raw}')
                    return redirect('app_settings')
                if pct < 0 or pct > 100:
                    messages.error(request, 'Chegirma 0–100% oralig‘ida bo‘lishi kerak.')
                    return redirect('app_settings')
            tier.name = name
            tier.code = tier.kind
            tier.discount_percent = pct
            tier.save(update_fields=['name', 'code', 'discount_percent'])

        app.vat_enabled = vat_enabled
        app.vat_percent = vat_pct
        app.pos_secret_code = secret_code
        app.pos_secret_discount_percent = secret_pct
        app.pos_secret_markup_code = markup_code
        app.pos_secret_markup_percent = markup_pct
        app.theme_mode = theme_mode
        app.theme_day_start = day_start
        app.theme_night_start = night_start
        app.save()
        messages.success(request, 'Sozlamalar saqlandi.')
        return redirect('app_settings')

    return render(request, 'accounts/app_settings.html', {
        'app': app,
        'tiers_list': tiers_list,
        'theme_choices': AppSettings.THEME_MODE_CHOICES,
        'system_kinds': PriceTier.SYSTEM_KINDS,
    })


def _normalize_customer_phone(phone):
    phone = (phone or '').strip()
    phone_digits = ''.join(ch for ch in phone if ch.isdigit())
    if phone_digits.startswith('998'):
        phone_digits = phone_digits[3:]
    if len(phone_digits) < 9:
        return None, phone_digits
    if not phone.startswith('+'):
        phone = '+998' + phone_digits
    elif not phone.startswith('+998'):
        phone = '+998' + phone_digits
    return phone, phone_digits


@login_required(login_url='login')
@portal_cap_required('customers')
def customers_loyalty(request):
    allowed_types = list(
        PriceTier.objects.exclude(kind=PriceTier.KIND_REGULAR)
        .filter(is_active=True)
        .values_list('kind', flat=True)
    )
    if not allowed_types:
        allowed_types = [Customer.TYPE_LOYAL, Customer.TYPE_PARTNER]
    default_type = (
        Customer.TYPE_LOYAL if Customer.TYPE_LOYAL in allowed_types else allowed_types[0]
    )

    if request.method == 'POST':
        pk = request.POST.get('customer_id')
        name = (request.POST.get('name') or '').strip()
        phone, phone_digits = _normalize_customer_phone(request.POST.get('phone'))
        cust_type = request.POST.get('customer_type') or default_type
        if cust_type not in allowed_types:
            cust_type = default_type
        if not name or not phone:
            messages.error(request, 'Ism va to‘liq telefon (+998…) majburiy.')
            return redirect('customers_loyalty')
        bonus_raw = (request.POST.get('bonus_discount_percent') or '').strip().replace(',', '.')
        try:
            bonus_pct = Decimal(bonus_raw) if bonus_raw != '' else Decimal('0.00')
        except Exception:
            messages.error(request, 'Shaxsiy aksiya foizi noto‘g‘ri.')
            return redirect('customers_loyalty')
        if bonus_pct < 0 or bonus_pct > 100:
            messages.error(request, 'Shaxsiy aksiya 0–100% oralig‘ida bo‘lishi kerak.')
            return redirect('customers_loyalty')

        tier = PriceTier.objects.filter(kind=cust_type, is_active=True).first()
        if pk:
            customer = get_object_or_404(Customer, pk=pk)
            customer.name = name
            customer.phone = phone
            customer.customer_type = cust_type
            customer.price_tier = tier
            customer.bonus_discount_percent = bonus_pct
            customer.is_active = True
            customer.save()
            messages.success(request, f'Yangilandi: {customer.name}')
        else:
            existing = Customer.objects.filter(phone=phone).first()
            if existing:
                existing.name = name
                existing.customer_type = cust_type
                existing.price_tier = tier
                existing.bonus_discount_percent = bonus_pct
                existing.is_active = True
                existing.save()
                messages.success(request, f'Mavjud mijoz yangilandi: {existing.name}')
            else:
                customer = Customer.objects.create(
                    name=name,
                    phone=phone,
                    customer_type=cust_type,
                    price_tier=tier,
                    bonus_discount_percent=bonus_pct,
                )
                messages.success(request, f'Qo‘shildi: {customer.name}')
        return redirect('customers_loyalty')

    type_filter = request.GET.get('type') or ''
    q = (request.GET.get('q') or '').strip()
    sort = request.GET.get('sort') or 'spend'

    active_orders = Q(
        order__is_active=True,
        order__deleted_at__isnull=True,
    ) & ~Q(order__order_status__in=['AwaitingApproval', 'Cancelled'])
    qs = Customer.objects.filter(
        is_active=True,
        customer_type__in=allowed_types,
    ).select_related('price_tier').annotate(
        orders_count=Coalesce(Count('order', filter=active_orders), 0),
        total_spent=Coalesce(Sum('order__total_amount', filter=active_orders), _ZERO_MONEY),
        last_purchase=Max('order__order_date', filter=active_orders),
    )
    if type_filter in allowed_types:
        qs = qs.filter(customer_type=type_filter)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q))
    if sort == 'orders':
        qs = qs.order_by('-orders_count', '-total_spent', 'name')
    elif sort == 'name':
        qs = qs.order_by('name')
    else:
        qs = qs.order_by('-total_spent', '-orders_count', 'name')
    page_obj = Paginator(qs, 20).get_page(request.GET.get('page'))
    loyalty_type_choices = PriceTier.discount_type_choices()

    ranking = list(
        Customer.objects.filter(is_active=True, customer_type__in=allowed_types)
        .annotate(
            orders_count=Coalesce(Count('order', filter=active_orders), 0),
            total_spent=Coalesce(Sum('order__total_amount', filter=active_orders), _ZERO_MONEY),
        )
        .filter(orders_count__gt=0)
        .order_by('-total_spent')[:10]
    )

    return render(request, 'accounts/customers_loyalty.html', {
        'page_obj': page_obj,
        'type_filter': type_filter,
        'q': q,
        'sort': sort,
        'type_choices': loyalty_type_choices,
        'ranking': ranking,
        'loyal_count': Customer.objects.filter(is_active=True, customer_type=Customer.TYPE_LOYAL).count(),
        'partner_count': Customer.objects.filter(is_active=True, customer_type=Customer.TYPE_PARTNER).count(),
        'loyalty_customers_count': Customer.objects.filter(
            is_active=True, customer_type__in=allowed_types
        ).count(),
    })


@login_required(login_url='login')
@portal_cap_required('btn_customer_edit')
def customer_detail(request, pk):
    customer = get_object_or_404(
        Customer.objects.select_related('price_tier'),
        pk=pk,
    )
    allowed_types = list(
        PriceTier.objects.exclude(kind=PriceTier.KIND_REGULAR)
        .filter(is_active=True)
        .values_list('kind', flat=True)
    )
    if not allowed_types:
        allowed_types = [Customer.TYPE_LOYAL, Customer.TYPE_PARTNER]

    if request.method == 'POST':
        action = (request.POST.get('action') or 'save').strip()
        if action == 'apply_suggested':
            stats = _customer_purchase_stats(customer)
            suggested = _suggest_bonus_percent(
                stats['total_spent'], stats['orders_count'], customer.bonus_discount_percent
            )
            if suggested is None:
                messages.info(request, 'Hozircha yuqoriroq aksiya tavsiya qilinmaydi.')
            else:
                customer.bonus_discount_percent = suggested
                customer.save(update_fields=['bonus_discount_percent'])
                messages.success(request, f'Shaxsiy aksiya −{suggested}% qilib belgiladi.')
            return redirect('customer_detail', pk=customer.pk)

        name = (request.POST.get('name') or '').strip()
        phone, _digits = _normalize_customer_phone(request.POST.get('phone'))
        cust_type = request.POST.get('customer_type') or customer.customer_type
        if cust_type not in allowed_types and cust_type != Customer.TYPE_REGULAR:
            cust_type = customer.customer_type
        notes = (request.POST.get('notes') or '').strip()
        bonus_raw = (request.POST.get('bonus_discount_percent') or '').strip().replace(',', '.')
        try:
            bonus_pct = Decimal(bonus_raw) if bonus_raw != '' else Decimal('0.00')
        except Exception:
            messages.error(request, 'Shaxsiy aksiya foizi noto‘g‘ri.')
            return redirect('customer_detail', pk=customer.pk)
        if bonus_pct < 0 or bonus_pct > 100:
            messages.error(request, 'Shaxsiy aksiya 0–100% oralig‘ida bo‘lishi kerak.')
            return redirect('customer_detail', pk=customer.pk)
        if not name or not phone:
            messages.error(request, 'Ism va telefon majburiy.')
            return redirect('customer_detail', pk=customer.pk)

        tier = PriceTier.objects.filter(kind=cust_type, is_active=True).first()
        customer.name = name
        customer.phone = phone
        customer.customer_type = cust_type
        customer.price_tier = tier
        customer.bonus_discount_percent = bonus_pct
        customer.notes = notes
        customer.is_active = True
        customer.save()
        messages.success(request, 'Mijoz ma’lumotlari saqlandi.')
        return redirect('customer_detail', pk=customer.pk)

    stats = _customer_purchase_stats(customer)
    suggested = _suggest_bonus_percent(
        stats['total_spent'], stats['orders_count'], customer.bonus_discount_percent
    )
    orders = (
        _active_order_stats_qs()
        .filter(customer=customer)
        .select_related('branch', 'employee')
        .prefetch_related('orderitem_set__product')
        .order_by('-order_date')
    )
    page_obj = Paginator(orders, 15).get_page(request.GET.get('page'))
    type_choices = [(Customer.TYPE_REGULAR, 'Oddiy mijoz')] + list(
        PriceTier.discount_type_choices()
    )

    return render(request, 'accounts/customer_detail.html', {
        'customer': customer,
        'stats': stats,
        'suggested_bonus': suggested,
        'page_obj': page_obj,
        'type_choices': type_choices,
        'effective_discount': customer.get_discount_percent(),
        'tier_discount': customer.get_tier_discount_percent(),
    })
