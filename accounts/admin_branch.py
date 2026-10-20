def get_admin_organizations(request):
    """None = superuser (cheklovsiz). False = ruxsat yo‘q. QuerySet = ruxsat etilgan tashkilotlar."""
    from .models import Organization, Branch

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return None

    branch_ids = get_admin_branch_ids(request)
    if branch_ids is False:
        return False
    if branch_ids is None:
        return None
    org_ids = set(
        Branch.objects.filter(pk__in=branch_ids, organization__isnull=False)
        .values_list('organization_id', flat=True)
    )
    if not org_ids:
        return False
    return Organization.objects.filter(pk__in=org_ids, is_active=True)


def get_admin_branch_ids(request):
    """
    None = cheklovsiz (superuser).
    False = hech narsa.
    list[int] = ruxsat etilgan filiallar.

    StaffAccess: viloyat ∪ tuman ∪ tashkilot ∪ filiallar (hammasi hisobga olinadi).
    Bo‘sh bo‘lsa — xodimning employee.branch (kassa «uy» filiali).
    """
    from .models import Organization, Branch

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return None

    access = getattr(user, 'staff_access', None)
    branch_ids = set()

    if access is not None:
        if access.branches.exists():
            branch_ids.update(
                access.branches.filter(is_active=True).values_list('id', flat=True)
            )

        org_ids = set()
        if access.organizations.exists():
            org_ids.update(
                access.organizations.filter(is_active=True).values_list('id', flat=True)
            )
        if access.districts.exists():
            org_ids.update(
                Organization.objects.filter(
                    is_active=True, district__in=access.districts.all()
                ).values_list('id', flat=True)
            )
        if access.viloyats.exists():
            org_ids.update(
                Organization.objects.filter(
                    is_active=True, district__viloyat__in=access.viloyats.all()
                ).values_list('id', flat=True)
            )
        if org_ids:
            branch_ids.update(
                Branch.objects.filter(organization_id__in=org_ids, is_active=True)
                .values_list('id', flat=True)
            )

    if branch_ids:
        return list(branch_ids)

    employee = getattr(user, 'employee', None)
    if employee and employee.branch_id:
        if getattr(employee.branch, 'is_active', True):
            return [employee.branch_id]
    return False


def scope_queryset_by_branch(qs, request, field='branch_id'):
    """Portal/admin querysetni StaffAccess filialiga qisqartirish."""
    branch_ids = get_admin_branch_ids(request)
    if branch_ids is None:
        return qs
    if branch_ids is False:
        return qs.none()
    if field.endswith('_id'):
        return qs.filter(**{f'{field}__in': branch_ids})
    return qs.filter(**{f'{field}_id__in': branch_ids})


def user_can_access_branch(request, branch_id):
    """Filialga ruxsat bormi."""
    if not branch_id:
        return False
    allowed = get_admin_branch_ids(request)
    if allowed is None:
        return True
    if allowed is False:
        return False
    return int(branch_id) in {int(x) for x in allowed}


