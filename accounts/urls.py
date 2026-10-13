from django.urls import path
from . import views
from django.views.generic import TemplateView
from django.urls import re_path
from django.views.static import serve
from django.conf import settings

urlpatterns = [
    path('', views.home, name='home'),

    path('manage_employee/<int:pk>/', views.manageEmployee, name='manage_employee'),
    path('employee/<int:pk>/block/', views.employee_toggle_block, name='employee_toggle_block'),
    path('employee/<int:pk>/delete/', views.employee_delete, name='employee_delete'),

    path('pos_terminal/', views.posTerminal, name='pos_terminal'),
    path('scan_product/', views.scanProduct, name='scan_product'),
    path('product_scan_info/', views.product_scan_info, name='product_scan_info'),
    path('pos_vat_settings/', views.pos_vat_settings, name='pos_vat_settings'),

    path('login/', views.loginPage, name='login'),
    path('logout/', views.logoutPage, name='logout'),

    path('branch_inventory', views.branchInventory, name='branch_inventory'),
    path('inventory_intake/', views.inventory_intake, name='inventory_intake'),
    path('inventory_lookup/', views.inventory_lookup, name='inventory_lookup'),
    path('inventory_stock_in/', views.inventory_stock_in, name='inventory_stock_in'),
    path('inventory_product_save/', views.inventory_product_save, name='inventory_product_save'),
    path('inventory_add_category/', views.inventory_add_category, name='inventory_add_category'),
    path('inventory_save_rate/', views.inventory_save_rate, name='inventory_save_rate'),
    path('accounts/<int:pk>/inventory_update', views.inventory_update, name='inventory_update'),
    path('employee_profile', views.employeeProfile, name='employee_profile'),
    path('employee_list', views.EmployeeList.as_view(), name='employee_list'),
    path('employee_form', views.EmployeeCreate.as_view(), name='employee_form'),
    path('checkout/cash/', views.checkout_cash, name='checkout_cash'),
    path('checkout/quote/', views.checkout_quote, name='checkout_quote'),
    path('orders/<int:pk>/approve/', views.order_approve, name='order_approve'),
    path('orders/<int:pk>/reject/', views.order_reject, name='order_reject'),
    path('api/customers/lookup/', views.customer_lookup, name='customer_lookup'),
    path('customers/', views.customers_loyalty, name='customers_loyalty'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('settings/', views.app_settings, name='app_settings'),
    path('sales_display/', views.salesDisplay, name='sales_display'),
    path('components/<int:pk>/sales_edit', views.salesUpdateView.as_view(), name='sales_edit'),
    path('accounts/<int:pk>/emp_receipt/', views.emp_receipt, name='emp_receipt'),
    path('admin_reports/', views.admin_reports, name='admin_reports'),
    path('admin_reports/export/', views.admin_reports_export_csv, name='admin_reports_export_csv'),
    path('delete-order/<int:pk>/', views.delete_order, name='delete_order'),
    path('delete-product/<int:pk>/', views.delete_product, name='delete_product'),
    path('warranty/<int:pk>/', views.warranty, name='warranty'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('warrnty_list/', views.warranty_list, name='warranty_list'),
    path('update_claim_status/<int:pk>/', views.update_claim_status, name='update_claim_status'),
    path('audit_logs/', views.audit_logs, name='audit_logs'),
    path('debtors/', views.debtors_list, name='debtors_list'),
    path('debtors/<int:pk>/pay/', views.debt_pay, name='debt_pay'),
    path('debtors/export/', views.debtors_export_csv, name='debtors_export_csv'),
    path('expenses/', views.expenses_list, name='expenses_list'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('sales_display/export/', views.export_sales_csv, name='export_sales_csv'),
    path('branch_inventory/export/', views.export_branch_inventory_csv, name='export_branch_inventory_csv'),
    path('employee_list/export_employee_csv/', views.employee_list_export_csv, name='employee_list_export_csv'),
    path('warrnty_list/export_warranty_list/', views.warranty_list_export_csv, name='warranty_list_export_csv'),
    path('audit_logs/export_audit_logs/', views.audit_logs_export_csv, name='audit_logs_export_csv'),
    path('google439ec38d3e46cf95.html', TemplateView.as_view(template_name='google439ec38d3e46cf95.html')),
]

if not settings.DEBUG:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]
