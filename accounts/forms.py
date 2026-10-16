from django import forms
from .models import (
    Employee, Product,
    Supplier, ProductCategory,
)
from .money import CURRENCY_CHOICES, CURRENCY_UZS
from decimal import Decimal

_INPUT = (
    'w-full px-3 py-2 border border-gray-300 rounded-md text-sm '
    'focus:ring-blue-500 focus:border-blue-500 outline-none bg-white'
)

class InventoryEditForm(forms.Form):

    product_name = forms.CharField(
        label='Mahsulot nomi',
        max_length=100,
        widget=forms.TextInput(attrs={'class': _INPUT}),
    )
    barcode = forms.CharField(
        label='Shtrix-kod',
        max_length=100,
        widget=forms.TextInput(attrs={'class': _INPUT}),
    )
    category = forms.ChoiceField(
        label='Kategoriya',
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    new_category = forms.CharField(
        label='Yoki yangi kategoriya',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': _INPUT,
            'placeholder': 'Yangi kategoriya nomi (ixtiyoriy)',
        }),
    )
    supplier = forms.ModelChoiceField(
        label='Yetkazib beruvchi',
        queryset=Supplier.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    cost_currency = forms.ChoiceField(
        label='Tannarx valyutasi',
        choices=CURRENCY_CHOICES,
        initial=CURRENCY_UZS,
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    cost_price = forms.DecimalField(
        label='Tannarx',
        max_digits=14,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': '0'}),
    )
    unit = forms.ChoiceField(
        label='O‘lchov birligi',
        choices=Product.UNIT_CHOICES,
        initial=Product.UNIT_TA,
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    currency = forms.ChoiceField(
        label='Sotish valyutasi',
        choices=CURRENCY_CHOICES,
        initial=CURRENCY_UZS,
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    base_price = forms.DecimalField(
        label='Sotish narxi',
        max_digits=14,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': '0'}),
    )
    min_stock_level = forms.DecimalField(
        label='Minimal zaxira',
        max_digits=12,
        decimal_places=3,
        min_value=0,
        initial=Decimal('3'),
        widget=forms.NumberInput(attrs={'class': _INPUT, 'step': '0.001', 'min': '0'}),
    )
    warranty_days = forms.IntegerField(
        label='Mahsulot kafolati (kun)',
        min_value=0,
        initial=365,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'min': '0'}),
        help_text='Sotib olishdan keyin ta’mirlash muddati',
    )
    replacement_days = forms.IntegerField(
        label='Almashtirish muddati (kun)',
        min_value=0,
        initial=7,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'min': '0'}),
    )
    service_warranty_days = forms.IntegerField(
        label='Ish/xizmat kafolati (kun)',
        min_value=0,
        initial=90,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'min': '0'}),
        help_text='Ta’mirlashdan keyin qo‘shimcha kafolat',
    )
    quantity = forms.DecimalField(
        label='Filial qoldig‘i',
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': _INPUT, 'step': '0.001', 'min': '0'}),
    )
    image = forms.ImageField(
        label='Rasm',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'block w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-3 '
                     'file:rounded-md file:border-0 file:bg-blue-50 file:text-blue-700 '
                     'file:font-semibold hover:file:bg-blue-100',
        }),
    )

    def __init__(self, *args, inventory=None, **kwargs):
        self.inventory = inventory
        self.product = inventory.product if inventory else None
        super().__init__(*args, **kwargs)

        categories = list(
            ProductCategory.objects.filter(is_active=True)
            .order_by('name')
            .values_list('name', flat=True)
        )
        if self.product and self.product.category and self.product.category not in categories:
            categories.insert(0, self.product.category)
        if not categories:
            categories = ['Noutbuk']
        self.fields['category'].choices = [(c, c) for c in categories]

        if self.inventory and not self.is_bound:
            p = self.product
            self.fields['product_name'].initial = p.product_name
            self.fields['barcode'].initial = p.barcode
            self.fields['category'].initial = p.category
            self.fields['supplier'].initial = p.supplier_id
            self.fields['cost_currency'].initial = getattr(p, 'cost_currency', None) or p.currency
            self.fields['cost_price'].initial = p.cost_price
            self.fields['unit'].initial = getattr(p, 'unit', None) or Product.UNIT_TA
            self.fields['currency'].initial = p.currency
            self.fields['base_price'].initial = p.base_price
            self.fields['min_stock_level'].initial = p.min_stock_level
            self.fields['warranty_days'].initial = p.warranty_days
            self.fields['replacement_days'].initial = p.replacement_days
            self.fields['service_warranty_days'].initial = p.service_warranty_days
            self.fields['quantity'].initial = self.inventory.quantity
            if p.image:
                self.fields['image'].initial = p.image

    def clean_barcode(self):
        barcode = (self.cleaned_data.get('barcode') or '').strip()
        if not barcode:
            raise forms.ValidationError('Shtrix-kod majburiy')
        qs = Product.objects.filter(barcode__iexact=barcode)
        if self.product:
            qs = qs.exclude(pk=self.product.pk)
        if qs.exists():
            raise forms.ValidationError('Bu shtrix-kod boshqa mahsulotda band')
        return barcode

    def clean(self):
        cleaned = super().clean()
        new_cat = (cleaned.get('new_category') or '').strip()
        if new_cat:
            cleaned['category'] = new_cat
        if not cleaned.get('category'):
            self.add_error('category', 'Kategoriya tanlang yoki yarating')
        return cleaned

    def save(self):
        if not self.inventory or not self.product:
            raise ValueError('Inventory majburiy')

        data = self.cleaned_data
        category = data['category']
        ProductCategory.objects.get_or_create(name=category, defaults={'is_active': True})

        product = self.product
        product.product_name = data['product_name'].strip()
        product.barcode = data['barcode']
        product.category = category
        product.supplier = data['supplier']
        product.cost_currency = data['cost_currency']
        product.cost_price = data['cost_price']
        product.unit = data['unit']
        product.currency = data['currency']
        product.base_price = data['base_price']
        product.min_stock_level = data['min_stock_level']
        product.warranty_days = data['warranty_days']
        product.replacement_days = data['replacement_days']
        product.service_warranty_days = data['service_warranty_days']

        image_value = data.get('image')
        if image_value is False:
            if product.image:
                product.image.delete(save=False)
            product.image = None
        elif image_value:
            product.image = image_value

        product.save()

        self.inventory.quantity = data['quantity']
        self.inventory.save(update_fields=['quantity'])
        return self.inventory

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['email', 'phone', 'profile_pic']
        exclude = ['user']
        labels = {
            'email': 'Email',
            'phone': 'Telefon',
            'profile_pic': 'Profil rasmi',
        }

class EmployeeAdminForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        label='Login',
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 focus:border-blue-600 focus:ring-0 font-semibold',
            'placeholder': 'Tizimga kirish loginini yarating'
        })
    )
    password = forms.CharField(
        label='Parol',
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 focus:border-blue-600 focus:ring-0 font-semibold',
            'placeholder': 'Vaqtinchalik parol belgilang',
            'autocomplete': 'new-password',
        })
    )

    class Meta:
        model = Employee
        fields = [
            'name',
            'email',
            'phone',
            'branch',
            'role',
            'profile_pic',
        ]
        labels = {
            'name': 'To‘liq ism',
            'email': 'Email',
            'phone': 'Telefon',
            'branch': 'Filial',
            'role': 'Lavozim',
            'profile_pic': 'Profil rasmi',
        }
        widgets = {
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and getattr(instance, 'user_id', None):
            self.fields['username'].initial = instance.user.username
            self.fields['password'].widget.attrs['placeholder'] = 'Bo‘sh qoldiring — parol o‘zgarmaydi'
            self.fields['password'].required = False
        else:
            self.fields['password'].required = True
            self.fields['password'].widget.attrs['placeholder'] = 'Vaqtinchalik parol belgilang'

    def clean_password(self):
        password = self.cleaned_data.get('password') or ''
        instance = getattr(self, 'instance', None)
        if not (instance and instance.pk) and not password:
            raise forms.ValidationError('Parol majburiy.')
        return password
