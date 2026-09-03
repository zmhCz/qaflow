from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BusinessAccountViewSet, BusinessLoadTaskViewSet, DataFactoryViewSet

router = DefaultRouter()
router.register(r'', DataFactoryViewSet, basename='data-factory')

account_pool_list = BusinessAccountViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
account_pool_detail = BusinessAccountViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
account_pool_options = BusinessAccountViewSet.as_view({'get': 'options'})
account_pool_statistics = BusinessAccountViewSet.as_view({'get': 'statistics'})
account_pool_bulk_import = BusinessAccountViewSet.as_view({'post': 'bulk_import'})
account_pool_allocate = BusinessAccountViewSet.as_view({'post': 'allocate'})
account_pool_release = BusinessAccountViewSet.as_view({'post': 'release'})
account_pool_release_one = BusinessAccountViewSet.as_view({'post': 'release_one'})

business_load_task_list = BusinessLoadTaskViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
business_load_task_detail = BusinessLoadTaskViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
business_load_task_options = BusinessLoadTaskViewSet.as_view({'get': 'options'})
business_load_community_candidates = BusinessLoadTaskViewSet.as_view({'get': 'community_candidates'})
business_load_room_list_preview = BusinessLoadTaskViewSet.as_view({'post': 'room_list_preview'})
business_load_task_precheck = BusinessLoadTaskViewSet.as_view({'post': 'precheck'})
business_load_task_start = BusinessLoadTaskViewSet.as_view({'post': 'start'})
business_load_task_trial_run = BusinessLoadTaskViewSet.as_view({'post': 'trial_run'})
business_load_task_stop = BusinessLoadTaskViewSet.as_view({'post': 'stop'})
business_load_task_team_room_republish = BusinessLoadTaskViewSet.as_view({'post': 'team_room_republish'})
business_load_task_team_room_cancel = BusinessLoadTaskViewSet.as_view({'post': 'team_room_cancel'})

urlpatterns = [
    path('account-pool/', account_pool_list, name='account-pool-list'),
    path('account-pool/options/', account_pool_options, name='account-pool-options'),
    path('account-pool/statistics/', account_pool_statistics, name='account-pool-statistics'),
    path('account-pool/bulk-import/', account_pool_bulk_import, name='account-pool-bulk-import'),
    path('account-pool/allocate/', account_pool_allocate, name='account-pool-allocate'),
    path('account-pool/release/', account_pool_release, name='account-pool-release'),
    path('account-pool/<int:pk>/', account_pool_detail, name='account-pool-detail'),
    path('account-pool/<int:pk>/release/', account_pool_release_one, name='account-pool-release-one'),
    path('business-load/tasks/', business_load_task_list, name='business-load-task-list'),
    path('business-load/tasks/options/', business_load_task_options, name='business-load-task-options'),
    path('business-load/tasks/community-candidates/', business_load_community_candidates, name='business-load-community-candidates'),
    path('business-load/tasks/room-list-preview/', business_load_room_list_preview, name='business-load-room-list-preview'),
    path('business-load/tasks/<int:pk>/', business_load_task_detail, name='business-load-task-detail'),
    path('business-load/tasks/<int:pk>/precheck/', business_load_task_precheck, name='business-load-task-precheck'),
    path('business-load/tasks/<int:pk>/start/', business_load_task_start, name='business-load-task-start'),
    path('business-load/tasks/<int:pk>/trial-run/', business_load_task_trial_run, name='business-load-task-trial-run'),
    path('business-load/tasks/<int:pk>/stop/', business_load_task_stop, name='business-load-task-stop'),
    path('business-load/tasks/<int:pk>/team-room-republish/', business_load_task_team_room_republish, name='business-load-task-team-room-republish'),
    path('business-load/tasks/<int:pk>/team-room-cancel/', business_load_task_team_room_cancel, name='business-load-task-team-room-cancel'),
    path('', include(router.urls)),
]
