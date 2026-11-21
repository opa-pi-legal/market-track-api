from django.urls import path
from . import views

app_name = 'web'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('', views.dashboard_view, name='dashboard'),
    path('relatorios/csv/', views.export_csv_report_view, name='export_csv'),
    path('alertas/badge/', views.alerts_badge_partial, name='alerts_badge'),
    path('alertas/<int:alert_id>/lido/', views.mark_alert_read_view, name='mark_alert_read'),

    path('grupos/selecionar/<int:group_id>/', views.select_group_view, name='select_group'),
    path('grupos/criar/', views.create_group_view, name='create_group'),
    path('grupos/entrar/', views.join_group_view, name='join_group'),
    path('grupos/convite/', views.create_invite_view, name='create_invite'),

    path('listas/', views.lists_view, name='lists'),
    path('listas/criar/', views.create_list_view, name='create_list'),
    path('listas/<int:list_id>/orcamento/', views.update_list_budget_view, name='update_list_budget'),
    path('listas/<int:list_id>/item/adicionar/', views.add_list_item_view, name='add_list_item'),
    path('listas/item/<int:item_id>/toggle/', views.toggle_list_item_view, name='toggle_list_item'),
    path('listas/item/<int:item_id>/remover/', views.delete_list_item_view, name='delete_list_item'),

    path('comunidade/', views.community_view, name='community'),
    path('comunidade/publicar/', views.publish_offer_view, name='publish_offer'),
    path('comunidade/<int:offer_id>/votar/', views.vote_offer_view, name='vote_offer'),
    path('comunidade/<int:offer_id>/adicionar-lista/', views.add_offer_to_list_view, name='add_offer_to_list'),
    path('comunidade/raio/', views.save_radius_preference_view, name='save_radius'),

    path('catalogo/', views.catalog_view, name='catalog'),
    path('catalogo/mercado/criar/', views.create_market_view, name='create_market'),
    path('catalogo/produto/criar/', views.create_product_view, name='create_product'),

    path('curadoria/', views.moderation_view, name='curadoria'),
    path('moderacao/', views.moderation_view, name='moderation'),
    path('moderacao/oferta/<int:offer_id>/', views.moderate_offer_view, name='moderate_offer'),
    path('moderacao/produto/<int:product_id>/promover/', views.promote_product_view, name='promote_product'),
    path('moderacao/usuario/<int:user_id>/desbanir/', views.unban_user_view, name='unban_user'),
    path('moderacao/mercado/<int:market_id>/geo/', views.update_market_geo_view, name='update_market_geo'),

    path('manutencao/', views.maintenance_view, name='maintenance'),
    path('manutencao/limpar-expiradas/', views.cleanup_expired_offers_view, name='cleanup_expired_offers'),
    path('manutencao/simular-alerta/', views.simulate_alert_view, name='simulate_alert'),
]