def get_admin_branch(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return None
    employee = getattr(user, 'employee', None)
    if employee and employee.branch_id and user_can_access_branch(request, employee.branch_id):
        return employee.branch
    branch_ids = get_admin_branch_ids(request)
    if branch_ids is None:
        return None
    if branch_ids is False or not branch_ids:
        return False
    from .models import Branch
    return Branch.objects.filter(pk=branch_ids[0]).first() or False


class BranchScopedAdminMixin:

    branch_lookup = 'branch'

    def _scoped_orgs(self, request):
        return get_admin_organizations(request)

    def _scoped_branch_ids(self, request):
        return get_admin_branch_ids(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        orgs = self._scoped_orgs(request)
        if orgs is None:
            return qs
        if orgs is False or not self.branch_lookup:
            return qs.none()

        lookup = self.branch_lookup
        branch_ids = self._scoped_branch_ids(request)

        if lookup in ('id', 'pk'):

            if branch_ids is False:
                return qs.none()
            if branch_ids is not None:
                return qs.filter(pk__in=branch_ids)
            return qs.filter(organization__in=orgs)

        if lookup == 'branches':

            return qs.filter(pk__in=orgs.values('pk'))

        if lookup == 'viloyat':

            return qs.filter(
                pk__in=orgs.exclude(district__viloyat_id=None).values_list('district__viloyat_id', flat=True)
            ).distinct()

        if lookup == 'district':
            return qs.filter(
                pk__in=orgs.exclude(district_id=None).values_list('district_id', flat=True)
            ).distinct()

        if branch_ids is not None and branch_ids is not False:
            if lookup == 'branch':
                return qs.filter(branch_id__in=branch_ids).distinct()
            if lookup.endswith('__branch'):
                return qs.filter(**{f'{lookup}_id__in': branch_ids}).distinct()

            return qs.filter(**{f'{lookup}_id__in': branch_ids}).distinct()

        if lookup == 'branch':
            return qs.filter(branch__organization__in=orgs).distinct()
        if lookup.endswith('__branch'):
            return qs.filter(**{f'{lookup}__organization__in': orgs}).distinct()
        if lookup in ('organization',) or lookup.endswith('__organization'):
            return qs.filter(**{f'{lookup}__in': orgs}).distinct()
        return qs.filter(**{f'{lookup}__organization__in': orgs}).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        orgs = self._scoped_orgs(request)
        if orgs is not None and orgs is not False:
            from .models import (
                Branch, Employee, Product, Order, Customer, CustomerDebt,
                Organization, Viloyat, District,
            )

            branch_ids = self._scoped_branch_ids(request)

            if db_field.name == 'viloyat':
                kwargs['queryset'] = Viloyat.objects.filter(
                    pk__in=orgs.values_list('district__viloyat_id', flat=True)
                ).distinct()
            elif db_field.name == 'district':
                kwargs['queryset'] = District.objects.filter(
                    pk__in=orgs.exclude(district_id=None).values_list('district_id', flat=True)
                ).distinct()
            elif db_field.name == 'organization':
                kwargs['queryset'] = Organization.objects.filter(pk__in=orgs.values('pk'))
            elif db_field.name == 'branch':
                if branch_ids is not None and branch_ids is not False:
                    kwargs['queryset'] = Branch.objects.filter(pk__in=branch_ids)
                else:
                    kwargs['queryset'] = Branch.objects.filter(organization__in=orgs, is_active=True)
            elif db_field.name == 'employee':
                if branch_ids is not None and branch_ids is not False:
                    kwargs['queryset'] = Employee.objects.filter(branch_id__in=branch_ids)
                else:
                    kwargs['queryset'] = Employee.objects.filter(branch__organization__in=orgs)
            elif db_field.name in ('created_by', 'received_by', 'handled_by', 'issued_by'):
                if branch_ids is not None and branch_ids is not False:
                    kwargs['queryset'] = Employee.objects.filter(branch_id__in=branch_ids)
                else:
                    kwargs['queryset'] = Employee.objects.filter(branch__organization__in=orgs)
            elif db_field.name == 'product':
                kwargs['queryset'] = Product.objects.filter(
                    branchinventory__branch__organization__in=orgs, is_active=True
                ).distinct()
            elif db_field.name == 'order':
                if branch_ids is not None and branch_ids is not False:
                    kwargs['queryset'] = Order.objects.filter(branch_id__in=branch_ids)
                else:
                    kwargs['queryset'] = Order.objects.filter(branch__organization__in=orgs)
            elif db_field.name == 'customer':
                kwargs['queryset'] = Customer.objects.filter(
                    order__branch__organization__in=orgs
                ).distinct()
            elif db_field.name == 'debt':
                kwargs['queryset'] = CustomerDebt.objects.filter(branch__organization__in=orgs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        orgs = self._scoped_orgs(request)
        branch = get_admin_branch(request)
        if orgs is not None and orgs is not False and hasattr(obj, 'organization_id'):
            allowed_ids = set(orgs.values_list('id', flat=True))
            if not change and not getattr(obj, 'organization_id', None):
                obj.organization = orgs.order_by('id').first()
            elif obj.organization_id and obj.organization_id not in allowed_ids:
                obj.organization = orgs.order_by('id').first()
        if branch and branch is not False and hasattr(obj, 'branch_id'):
            if not change and not getattr(obj, 'branch_id', None):
                obj.branch = branch
            elif obj.branch_id and orgs is not None and orgs is not False:
                allowed_ids = set(orgs.values_list('id', flat=True))
                if obj.branch.organization_id not in allowed_ids:
                    obj.branch = branch
        super().save_model(request, obj, form, change)

    def _object_in_scope(self, request, obj):
        if obj is None:
            return True
        orgs = self._scoped_orgs(request)
        if orgs is None:
            return True
        if orgs is False:
            return False
        try:
            return self.get_queryset(request).filter(pk=obj.pk).exists()
        except Exception:
            return False

    def has_view_permission(self, request, obj=None):
        allowed = super().has_view_permission(request, obj)
        if not allowed:
            return False
        return self._object_in_scope(request, obj)

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not allowed:
            return False
        return self._object_in_scope(request, obj)

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if not allowed:
            return False
        return self._object_in_scope(request, obj)
