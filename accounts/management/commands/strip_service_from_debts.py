"""Mavjud qarzlardan to‘lanmagan xizmat (ustanovka / ornatib berish) qismini olib tashlash.

Qoida (kassadagi yangi hisob bilan bir xil): naqd avval xizmatga sanaladi,
qarz faqat tovar qismidan iborat bo‘ladi:

    maqsad_qarz = max(0, tovar_summasi - max(0, naqd - xizmat_summasi))
    yangi_dastlabki_qarz = min(dastlabki_qarz, maqsad_qarz)

Faqat kamaytiradi (hech qachon oshirmaydi) va qayta yurgizilsa o‘zgarmaydi.
To‘langan summa (paid_amount) o‘zgarmaydi; qoldiq va holat qayta hisoblanadi.
Standart rejim — faqat ko‘rsatish (dry-run). O‘zgartirish uchun --apply.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomerDebt

ZERO = Decimal('0.00')


class Command(BaseCommand):
    help = 'Qarzlardan to‘lanmagan xizmat (usta haqqi) qismini olib tashlaydi (standart: dry-run).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='O‘zgarishlarni bazaga yozish')

    def handle(self, *args, **options):
        apply = options['apply']
        qs = (
            CustomerDebt.objects
            .filter(order__isnull=False, order__service_amount__gt=0)
            .select_related('order', 'customer')
            .order_by('id')
        )
        changed = 0
        total_removed = ZERO
        with transaction.atomic():
            for debt in qs:
                order = debt.order
                service = order.service_amount or ZERO
                cash = order.get_cash_received() or ZERO
                target = max(ZERO, order.shop_amount - max(ZERO, cash - service))
                original = debt.original_amount or ZERO
                if original <= target:
                    self.stdout.write(
                        f'#{debt.id} buyurtma {order.id}: o‘zgarmaydi '
                        f'(qarz {original} <= tovar qismi {target})'
                    )
                    continue
                new_original = target.quantize(Decimal('0.01'))
                cut = original - new_original
                paid = debt.paid_amount or ZERO
                new_remaining = max(ZERO, new_original - paid).quantize(Decimal('0.01'))
                self.stdout.write(
                    f'#{debt.id} buyurtma {order.id} ({debt.customer}): '
                    f'dastlabki {original} -> {new_original}, '
                    f'qoldiq {debt.remaining_balance} -> {new_remaining}, '
                    f'holat {debt.status}'
                )
                changed += 1
                total_removed += cut
                if apply:
                    debt.original_amount = new_original
                    debt.remaining_balance = new_remaining
                    debt.refresh_status()
                    old_note = (debt.note or '').strip()
                    tag = f'Ustanovka {cut} qarzdan olib tashlandi'
                    debt.note = (f'{old_note} | {tag}' if old_note else tag)[:255]
                    debt.save()
            if not apply:
                transaction.set_rollback(True)

        mode = 'YOZILDI' if apply else 'DRY-RUN (hech narsa yozilmadi; --apply bilan yozing)'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: {changed} ta qarz, jami olib tashlangan {total_removed}'
        ))
