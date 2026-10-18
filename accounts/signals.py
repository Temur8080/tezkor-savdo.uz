from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from .models import Product, AuditTrail, BranchInventory, Order, OrderItem, Employee, WarrantyClaims, \
    Supplier
from .middleware import get_current_user
from .views import employeeProfile

MODELS_TO_AUDIT = {
    Product: [
        'product_name', 'cost_price', 'base_price', 'min_stock_level', 'barcode', 'is_active',
        'sale_active', 'sale_discount_percent', 'sale_starts_at', 'sale_ends_at',
    ],
    BranchInventory: ['quantity'],
    Order: ['order_status', 'total_amount', 'is_active'],
    OrderItem: ['product', 'quantity', 'unit_price', 'cost_price'],
    Employee: ['name', 'role', 'branch', 'is_active', 'email'],
    WarrantyClaims: ['status', 'claim_type', 'cost_impact', 'handled_by', 'resolution_date'],
    Supplier: ['name', 'status', 'contact_person', 'is_active'],
}

def get_employee_from_request():
    user = get_current_user()
    if user and user.is_authenticated:
        return getattr(user, 'employee', None)
    return None

@receiver(pre_save)
def universal_audit_pre_save(sender, instance, **kwargs):
    if sender not in MODELS_TO_AUDIT or not instance.pk:
        return

    try:
        old_obj = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    watch_fields = MODELS_TO_AUDIT.get(sender, [])
    changes = {}
    action_type = 'UPDATE'

    for field in watch_fields:
        if hasattr(instance, field):
            old_val = getattr(old_obj, field)
            new_val = getattr(instance, field)

            if old_val != new_val:
                changes[field] = {
                    'old': str(old_val),
                    'new': str(new_val)
                }

                if field == 'is_active' and new_val is False:
                    action_type = 'DELETE'

    if changes:
        AuditTrail.objects.create(
            user=get_employee_from_request(),
            action=action_type,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            change_log=changes,
        )

@receiver(post_save)
def universal_audit_post_save(sender, instance, created, **kwargs):
    if sender not in MODELS_TO_AUDIT or not created:
        return

    watch_fields = MODELS_TO_AUDIT[sender]
    snapshot = {field: str(getattr(instance, field)) for field in watch_fields}

    obj_name = getattr(instance, 'product_name', getattr(instance, 'name', str(instance)))

    AuditTrail.objects.create(
        user=get_employee_from_request(),
        action='CREATE',
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        change_log={**snapshot, 'info': f"{obj_name} uchun boshlang‘ich yozuv"}
    )

@receiver(post_delete, sender=Product)
def audit_product_delete(sender, instance, **kwargs):
    user = get_current_user()
    employee = None

    if user and user.is_authenticated:
        try: employee = user.employee
        except: employee = None

    AuditTrail.objects.create(
        user=employee,
        content_type=ContentType.objects.get_for_model(instance),
        action='DELETE',
        object_id=instance.id,
        change_log={
            'info': f"{instance.product_name} mahsuloti bazadan butunlay o‘chirildi.",
            'barcode': instance.barcode
        }
    )

@receiver(post_delete)
def universal_audit_post_delete(sender, instance, **kwargs):
    if sender not in MODELS_TO_AUDIT:
        return

    obj_name = getattr(instance, 'product_name', getattr(instance, 'name', str(instance)))

    AuditTrail.objects.create(
        user=get_employee_from_request(),
        action='DELETE',
        content_type=ContentType.objects.get_for_model(instance),
        object_id=instance.pk,
        change_log={'info': f"Butunlay o‘chirildi: {obj_name}"}
    )
