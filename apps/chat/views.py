from django.shortcuts import render

# Create your views here.
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from apps.accounts.models import User

class OwnerConversationView(generics.RetrieveAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        admin = User.objects.filter(role='admin').first()
        if not admin:
            admin = User.objects.filter(is_superuser=True).first()
        conversation, _ = Conversation.objects.get_or_create(owner=self.request.user, admin=admin)
        return conversation

class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs.get('conversation_id')
        return Message.objects.filter(conversation_id=conversation_id).order_by('timestamp')

    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        conversation = Conversation.objects.get(id=conversation_id)
        serializer.save(conversation=conversation, sender=self.request.user)

class AdminConversationListView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Conversation.objects.filter(admin=self.request.user).order_by('-updated_at')