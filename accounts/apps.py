from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Tezkor ma’lumotlar'

    def ready(self):
        import accounts.signals
        from accounts.admin_i18n import apply_uzbek_admin_labels, prune_unused_admin
        apply_uzbek_admin_labels()
        prune_unused_admin()

        from django.contrib import admin

        def _superuser_only(request):
            return bool(
                getattr(request, 'user', None)
                and request.user.is_active
                and request.user.is_superuser
            )

        admin.site.has_permission = _superuser_only
