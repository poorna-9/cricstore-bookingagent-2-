from django.urls import URLPattern, path
from . import views
from django.contrib.auth.views import LogoutView
urlpatterns=[
    path('',views.selectcity,name='select_city'),
    path('grounds/',views.checkpage,name='grounds_page'),
    path('grounddetail/<int:pk>/',views.grounddetail,name='grounddetail'),
    path('checkoutpage/',views.checkoutpage,name="bookground"),
    path('processpayment/',views.processpayment,name="process_payment"), # type: ignore
    path('get_reserved_slots/',views.getreservedslots,name='getreservedslots'), # type: ignore
    path('reserveslot/',views.reserveslot,name='reserve_slot'),
    path('user_location',views.getuserlocation,name="get_user_location"),
]