# -*- coding: utf-8 -*-
from django.urls import path, include
from .views.execution_views import serve_report_file
from .views.recording_views import (
    RecordingSessionsView,
    RecordingSessionDetailView,
    RecordingInteractionsView,
    RecordingScreenshotView,
    RecordingObserveView,
    RecordingFinalizeView,
)
from rest_framework.routers import DefaultRouter

from .views import (
    AppProjectViewSet,
    AppConfigViewSet,
    AppDeviceViewSet,
    AppElementViewSet,
    AppSemanticDictionaryViewSet,
    AppComponentViewSet,
    AppCustomComponentViewSet,
    AppComponentPackageViewSet,
    AppPackageViewSet,
    AppTestCaseFolderViewSet,
    AppTestCaseTagViewSet,
    AppTestCaseViewSet,
    AppTestSuiteViewSet,
    AppExplorationTaskViewSet,
    AppScheduledTaskViewSet,
    AppNotificationLogViewSet,
    AppTestExecutionViewSet,
    AppDashboardViewSet,
    AppPageMapViewSet,
)

router = DefaultRouter()

router.register(r'projects', AppProjectViewSet, basename='app-project')
router.register(r'config', AppConfigViewSet, basename='app-config')
router.register(r'dashboard', AppDashboardViewSet, basename='app-dashboard')
router.register(r'devices', AppDeviceViewSet, basename='app-device')
router.register(r'elements', AppElementViewSet, basename='app-element')
router.register(r'semantic-dictionaries', AppSemanticDictionaryViewSet, basename='app-semantic-dictionary')
router.register(r'components', AppComponentViewSet, basename='app-component')
router.register(r'custom-components', AppCustomComponentViewSet, basename='app-custom-component')
router.register(r'component-packages', AppComponentPackageViewSet, basename='app-component-package')
router.register(r'packages', AppPackageViewSet, basename='app-package')
router.register(r'test-case-folders', AppTestCaseFolderViewSet, basename='app-test-case-folder')
router.register(r'test-case-tags', AppTestCaseTagViewSet, basename='app-test-case-tag')
router.register(r'test-cases', AppTestCaseViewSet, basename='app-test-case')
router.register(r'test-suites', AppTestSuiteViewSet, basename='app-test-suite')
router.register(r'scheduled-tasks', AppScheduledTaskViewSet, basename='app-scheduled-task')
router.register(r'notification-logs', AppNotificationLogViewSet, basename='app-notification-log')
router.register(r'executions', AppTestExecutionViewSet, basename='app-execution')
router.register(r'exploration-tasks', AppExplorationTaskViewSet, basename='app-exploration-task')
router.register(r'page-maps', AppPageMapViewSet, basename='app-page-map')

urlpatterns = [
    path('', include(router.urls)),
    path('executions/<int:execution_id>/report/', serve_report_file, name='app-execution-report'),
    path('executions/<int:execution_id>/report/<path:file_path>', serve_report_file, name='app-execution-report-file'),

    # 录制器 API (M2 + M3)
    path('recording/sessions/', RecordingSessionsView.as_view(), name='app-recording-sessions'),
    path('recording/sessions/<str:session_id>/', RecordingSessionDetailView.as_view(), name='app-recording-session-detail'),
    path('recording/sessions/<str:session_id>/interactions/', RecordingInteractionsView.as_view(), name='app-recording-interactions'),
    path('recording/sessions/<str:session_id>/screenshot/', RecordingScreenshotView.as_view(), name='app-recording-screenshot'),
    path('recording/sessions/<str:session_id>/observe/', RecordingObserveView.as_view(), name='app-recording-observe'),
    path('recording/sessions/<str:session_id>/finalize/', RecordingFinalizeView.as_view(), name='app-recording-finalize'),
]
