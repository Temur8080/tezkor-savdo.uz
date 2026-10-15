from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal('0.01')

def money(value):
    return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def apply_discount(unit_price, discount_percent):
    price = money(unit_price)
    pct = money(discount_percent)
    if pct <= 0:
        return price
    if pct > Decimal('100'):
        pct = Decimal('100')
    return money(price * (Decimal('100') - pct) / Decimal('100'))


def apply_markup(unit_price, markup_percent):
    price = money(unit_price)
    pct = money(markup_percent)
    if pct <= 0:
        return price
    if pct > Decimal('1000'):
        pct = Decimal('1000')
    return money(price * (Decimal('100') + pct) / Decimal('100'))

def customer_payload(customer):
    if not customer:
        return None
    pct = customer.get_discount_percent()
    tier_pct = customer.get_tier_discount_percent()
    bonus = customer.bonus_discount_percent or Decimal('0.00')
    return {
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone or '',
        'email': customer.email or '',
        'address': customer.address or '',
        'customer_type': customer.customer_type,
        'customer_type_label': customer.get_customer_type_display(),
        'discount_percent': str(pct),
        'tier_discount_percent': str(tier_pct),
        'bonus_discount_percent': str(bonus),
        'is_partner': customer.customer_type == customer.TYPE_PARTNER,
    }
