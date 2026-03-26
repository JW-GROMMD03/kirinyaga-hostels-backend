from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts.views import SupportView, AdminProfileView
from apps.accounts.views_admin import (
    AdminProfileUpdateView,
    AnnouncementActiveView,
    SmsBalanceView,
    ImpersonateStartView,
    NewsletterSubscribeView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/admin/', include('apps.accounts.urls_admin')),
    path('api/hostels/', include('apps.hostels.urls')),
    path('api/bookings/', include('apps.bookings.urls')),
    path('api/reviews/', include('apps.reviews.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/roommate/', include('apps.roommate.urls')),
    path('api/subscriptions/', include('apps.subscriptions.urls')),
    path('api/chat/', include('apps.chat.urls')),
    path('api/support/', SupportView.as_view(), name='support'),
    path('api/admin/auth/profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('api/admin/auth/profile/update/', AdminProfileUpdateView.as_view(), name='admin-profile-update'),
    path('api/admin/announcements/active/', AnnouncementActiveView.as_view(), name='announcement-active'),
    path('api/admin/sms/balance/', SmsBalanceView.as_view(), name='sms-balance'),
    path('api/admin/impersonate/start/', ImpersonateStartView.as_view(), name='impersonate-start'),
    path('api/newsletter/subscribe/', NewsletterSubscribeView.as_view(), name='newsletter-subscribe'),
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)