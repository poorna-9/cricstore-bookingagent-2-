from django.urls import URLPattern, path
from . import views
from django.contrib.auth.views import LogoutView
urlpatterns=[
    path('',views.selectcity,name='select_city'),
    path('grounds/',views.checkpage,name='grounds_page'),
    path('grounddetail/<int:pk>/',views.grounddetail,name='grounddetail'),
    path('get_reserved_slots/',views.getreservedslots,name='getreservedslots'), # type: ignore
    path('reserveslot/',views.reserveslot,name='reserve_slot'),
    path('checkout/<int:session_id>/', views.checkoutpage, name='checkout'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('bookingthroughagent/',views.bookingagent,name="bookingthroughagent"),
    path('booking-agent/',views.userquerychatbot,name='booking_agent'),
    path('get_user_location/',views.getuserlocation,name="get_user_location"),
    path('tournament-booking/<int:pk>/',views.tournamentBookingPage,name='tournamentBookingPage'),
    path('reservetournamentday/',views.reservetournamentday,name='reservetournamentday'), 
    path('gettournamentreserveddays/',views.gettournamentreserveddays,name='gettournamentreserveddays'),
    path('userquerychatbot/',views.userquerychatbot,name="userquerychatbot"),
]

