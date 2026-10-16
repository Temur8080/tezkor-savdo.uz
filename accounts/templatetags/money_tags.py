from django import template
from accounts.money import format_money, format_qty, CURRENCY_UZS

register = template.Library()


@register.filter(name='money')
def money_filter(value, currency=CURRENCY_UZS):
    return format_money(value, currency)


@register.filter(name='qty')
def qty_filter(value):
    """100.000 → 100, 12.500 → 12.5"""
    return format_qty(value)
