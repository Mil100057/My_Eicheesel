from django.urls import path
from . import views

urlpatterns = [
    path('', views.simulation, name='simulation'),
    path('view_category', views.category, name='view_category'),
    path('view_name', views.name, name="view_name"),
    path('results_list_by_cat', views.results_list_by_cat, name="results_list_by_cat"),
    path('results_list_by_name', views.results_list_by_name, name='results_list_by_name'),
    path('delete-simulation/<int:simulation_id>/', views.delete_simulation, name='delete_simulation'),
    path('delete-account/<str:account_name>/', views.delete_account, name='delete_account'),
    path('delete-category/<str:category_name>/', views.delete_category, name='delete_category'),
    path('export-results-by-cat/', views.export_results_by_cat, name='export_results_by_cat'),
    path('export-results-by-name/', views.export_results_by_name, name='export_results_by_name'),
    path('compare-real-data/', views.compare_real_data, name='compare_real_data'),
    path('compare-real-data/delete/<int:data_id>/', views.delete_real_data, name='delete_real_data'),
    path('inflation-rates/', views.manage_inflation_rates, name='manage_inflation_rates'),
    path('inflation-rates/<int:year>/delete/', views.delete_inflation_rate, name='delete_inflation_rate'),
    path('summary-comparison/', views.summary_comparison, name='summary_comparison'),
    path('portfolios/', views.portfolio_list, name='portfolio_list'),
    path('portfolio/<int:portfolio_id>/', views.portfolio_detail, name='portfolio_detail'),
    path('portfolio/<int:portfolio_id>/add-transaction/', views.add_transaction, name='add_transaction'),
    path('stocks/', views.stock_list, name='stock_list'),
    path('portfolio/<int:portfolio_id>/delete/', views.delete_portfolio, name='delete_portfolio'),
    path('stocks/stock/<int:stock_id>/delete/', views.delete_stock, name='delete_stock'),
    path('transaction/<int:transaction_id>/delete/', views.delete_transaction, name='delete_transaction'),
]
