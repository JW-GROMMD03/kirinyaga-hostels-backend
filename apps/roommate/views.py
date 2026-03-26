from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .models import RoommateAd, ScamReport
from .serializers import RoommateAdSerializer, ScamReportSerializer

class RoommateAdListCreateView(generics.ListCreateAPIView):
    serializer_class = RoommateAdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        now = timezone.now()
        return RoommateAd.objects.filter(
            is_active=True
        ).exclude(
            blocked_until__gte=now
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class RoommateAdDetailView(generics.RetrieveAPIView):
    queryset = RoommateAd.objects.all()
    serializer_class = RoommateAdSerializer
    permission_classes = [permissions.AllowAny]

class MyRoommateAdsView(generics.ListAPIView):
    serializer_class = RoommateAdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RoommateAd.objects.filter(user=self.request.user).order_by('-created_at')

class ReportRoommateAdView(generics.CreateAPIView):
    serializer_class = ScamReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        ad_id = self.kwargs.get('pk')
        try:
            ad = RoommateAd.objects.get(pk=ad_id)
        except RoommateAd.DoesNotExist:
            raise serializers.ValidationError('Ad not found')
        serializer.save(ad=ad)

# Admin endpoints
class AdminDeactivateAdView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            ad = RoommateAd.objects.get(pk=pk)
        except RoommateAd.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)
        ad.is_active = False
        ad.save()
        return Response({'status': 'deactivated'})

class AdminBlockUserView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, user_id):
        from apps.accounts.models import User
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        user.is_active = False
        user.save()
        return Response({'status': 'user blocked'})