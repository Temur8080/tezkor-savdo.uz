def apply_uzbek_admin_labels():
    try:
        from django.contrib.auth.models import User, Group
        User._meta.verbose_name = 'Foydalanuvchi'
        User._meta.verbose_name_plural = 'Foydalanuvchilar'
        Group._meta.verbose_name = 'Guruh'
        Group._meta.verbose_name_plural = 'Guruhlar'
    except Exception:
        pass

    try:
        from django.contrib.auth.apps import AuthConfig
        AuthConfig.verbose_name = 'Foydalanuvchilar'
    except Exception:
        pass

def _unregister(*models):
    from django.contrib import admin

    for model in models:
        if model is None:
            continue
        try:
            if admin.site.is_registered(model):
                admin.site.unregister(model)
        except Exception:
            pass

def prune_unused_admin():

    from django.contrib.auth.models import Group

    _unregister(Group)

    try:
        from admin_interface.models import Theme
        _unregister(Theme)
    except Exception:
        pass

    try:
        from django_q import models as q_models
        _unregister(
            getattr(q_models, 'Success', None),
            getattr(q_models, 'Failure', None),
            getattr(q_models, 'Schedule', None),
            getattr(q_models, 'OrmQ', None),
        )
    except Exception:
        pass

    try:
        from accounts import models as m
        _unregister(
            getattr(m, 'OrderItem', None),
            getattr(m, 'Invoice', None),
            getattr(m, 'Payment', None),
            getattr(m, 'CashPayment', None),
            getattr(m, 'SalesAgent', None),
            getattr(m, 'WarrantyClaims', None),
            getattr(m, 'ReplacementRecord', None),
            getattr(m, 'DefectiveInventory', None),
            getattr(m, 'AuditTrail', None),
        )
    except Exception:
        pass
