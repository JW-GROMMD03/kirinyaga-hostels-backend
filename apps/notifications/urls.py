from django.urls import path
from .views import (
    NotificationListView,
    MarkNotificationReadView,
    NotificationDeleteView,
    SendBulkNotificationView
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications'),
    path('<uuid:pk>/mark-read/', MarkNotificationReadView.as_view(), name='mark-read'),
    path('<uuid:pk>/', NotificationDeleteView.as_view(), name='notification-detail'),
    path('send-bulk/', SendBulkNotificationView.as_view(), name='send-bulk'),
]