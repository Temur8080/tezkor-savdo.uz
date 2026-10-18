from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q

from .models import *
from .admin_branch import (
    BranchScopedAdminMixin,
    get_admin_organizations,
)

admin.site.site_header = "Tezkor boshqaruvi"
admin.site.site_title = "Tezkor POS"
admin.site.index_title = "Boshqaruv paneli"

class UserCreateWithOrgForm(UserCreationForm):

    full_name = forms.CharField(
        label='To‘liq ism',
        max_length=100,
        help_text='Portalda ko‘rinadigan ism',
    )
    branch = forms.ModelChoiceField(
        label='Filial',
        queryset=Branch.objects.none(),
        help_text='Xodim shu filialga biriktiriladi',
    )
    role = forms.ChoiceField(
        label='Lavozim',
        choices=Employee.ROLE_CHOICES,
        initial='Manager',
        help_text='Menejer = /dashboard/ va barcha funksiyalar. /admin/ ochilmaydi.',
    )

    class Meta:
        model = User
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        qs = Branch.objects.filter(is_active=True).select_related('organization').order_by('name')
        if request is not None:
            orgs = get_admin_organizations(request)
            if orgs is not None and orgs is not False:
                qs = qs.filter(organization__in=orgs)
            elif orgs is False:
                qs = qs.none()
        self.fields['branch'].queryset = qs
        if qs.count() == 1:
            self.fields['branch'].initial = qs.first()

    def save(self, commit=True):
        user = super().save(commit=False)

        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
            StaffAccess.objects.get_or_create(user=user)
            Employee.objects.update_or_create(
                user=user,
                defaults={
                    'name': self.cleaned_data.get('full_name') or user.username,
                    'role': self.cleaned_data.get('role') or 'Manager',
                    'branch': self.cleaned_data['branch'],
                    'is_active': True,
                    'email': user.email or '',
                },
            )
        return user

class StaffAccessInline(admin.StackedInline):
    model = StaffAccess
    can_delete = False
    max_num = 1
    min_num = 1
    extra = 0
    filter_horizontal = ('viloyats', 'districts', 'organizations', 'branches')
    verbose_name = 'Hudud ruxsatlari'
    verbose_name_plural = 'Hudud ruxsatlari (chapdan o‘ngga o‘tkazing)'
    fields = ('viloyats', 'districts', 'organizations', 'branches')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        orgs = get_admin_organizations(request)
        scoped = orgs is not None and orgs is not False

        class ScopedFormset(formset):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                help_txt = (
                    'Chap — mavjudlar. O‘ng — biriktirilganlar. '
                    'Viloyat / tuman / tashkilot / filial: o‘ngdagilarini admin ko‘radi.'
                )
                for form in self.forms:
                    v = form.fields.get('viloyats')
                    d = form.fields.get('districts')
                    o = form.fields.get('organizations')
                    b = form.fields.get('branches')
                    if orgs is None:
                        if v:
                            v.queryset = Viloyat.objects.filter(is_active=True).order_by('name')
                        if d:
                            d.queryset = District.objects.filter(is_active=True).select_related('viloyat').order_by('name')
                        if o:
                            o.queryset = Organization.objects.filter(is_active=True).order_by('name')
                        if b:
                            b.queryset = Branch.objects.filter(is_active=True).select_related('organization').order_by('name')
                    elif scoped:
                        if v:
                            v.queryset = Viloyat.objects.filter(
                                pk__in=orgs.values_list('district__viloyat_id', flat=True)
                            ).distinct().order_by('name')
                        if d:
                            d.queryset = District.objects.filter(
                                pk__in=orgs.exclude(district_id=None).values_list('district_id', flat=True)
                            ).distinct().order_by('name')
                        if o:
                            o.queryset = orgs.order_by('name')
                        if b:
                            b.queryset = Branch.objects.filter(
                                organization__in=orgs, is_active=True
                            ).order_by('name')
                    else:
                        for f in (v, d, o, b):
                            if f:
                                f.queryset = f.queryset.none()
                    for f in (v, d, o, b):
                        if f:
                            f.help_text = help_txt

        return ScopedFormset

