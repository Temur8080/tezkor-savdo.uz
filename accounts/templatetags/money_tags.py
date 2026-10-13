from django import template
from accounts.money import format_money, CURRENCY_UZS

register = template.Library()


@register.filter(name='money')
def money_filter(value, currency=CURRENCY_UZS):
    return format_money(value, currency)
