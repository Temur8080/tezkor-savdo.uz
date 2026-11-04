"""Mavjud sotuv / audit / ombor yozuvlaridan ProductHistory ni tiklash.

Faqat muhim amallar: kirim, sotuv, qaytarish, narx o‘zgarishi, tugagan.
Vaqtinchalik qoldiq ushlab turish / qo‘lda tahrir shovqini yozilmaydi.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import (
    AuditTrail,
    BranchInventory,
    OrderItem,
    Product,
    ProductHistory,
    SaleReturnItem,
)


BACKFILL_TAG = '[tiklangan]'


def _dec(value, default=None):
    if value is None or value == '':
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _set_created_at(pk, when):
    if when is None:
        return
    ProductHistory.objects.filter(pk=pk).update(created_at=when)


class Command(BaseCommand):
    help = 'Mahsulot tarixini sotuv, qaytarish va audit yozuvlaridan tiklaydi (faqat muhim amallar)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help=f'Avvalgi {BACKFILL_TAG} yozuvlarni o‘chirib qayta tiklaydi',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat hisoblaydi, bazaga yozmaydi',
        )

    def handle(self, *args, **options):
        force = options['force']
        dry = options['dry_run']

        existing_backfill = ProductHistory.objects.filter(note__startswith=BACKFILL_TAG).count()
        existing_live = ProductHistory.objects.exclude(note__startswith=BACKFILL_TAG).count()

        if existing_backfill and not force:
            self.stdout.write(self.style.WARNING(
                f'Allaqachon {existing_backfill} ta tiklangan yozuv bor. '
                f'Qayta ishlash uchun --force bering.'
            ))
            return

        if dry:
            self.stdout.write('DRY-RUN: bazaga yozilmaydi')

        with transaction.atomic():
            if force and not dry:
                deleted, _ = ProductHistory.objects.filter(note__startswith=BACKFILL_TAG).delete()
                self.stdout.write(f'Eski tiklangan yozuvlar o‘chirildi: {deleted}')

            created = 0
            created += self._backfill_stock_audits(dry=dry)
            created += self._backfill_orphan_sales(dry=dry)
            created += self._backfill_returns(dry=dry)
            created += self._backfill_price_audits(dry=dry)

            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'Tayyor: {created} ta yozuv'
            + (' (dry-run)' if dry else '')
            + (f'; jonli yozuvlar: {existing_live}' if existing_live else '')
        ))

    def _backfill_stock_audits(self, *, dry: bool) -> int:
        """Kirim + sotuv (audit); bron/tahrir juftliklari tashlab ketiladi."""
        ct = ContentType.objects.get_for_model(BranchInventory)
        inv_map = {
            inv.id: inv
            for inv in BranchInventory.objects.select_related('product', 'branch')
        }

        sale_index = []
        for oi in (
            OrderItem.objects
            .filter(order__is_active=True, order__order_status__in=('Completed', 'Pending', 'Returned'))
            .select_related('order', 'product', 'order__employee', 'order__branch')
        ):
            sale_index.append({
                'oi': oi,
                'product_id': oi.product_id,
                'branch_id': oi.order.branch_id,
                'qty': oi.quantity or Decimal('0'),
                'when': oi.order.order_date,
                'used': False,
            })

        # 1) Barcha miqdor o‘zgarishlarini yig‘ish
        moves = []
        audits = (
            AuditTrail.objects
            .filter(content_type=ct)
            .select_related('user')
            .order_by('timestamp', 'id')
        )
        for audit in audits:
            inv = inv_map.get(audit.object_id)
            if not inv:
                continue
            log = audit.change_log or {}
            qty_change = log.get('quantity')

            old_q = new_q = None
            if isinstance(qty_change, dict):
                old_q = _dec(qty_change.get('old'))
                new_q = _dec(qty_change.get('new'))
            elif audit.action == 'CREATE':
                new_q = _dec(qty_change if not isinstance(qty_change, dict) else qty_change)
                if new_q is None:
                    continue
                old_q = Decimal('0')
            else:
                continue

            if old_q is None or new_q is None:
                continue
            delta = new_q - old_q
            if audit.action == 'CREATE' and new_q == 0:
                continue
            if delta == 0:
                continue

            moves.append({
                'audit': audit,
                'inv': inv,
                'delta': delta,
                'new_q': new_q,
                'skip': False,
                'sale': None,
            })

        # 2) Sotuvlarga bog‘lash
        for move in moves:
            if move['delta'] >= 0:
                continue
            need = -move['delta']
            window = timedelta(seconds=5)
            inv = move['inv']
            for slot in sale_index:
                if slot['used']:
                    continue
                if slot['product_id'] != inv.product_id or slot['branch_id'] != inv.branch_id:
                    continue
                if slot['qty'] != need or slot['when'] is None:
                    continue
                if abs(slot['when'] - move['audit'].timestamp) <= window:
                    move['sale'] = slot
                    slot['used'] = True
                    break

        # 3) Sotuv bo‘lmagan −/+ juftliklarni (bron ushlash/qaytarish) o‘chirish
        pair_window = timedelta(hours=6)
        for i, move in enumerate(moves):
            if move['skip'] or move['sale'] or move['delta'] >= 0:
                continue
            abs_d = -move['delta']
            inv = move['inv']
            for j in range(i + 1, len(moves)):
                nxt = moves[j]
                if nxt['skip'] or nxt['sale']:
                    continue
                if nxt['inv'].id != inv.id:
                    continue
                if nxt['audit'].timestamp - move['audit'].timestamp > pair_window:
                    break
                if nxt['delta'] == abs_d:
                    move['skip'] = True
                    nxt['skip'] = True
                    break

        # 4) Faqat kirim va sotuvni yozish; bog‘lanmagan − ni tashlash
        created = 0
        for move in moves:
            if move['skip']:
                continue
            delta = move['delta']
            if delta < 0 and not move['sale']:
                continue

            audit = move['audit']
            inv = move['inv']
            new_q = move['new_q']

            if delta > 0:
                event = ProductHistory.EVENT_STOCK_IN
                note = f'{BACKFILL_TAG} Ombor kirimi'
                order = None
                user = audit.user
                unit_price = inv.product.base_price
                currency = inv.product.currency
            else:
                oi = move['sale']['oi']
                event = ProductHistory.EVENT_SALE
                note = f'{BACKFILL_TAG} Sotuv #{oi.order_id}'
                order = oi.order
                user = oi.order.employee or audit.user
                unit_price = oi.unit_price
                currency = oi.order.currency or inv.product.currency

            if dry:
                created += 1
                if new_q <= 0 and event == ProductHistory.EVENT_SALE:
                    created += 1
                continue

            row = ProductHistory.objects.create(
                product=inv.product,
                branch=inv.branch,
                event_type=event,
                quantity=delta,
                quantity_after=new_q,
                unit_price=unit_price,
                currency=currency or '',
                order=order,
                user=user,
                note=note[:255],
            )
            _set_created_at(row.pk, audit.timestamp)
            created += 1

            if new_q <= 0 and event == ProductHistory.EVENT_SALE:
                dep = ProductHistory.objects.create(
                    product=inv.product,
                    branch=inv.branch,
                    event_type=ProductHistory.EVENT_DEPLETED,
                    quantity=None,
                    quantity_after=new_q,
                    unit_price=unit_price,
                    currency=currency or '',
                    order=order,
                    user=user,
                    note=f'{BACKFILL_TAG} Omborda qoldiq tugadi',
                )
                _set_created_at(dep.pk, audit.timestamp)
                created += 1

        self.stdout.write(f'  stock/audit: {created}')
        self._unused_sales = [s for s in sale_index if not s['used']]
        return created

    def _backfill_orphan_sales(self, *, dry: bool) -> int:
        unused = getattr(self, '_unused_sales', [])
        created = 0
        for slot in unused:
            oi = slot['oi']
            order = oi.order
            inv = BranchInventory.objects.filter(branch_id=order.branch_id, product_id=oi.product_id).first()
            if dry:
                created += 1
                continue
            row = ProductHistory.objects.create(
                product=oi.product,
                branch=order.branch,
                event_type=ProductHistory.EVENT_SALE,
                quantity=-(oi.quantity or Decimal('0')),
                quantity_after=inv.quantity if inv else None,
                unit_price=oi.unit_price,
                currency=order.currency or getattr(oi.product, 'currency', '') or '',
                order=order,
                user=order.employee,
                note=f'{BACKFILL_TAG} Sotuv #{order.id}',
            )
            _set_created_at(row.pk, order.order_date)
            created += 1
        self.stdout.write(f'  orphan sales: {created}')
        return created

    def _backfill_returns(self, *, dry: bool) -> int:
        created = 0
        qs = (
            SaleReturnItem.objects
            .filter(sale_return__is_active=True, sale_return__status='Completed')
            .select_related(
                'sale_return', 'product', 'sale_return__branch',
                'sale_return__employee', 'sale_return__order',
            )
        )
        for item in qs:
            ret = item.sale_return
            inv = BranchInventory.objects.filter(branch=ret.branch, product=item.product).first()
            if dry:
                created += 1
                continue
            row = ProductHistory.objects.create(
                product=item.product,
                branch=ret.branch,
                event_type=ProductHistory.EVENT_RETURN,
                quantity=item.quantity,
                quantity_after=inv.quantity if inv else None,
                unit_price=item.unit_price,
                currency=ret.currency or '',
                order=ret.order,
                user=ret.employee,
                note=f'{BACKFILL_TAG} Qaytarish · {ret.receipt_number}',
            )
            _set_created_at(row.pk, ret.return_date)
            created += 1
        self.stdout.write(f'  returns: {created}')
        return created

    def _backfill_price_audits(self, *, dry: bool) -> int:
        ct = ContentType.objects.get_for_model(Product)
        products = {p.id: p for p in Product.objects.all()}
        created = 0
        audits = (
            AuditTrail.objects
            .filter(content_type=ct)
            .select_related('user')
            .order_by('timestamp', 'id')
        )
        for audit in audits:
            product = products.get(audit.object_id)
            if not product:
                continue
            log = audit.change_log or {}
            if 'base_price' not in log:
                continue
            price_change = log.get('base_price')
            if isinstance(price_change, dict):
                old_p = _dec(price_change.get('old'))
                new_p = _dec(price_change.get('new'))
            else:
                old_p = None
                new_p = _dec(price_change)
            if new_p is None:
                continue
            if old_p is not None and old_p == new_p:
                continue

            inv = (
                BranchInventory.objects
                .filter(product=product)
                .select_related('branch')
                .order_by('id')
                .first()
            )
            if dry:
                created += 1
                continue
            row = ProductHistory.objects.create(
                product=product,
                branch=inv.branch if inv else None,
                event_type=ProductHistory.EVENT_PRICE_CHANGE,
                quantity_after=inv.quantity if inv else None,
                old_price=old_p,
                new_price=new_p,
                unit_price=new_p,
                currency=product.currency or '',
                user=audit.user,
                note=f'{BACKFILL_TAG} Narx o‘zgarishi',
            )
            _set_created_at(row.pk, audit.timestamp)
            created += 1
        self.stdout.write(f'  price audits: {created}')
        return created
