from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.utils.safestring import mark_safe

CURRENCY_UZS = 'UZS'
CURRENCY_USD = 'USD'

CURRENCY_CHOICES = (
    (CURRENCY_UZS, 'So‘m'),
    (CURRENCY_USD, 'Dollar'),
)

CURRENCY_LABELS = {
    CURRENCY_UZS: 'so‘m',
    CURRENCY_USD: '$',
}

def parse_decimal(value):
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        raw = str(value).replace(' ', '').replace('\u00a0', '')

        if raw.count(',') > 1 or (',' in raw and '.' in raw):
            raw = raw.replace(',', '')
        else:
            raw = raw.replace(',', '.')
        return Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')

def format_number(value, decimals=None):

    amount = parse_decimal(value)

    if decimals is None:

        if amount == amount.to_integral_value():
            decimals = 0
        else:
            decimals = 2

    if decimals == 0:
        quantized = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        sign = '-' if quantized < 0 else ''
        digits = f"{abs(int(quantized))}"
        grouped = ' '.join(reversed([digits[max(i - 3, 0):i] for i in range(len(digits), 0, -3)]))
        return f"{sign}{grouped}"

    quantized = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    sign = '-' if quantized < 0 else ''
    abs_val = abs(quantized)
    whole = int(abs_val)
    frac = f"{abs_val - whole:.2f}"[2:]
    digits = str(whole)
    grouped = ' '.join(reversed([digits[max(i - 3, 0):i] for i in range(len(digits), 0, -3)]))
    return f"{sign}{grouped}.{frac}"

def format_money(value, currency=CURRENCY_UZS, decimals=None):
    currency = (currency or CURRENCY_UZS).upper()
    if currency not in (CURRENCY_UZS, CURRENCY_USD):
        currency = CURRENCY_UZS

    if decimals is None:
        decimals = 2 if currency == CURRENCY_USD else 0

    number = format_number(value, decimals=decimals)
    if currency == CURRENCY_USD:
        return mark_safe(f"${number}")
    return mark_safe(f"{number} so‘m")


def format_qty(value):
    """Miqdor ko‘rsatish: 5.000 → 5, 12.500 → 12.5 (vergul/000 chalkashmasin)."""
    if value is None or value == '':
        return '0'
    amount = parse_decimal(value)
    quantized = amount.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    text = f'{quantized:.3f}'.rstrip('0').rstrip('.')
    return text or '0'

def convert_amount(amount, from_currency, to_currency, usd_rate):

    amount = parse_decimal(amount)
    fr = (from_currency or CURRENCY_UZS).upper()
    to = (to_currency or CURRENCY_UZS).upper()
    if fr == to:
        return amount
    rate = parse_decimal(usd_rate)
    if rate <= 0:
        rate = Decimal('1')
    if fr == CURRENCY_USD and to == CURRENCY_UZS:
        return (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if fr == CURRENCY_UZS and to == CURRENCY_USD:
        return (amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return amount
