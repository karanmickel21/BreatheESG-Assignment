from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('ingestion', views.IngestionBatchViewSet, basename='batch')
router.register('records', views.EmissionRecordViewSet, basename='record')
router.register('facilities', views.FacilityPlantViewSet, basename='facility')

urlpatterns = [
    path('', include(router.urls)),
    path('me/', views.me),
    path('dashboard/', views.dashboard),
]
