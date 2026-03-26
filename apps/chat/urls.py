from django.urls import path
from .views import OwnerConversationView, MessageListCreateView, AdminConversationListView

urlpatterns = [
    path('my/', OwnerConversationView.as_view(), name='my-conversation'),
    path('my/messages/', MessageListCreateView.as_view(), kwargs={'conversation_id': None}, name='my-messages'),
    path('<uuid:conversation_id>/messages/', MessageListCreateView.as_view(), name='conversation-messages'),
    path('admin/', AdminConversationListView.as_view(), name='admin-conversations'),
]