class TezkorUserAdmin(DjangoUserAdmin):
    add_form = UserCreateWithOrgForm
    inlines = [StaffAccessInline]
    list_display = (
        'username', 'get_employee_name', 'get_organizations', 'get_branch',
        'is_staff', 'is_active', 'is_superuser',
    )
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'staff_access__organizations', 'employee__branch')
    search_fields = ('username', 'email', 'employee__name', 'employee__branch__name')
    ordering = ('username',)

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'full_name', 'branch', 'role'),
            'description': (
                'Bu foydalanuvchi https://tezkor-savdo.uz portaliga kiradi (dashboard, xodimlar, ombor…). '
                'Superuser yoqilmasa /admin/ ochilmaydi — bu to‘g‘ri.'
            ),
        }),
    )

    @admin.display(description='Ism', ordering='employee__name')
    def get_employee_name(self, obj):
        emp = getattr(obj, 'employee', None)
        return emp.name if emp else '—'

    @admin.display(description='Hudud / tashkilot')
    def get_organizations(self, obj):
        access = getattr(obj, 'staff_access', None)
        if access:
            parts = []
            v = access.viloyats.count()
            d = access.districts.count()
            o = access.organizations.count()
            b = access.branches.count()
            if v:
                parts.append(f'{v} viloyat')
            if d:
                parts.append(f'{d} tuman')
            if o:
                names = list(access.organizations.values_list('name', flat=True)[:3])
                extra = o - len(names)
                text = ', '.join(names) + ('…' if extra > 0 else '')
                parts.append(text)
            if b:
                parts.append(f'{b} filial')
            if parts:
                return ' · '.join(parts)
        emp = getattr(obj, 'employee', None)
        if emp and emp.branch_id and emp.branch.organization_id:
            return emp.branch.organization.name
        return '—'

    @admin.display(description='Filial', ordering='employee__branch__name')
    def get_branch(self, obj):
        emp = getattr(obj, 'employee', None)
        return emp.branch.name if emp and emp.branch_id else '—'

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            'employee__branch__organization', 'staff_access'
        ).prefetch_related('staff_access__organizations')
        orgs = get_admin_organizations(request)
        if orgs is None:
            return qs
        if orgs is False:
            return qs.none()
        return qs.filter(
            Q(staff_access__organizations__in=orgs)
            | Q(employee__branch__organization__in=orgs)
        ).distinct()

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [
                f for f in filters
                if f not in ('staff_access__organizations', 'is_superuser')
            ]
        return filters

    def get_form(self, request, obj=None, **kwargs):
        defaults = {}
        if obj is None:
            base = self.add_form

            class BoundCreateForm(base):
                def __init__(self, *a, **kw):
                    kw['request'] = request
                    super().__init__(*a, **kw)

            defaults['form'] = BoundCreateForm
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_inline_instances(self, request, obj=None):

        return super().get_inline_instances(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        user = form.instance
        StaffAccess.objects.get_or_create(user=user)

        if not Employee.objects.filter(user=user).exists():
            branch = Branch.objects.filter(is_active=True).order_by('id').first()
            if branch:
                Employee.objects.create(
                    user=user,
                    name=user.get_full_name() or user.username,
                    role='Manager',
                    branch=branch,
                    is_active=True,
                    email=user.email or '',
                )

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return self._user_in_org(request, obj)

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return self._user_in_org(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj and obj.is_superuser and not request.user.is_superuser:
            return False
        return self._user_in_org(request, obj)

    def _user_in_org(self, request, obj):
        if obj is None:
            return True
        orgs = get_admin_organizations(request)
        if orgs is None:
            return True
        if orgs is False:
            return False
        allowed = set(orgs.values_list('id', flat=True))
        access = getattr(obj, 'staff_access', None)
        if access and access.organizations.filter(id__in=allowed).exists():
            return True
        emp = getattr(obj, 'employee', None)
        return bool(emp and emp.branch_id and emp.branch.organization_id in allowed)

admin.site.unregister(User)
admin.site.register(User, TezkorUserAdmin)

@admin.register(Viloyat)
class ViloyatAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)
    branch_lookup = 'viloyat'
    ordering = ('name',)

@admin.register(District)
class DistrictAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'kind', 'viloyat', 'is_active')
    search_fields = ('name', 'viloyat__name')
    list_filter = ('kind', 'viloyat', 'is_active')
    list_select_related = ('viloyat',)
    branch_lookup = 'district'
    ordering = ('viloyat__name', 'name')

