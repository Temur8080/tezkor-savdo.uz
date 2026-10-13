from django import forms
import django_filters
from .models import *
from django.db.models import F

class installmentFilter(django_filters.FilterSet):
    employee_name = django_filters.CharFilter(field_name='order__employee__name', lookup_expr='icontains', label='Xodim', widget=forms.TextInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
        'placeholder': 'Xodim ismini qidirish...'
    }))

    customer_name = django_filters.CharFilter(field_name='order__customer__name', lookup_expr='icontains', label='Mijoz', widget=forms.TextInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
        'placeholder': 'Mijoz ismini qidirish...'
    }))

    order_date = django_filters.DateFilter(field_name='order__order_date', lookup_expr='exact', label='Buyurtma sanasi', widget=forms.DateInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none', 'type' : 'date',
        'placeholder': 'Buyurtma sanasini qidirish...'
    }))

    branch = django_filters.ModelChoiceFilter(field_name='order__branch', to_field_name='id',
        queryset=Branch.objects.all(),
        label='Filial',
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white',
        })
    )

    class Meta:
        model = OrderItem
        fields = ['order__customer', 'order__employee', 'order__branch']

class salesFilter(django_filters.FilterSet):
    employee_name = django_filters.CharFilter(field_name='order__employee__name', lookup_expr='icontains', label='Xodim', widget=forms.TextInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
        'placeholder': 'Xodim ismini qidirish...'
    }))

    customer_name = django_filters.CharFilter(field_name='order__customer__name', lookup_expr='icontains', label='Mijoz', widget=forms.TextInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
        'placeholder': 'Mijoz ismini qidirish...'
    }))

    order_date = django_filters.DateFilter(field_name='order__order_date', lookup_expr='exact', label='Buyurtma sanasi', widget=forms.DateInput(attrs={
        'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none', 'type' : 'date',
        'placeholder': 'Buyurtma sanasini qidirish...'
    }))

    branch = django_filters.ModelChoiceFilter(field_name='order__branch', to_field_name='id',
        queryset=Branch.objects.all(),
        label='Filial',
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white',
        })
    )

    class Meta:
        model = Order
        fields = ['customer', 'employee', 'branch']


class InventoryFilter(django_filters.FilterSet):
    STOCK_CHOICES = (
    ('low', 'Kam qoldiq'),
    ('out', 'Tugagan'),
    ('in stock', 'Mavjud'),
    )

    stock_status = django_filters.ChoiceFilter(choices=STOCK_CHOICES, method='filter_stock_status', label='Ombor holati', widget=forms.Select(attrs={'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white',}))

    def filter_stock_status(self, queryset, name, value):
        if value == 'low':
            return queryset.filter(quantity__gt=0, quantity__lte=F('product__min_stock_level'))
        elif value == 'out':
            return queryset.filter(quantity__lte=0)
        elif value == 'in stock':
            return queryset.filter(quantity__gt=F('product__min_stock_level'))
        return queryset


    product__product_name = django_filters.CharFilter(field_name='product__product_name', lookup_expr='icontains', label='Mahsulot nomi', widget=forms.TextInput(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
            'placeholder': 'Mahsulot nomini qidirish...'
        }))


    product__barcode = django_filters.CharFilter(field_name='product__barcode', lookup_expr='icontains', label='Shtrix-kod',         widget=forms.TextInput(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none',
            'placeholder': 'Shtrix-kodni qidirish...'
        }))

    branch = django_filters.ModelChoiceFilter(
        queryset=Branch.objects.all(),
        label='Filial',
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white',
        })
    )

    product = django_filters.ModelChoiceFilter(
        queryset=Product.objects.filter(is_active=True),
        label='Mahsulot',
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white'
        })
    )

    class Meta:
        model = BranchInventory
        fields = ['branch','product']
