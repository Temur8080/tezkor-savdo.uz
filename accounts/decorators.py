from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect

from accounts.portal_perms import (
    ROLE_CONSULTANT,
    ROLE_MANAGER,
    ROLE_SALES,
    has_portal_cap,
)


def get_active_employee(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    from accounts.models import Employee
    return (
        Employee.objects
        .filter(user=user, is_active=True)
        .select_related('branch')
        .first()
    )


def is_app_manager(user):
    """Menejer ko‘rinishi / ko‘p filial — portal «multi_branch» huquqi."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return has_portal_cap(user, 'multi_branch')


def is_consultant(user):
    emp = get_active_employee(user)
    return emp is not None and emp.role == ROLE_CONSULTANT


def can_complete_sale(user):
    return has_portal_cap(user, 'sale_complete')


def can_process_return(user):
    return has_portal_cap(user, 'return_process')


def post_login_redirect_name(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'login'
    if user.is_superuser:
        return 'dashboard'
    emp = get_active_employee(user)
    if emp is None:
        return 'login'
    if has_portal_cap(user, 'dashboard'):
        return 'dashboard'
    if has_portal_cap(user, 'pos'):
        return 'pos_terminal'
    return 'login'


def portal_cap_required(code, message=None):
    """View faqat berilgan portal huquqi bo‘lsa ochiladi."""
    err = message or 'Bu bo‘lim uchun ruxsatingiz yo‘q.'

    def decorator(view_func):
        @login_required(login_url='login')
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not has_portal_cap(request.user, code):
                wants_json = (
                    'application/json' in (request.content_type or '')
                    or 'application/json' in (request.headers.get('Accept') or '')
                    or request.headers.get('x-requested-with') == 'XMLHttpRequest'
                )
                if wants_json:
                    from django.http import JsonResponse
                    return JsonResponse({'error': err}, status=403)
                messages.error(request, err)
                dest = post_login_redirect_name(request.user)
                return redirect(dest if dest != 'login' else 'pos_terminal')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def manager_required(view_func):
    """Moslik: eski menejer dekoratori → multi_branch."""
    return portal_cap_required(
        'multi_branch',
        'Bu bo‘lim faqat menejerlar uchun.',
    )(view_func)


class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    portal_cap = 'multi_branch'
    permission_denied_message = 'Bu bo‘lim faqat menejerlar uchun.'

    def test_func(self):
        return has_portal_cap(self.request.user, self.portal_cap)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            dest = post_login_redirect_name(self.request.user)
            return redirect(dest if dest != 'login' else 'pos_terminal')
        return super().handle_no_permission()


class PortalCapRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'
    portal_cap = None
    permission_denied_message = 'Bu bo‘lim uchun ruxsatingiz yo‘q.'

    def test_func(self):
        return bool(self.portal_cap) and has_portal_cap(self.request.user, self.portal_cap)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            dest = post_login_redirect_name(self.request.user)
            return redirect(dest if dest != 'login' else 'pos_terminal')
        return super().handle_no_permission()


def unauthenticated_user(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            dest = post_login_redirect_name(request.user)
            if dest == 'login':
                from django.contrib.auth import logout
                logout(request)
                messages.error(
                    request,
                    'Xodim profili yo‘q. «Xodimlar» orqali filial va lavozim bilan yarating.',
                )
                return redirect('login')
            return redirect(dest)
        return view_func(request, *args, **kwargs)
    return wrapper