@admin.register(Organization)
class OrganizationAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'brand_name', 'district', 'phone', 'is_active')
    search_fields = ('name', 'brand_name')
    list_filter = ('is_active', 'district__viloyat', 'district')
    list_select_related = ('district__viloyat',)
    branch_lookup = 'branches'
    fields = ('district', 'name', 'brand_name', 'logo', 'phone', 'address', 'is_active')

    def has_add_permission(self, request):
        orgs = get_admin_organizations(request)
        if orgs is False:
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_deleted_objects(self, objs, request):

        objs = list(objs)
        deleted = [f'«{o}» arxivlanadi (filiallar saqlanadi, faol emas)' for o in objs]
        model_count = {Organization._meta.verbose_name: len(objs)}
        return deleted, model_count, set(), []

    def delete_model(self, request, obj):
        obj.delete()
        self.message_user(
            request,
            f'«{obj}» arxivlandi (o‘chirilmadi). Filiallar faolsizlantirildi.',
        )

    def delete_queryset(self, request, queryset):
        count = queryset.count()
        for obj in queryset:
            obj.delete()
        self.message_user(request, f'{count} ta tashkilot arxivlandi.')

@admin.register(Branch)
class BranchAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'organization', 'phone_number', 'address', 'is_active')
    search_fields = ('name', 'organization__name')
    list_filter = ('organization', 'organization__district__viloyat', 'is_active')
    list_select_related = ('organization__district__viloyat',)
    branch_lookup = 'id'

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [f for f in filters if f != 'organization']
        return filters

    def has_add_permission(self, request):
        orgs = get_admin_organizations(request)
        if orgs is False:
            return False
        return super().has_add_permission(request)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        if get_admin_organizations(request) is not None:
            actions.pop('restore_branch', None)
            actions.pop('archive_branch', None)
        return actions

    actions = ['restore_branch', 'archive_branch']

    @admin.action(description='Tanlangan filialni tiklash')
    def restore_branch(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} ta filial tiklandi.")

    @admin.action(description='Tanlangan filiallarni arxivlash')
    def archive_branch(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} ta filial arxivlandi.")

@admin.register(Employee)
class EmployeeAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'role', 'branch', 'hire_date', 'is_active')
    list_filter = ('role', 'branch', 'is_active')
    search_fields = ('name',)
    ordering = ('-is_active', 'name')
    branch_lookup = 'branch'

    actions = ['archive_employee', 'restore_employee']

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [f for f in filters if f != 'branch']
        return filters

    @admin.action(description='Tanlangan xodimni tiklash')
    def restore_employee(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} ta xodim tiklandi.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    @admin.action(description='Tanlangan xodimni arxivlash')
    def archive_employee(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} ta xodim arxivlandi.")

@admin.register(PriceTier)
class PriceTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'discount_percent', 'is_active')
    list_editable = ('discount_percent', 'is_active')
    list_display_links = ('name',)
    search_fields = ('name', 'kind')
    readonly_fields = ('kind', 'code')
    fields = ('kind', 'name', 'discount_percent', 'is_active')

