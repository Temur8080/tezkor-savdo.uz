from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


ROLE_SALES = 'Sales Agent'
ROLE_CONSULTANT = 'Consultant'
ROLE_MANAGER = 'Manager'


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
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    emp = get_active_employee(user)
    return emp is not None and emp.role == ROLE_MANAGER


def is_consultant(user):
    emp = get_active_employee(user)
    return emp is not None and emp.role == ROLE_CONSULTANT


def can_complete_sale(user):
    if is_app_manager(user):
        return True
    emp = get_active_employee(user)
    return emp is not None and emp.role == ROLE_SALES


def post_login_redirect_name(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'login'
    if user.is_superuser:
        return 'dashboard'
    emp = get_active_employee(user)
    if emp is not None:
        if emp.role == ROLE_MANAGER:
            return 'dashboard'
        return 'pos_terminal'
    return 'login'


def manager_required(view_func):
    @login_required(login_url='login')
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_app_manager(request.user):
            wants_json = (
                'application/json' in (request.content_type or '')
                or 'application/json' in (request.headers.get('Accept') or '')
                or request.headers.get('x-requested-with') == 'XMLHttpRequest'
            )
            if wants_json:
                from django.http import JsonResponse
                return JsonResponse({'error': 'Bu amal faqat menejerlar uchun.'}, status=403)
            messages.error(request, 'Bu bo‘lim faqat menejerlar uchun.')
            return redirect('pos_terminal')
        return view_func(request, *args, **kwargs)
    return _wrapped


class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'

    def test_func(self):
        return is_app_manager(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, 'Bu bo‘lim faqat menejerlar uchun.')
            return redirect('pos_terminal')
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