@admin.register(Customer)
class CustomerAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'name', 'phone', 'customer_type', 'price_tier',
        'bonus_discount_percent', 'email', 'date_created', 'is_active',
    )
    list_filter = ('customer_type', 'is_active', 'price_tier')
    search_fields = ('name', 'phone', 'email')
    list_editable = ('customer_type', 'bonus_discount_percent')
    autocomplete_fields = ('price_tier',)
    branch_lookup = 'order__branch'
    fields = (
        'name', 'phone', 'email', 'address',
        'customer_type', 'price_tier', 'bonus_discount_percent',
        'notes', 'is_active',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('price_tier')

    def get_actions(self, request):
        actions = super().get_actions(request)
        if actions and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return request.user.is_staff

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    search_fields = ('name',)
    list_filter = ('is_active',)

@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'usd_to_uzs', 'vat_enabled', 'vat_percent',
        'pos_secret_code', 'pos_secret_discount_percent',
        'pos_secret_markup_code', 'pos_secret_markup_percent',
        'theme_mode', 'updated_at',
    )
    fields = (
        'usd_to_uzs', 'vat_enabled', 'vat_percent',
        'pos_secret_code', 'pos_secret_discount_percent',
        'pos_secret_markup_code', 'pos_secret_markup_percent',
        'theme_mode', 'theme_day_start', 'theme_night_start', 'updated_at',
    )
    readonly_fields = ('updated_at',)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser and not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Product)
class ProductAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'supplier', 'product_name', 'category', 'unit', 'cost_currency', 'cost_price',
        'currency', 'base_price', 'sale_active', 'sale_discount_percent',
        'warranty_days', 'replacement_days', 'service_warranty_days', 'barcode', 'is_active',
    )
    search_fields = ('product_name', 'barcode')
    list_filter = ('is_active', 'sale_active', 'supplier', 'category', 'unit', 'currency', 'cost_currency',)
    list_select_related = ('supplier',)
    ordering = ('category', 'product_name')
    branch_lookup = 'branchinventory__branch'
    fieldsets = (
        (None, {
            'fields': (
                'supplier', 'product_name', 'category', 'barcode', 'unit',
                'cost_currency', 'cost_price',
                'currency', 'base_price',
                'min_stock_level', 'image', 'is_active',
            ),
        }),
        ('Mahsulot skidkasi', {
            'fields': ('sale_active', 'sale_discount_percent', 'sale_starts_at', 'sale_ends_at'),
        }),
        ('Kafolat muddatlari', {
            'fields': ('warranty_days', 'replacement_days', 'service_warranty_days'),
        }),
    )

    actions = ['archive_products', 'restore_product']

    @admin.action(description='Tanlangan mahsulotni tiklash')
    def restore_product(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} ta mahsulot tiklandi.")

    @admin.action(description='Tanlangan mahsulotlarni arxivlash')
    def archive_products(self, request, queryset):
        for product in queryset:
            product.soft_delete()
        self.message_user(request, f"{queryset.count()} ta mahsulot arxivlandi.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if actions and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

@admin.register(BranchInventory)
class BranchInventoryAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('branch', 'product', 'product__category', 'quantity_display', 'get_is_active')
    list_filter = ('branch', 'product', 'product__category')
    date_hierarchy = 'date_added'
    branch_lookup = 'branch'

    @admin.display(description='Miqdor', ordering='quantity')
    def quantity_display(self, obj):
        from .money import format_qty
        return format_qty(obj.quantity)

    @admin.display(description='Mahsulot faol')
    def get_is_active(self, obj):
        return obj.product.is_active

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(
            product__is_active=True,
            branch__is_active=True
        )

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [f for f in filters if f != 'branch']
        return filters

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(SaleReturn)
class SaleReturnAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'receipt_number', 'order', 'branch', 'employee', 'total_amount',
        'cash_refunded', 'debt_reduced', 'return_date', 'status',
    )
    list_filter = ('status', 'branch', 'return_date')
    search_fields = ('receipt_number', 'order__id', 'customer__name')
    branch_lookup = 'branch'
    readonly_fields = ('return_date', 'receipt_number')


@admin.register(SaleReturnItem)
class SaleReturnItemAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('sale_return', 'product', 'quantity', 'unit_price', 'line_total')
    search_fields = ('product__product_name', 'sale_return__receipt_number')
    branch_lookup = 'sale_return__branch'


@admin.register(Order)
class OrderAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'customer', 'employee', 'branch', 'order_date', 'total_amount', 'order_status', 'payment_method', 'is_active')
    list_filter = ('is_active', 'order_status', 'branch', 'payment_method')
    search_fields = ('customer__name', 'id')
    branch_lookup = 'branch'

    actions = ['archive_orders', 'restore_orders']

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [f for f in filters if f != 'branch']
        return filters

    @admin.action(description='Tanlangan buyurtmani arxivlash')
    def archive_orders(self, request, queryset):
        count = 0
        for order in queryset:
            order.soft_delete()
            count += 1
        self.message_user(request, f"{count} ta buyurtma arxivlandi.")

    @admin.action(description='Tanlangan buyurtmalarni tiklash')
    def restore_orders(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} ta buyurtma tiklandi.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if actions and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

@admin.register(Supplier)
class SupplierAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'contract_start', 'contract_period', 'contract_status', 'contract_expiration', 'is_active')
    search_fields = ('name', 'contact_person')
    list_filter = ('status', 'is_active')
    branch_lookup = 'product__branchinventory__branch'

    actions = ['archive_products', 'restore_product']

    @admin.action(description='Tanlangan mahsulotni tiklash')
    def restore_product(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} ta mahsulot tiklandi.")

    @admin.action(description='Tanlangan mahsulotlarni arxivlash')
    def archive_products(self, request, queryset):
        for product in queryset:
            product.soft_delete()
        self.message_user(request, f"{queryset.count()} ta mahsulot arxivlandi.")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if actions and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

@admin.register(CustomerDebt)
class CustomerDebtAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'id', 'customer', 'branch', 'currency', 'original_amount',
        'paid_amount', 'remaining_balance', 'status', 'created_at',
    )
    list_filter = ('status', 'currency', 'branch')
    search_fields = ('customer__name', 'customer__phone', 'note')
    readonly_fields = ('created_at', 'updated_at')
    branch_lookup = 'branch'

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if get_admin_organizations(request) is not None:
            filters = [f for f in filters if f != 'branch']
        return filters

@admin.register(DebtPayment)
class DebtPaymentAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'debt', 'amount', 'received_by', 'paid_at')
    list_filter = ('paid_at',)
    search_fields = ('debt__customer__name', 'note')
    readonly_fields = ('paid_at',)
    branch_lookup = 'debt__branch'

_DIRECTORY_ORDER = {
    'viloyat': 1,
    'district': 2,
    'organization': 3,
    'branch': 4,
}
_original_get_app_list = admin.site.get_app_list

def _tezkor_get_app_list(request, app_label=None):
    app_list = _original_get_app_list(request, app_label=app_label)
    directory = []
    for app in app_list:
        remaining = []
        for model in app.get('models', []):
            key = (model.get('object_name') or '').lower()
            if key in _DIRECTORY_ORDER:
                directory.append((_DIRECTORY_ORDER[key], model))
            else:
                remaining.append(model)
        app['models'] = remaining

    app_list = [app for app in app_list if app.get('models')]
    if directory:
        directory.sort(key=lambda item: item[0])
        app_list.insert(0, {
            'name': 'Hudud va tashkilotlar',
            'app_label': 'directory',
            'app_url': '/admin/',
            'has_module_perms': True,
            'models': [model for _, model in directory],
        })
    return app_list

admin.site.get_app_list = _tezkor_get_app_list
