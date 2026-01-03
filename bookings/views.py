from datetime import time, timezone
from django.http import JsonResponse
from django.shortcuts import render,get_object_or_404, redirect
from .models import *
from datetime import date, timedelta
from django.views.decorators.csrf import csrf_exempt
from .document import GroundDocument
from datetime import datetime,timedelta
from ai.ground import interpret_ground_query
from django.contrib import messages
from ai.chatcric import interpretgroundquery
import math
from django.db.models import Avg
from django.db import transaction
import razorpay
from django.conf import settings
from .models import payment
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string

def haversine(lat1, lon1, lat2, lon2):
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def findgroundsnear(grounds, radius, userlat, userlon):
    nearby_grounds = []
    for ground in grounds:
        if ground.lattitude is None or ground.longitude is None:
            continue
        distance = haversine(userlat, userlon, ground.lattitude, ground.longitude)
        if distance <= radius:
            nearby_grounds.append(ground)
    return nearby_grounds

@login_required
def bookingagent(request):
    return render(request,"bookings/booking-agent.html",{})

def timingstoslots(timings, sporttype=None, groundorturf="turf",am_pm=None, shift="evening", constraint="between"):
    shift_ampm={
        "morning": "AM",
        "afternoon": "PM",
        "evening": "PM",
        "night": "PM"
    }
    constraint_map = {
    "from": "after",
    "starting": "after",
    "until": "before"
    }
    if shift:
        am_pm=shift_ampm[shift]
    constraint = constraint_map.get(constraint, constraint)
    opening_time = time(6, 0)
    closing_time = time(23, 0)
    userslots = []
    starttime, endtime = parse_natural_timings(timings, shift, am_pm)
    if not starttime or not endtime:
        return userslots  
    if constraint == "after":
        endtime = closing_time
    elif constraint == "before" and "-" not in timings:
        endtime = starttime
        starttime = opening_time
    elif constraint == "between":
        pass
    slotduration = timedelta(hours=3.5) if groundorturf == "ground" else timedelta(hours=1)
    current = datetime.combine(datetime.today(), starttime)
    end_dt = datetime.combine(datetime.today(), endtime)
    while current + slotduration <= end_dt:
        slot_end = current + slotduration
        userslots.append(
            f"{current.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
        )
        current = slot_end
    if am_pm == "AM":
       userslots = [
        s for s in userslots
        if datetime.strptime(s.split(" - ")[0], "%I:%M %p").hour < 12
      ]
    return userslots

def normalize_date_text(text):
    text = text.lower().strip()
    keywords = [
        "this", "next", "coming", "upcoming", "current"
    ]
    weekdays = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday"
    ]
    for k in keywords:
        for d in weekdays:
            text = text.replace(k + d, f"{k} {d}")
    text = text.replace("thisweekend", "this weekend")
    text = text.replace("nextweekend", "next weekend")
    return text

def parse_natural_date(text):
    text = normalize_date_text(text)
    today = datetime.now().date()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "day after tomorrow":
        return today + timedelta(days=2)
    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    words = text.split()
    current_day = today.weekday()
    if len(words) == 1 and words[0] in WEEKDAYS:
        words = ["this", words[0]]
    if words[-1] == "weekend":
        days_until_sat = (5 - current_day) % 7
        if days_until_sat == 0:
            days_until_sat = 7
        if words[0] in ["next", "upcoming"]:
            days_until_sat += 7
        return today + timedelta(days=days_until_sat)
    if words[-1] in WEEKDAYS:
        target = WEEKDAYS[words[-1]]
        delta = (target - current_day) % 7
        if words[0] == "this" and delta == 0:
            return today
        if delta == 0:
            delta = 7
        if words[0] in ["next", "upcoming"]:
            delta += 7
        return today + timedelta(days=delta)
    return None

def parse_natural_timings(timings,shift=None,am_or_pm=None):
    opening=time(6,0)
    closing=time(23,0)
    if not timings or not any(c.isdigit() for c in timings):
      timings = ""
    if not timings and shift:
        if shift=="morning":
            return opening,time(12,0)
        if shift=="afternoon":
            return time(12,0),time(17,0)
        if shift=="evening":
            return time(17,0),time(21,0)
        if shift=="night":
            return time(21,0),closing
    if timings and "-" in timings:
        start,end=timings.split("-")
        start=start.strip()
        end=end.strip()
        if am_or_pm:
            start += f" {am_or_pm.upper()}"
            end += f" {am_or_pm.upper()}"
        start_time = datetime.strptime(start, "%I %p").time() if ":" not in start else datetime.strptime(start, "%I:%M %p").time()
        end_time = datetime.strptime(end, "%I %p").time() if ":" not in end else datetime.strptime(end, "%I:%M %p").time()
        return start_time, end_time
    if timings and "-" not in timings:
       start=timings.strip()
       if am_or_pm:
         start += f" {am_or_pm.upper()}"
       start_time = datetime.strptime(start, "%I %p").time() if ":" not in start else datetime.strptime(start, "%I:%M %p").time()
       if shift=="morning":
        return start_time,time(12,0)
       if shift=="afternoon":
        return start_time,time(17,0)
       if shift=="evening":
        return start_time,time(21,0)
       if shift=="night":
        return start_time,closing  
    return opening,closing

def checkpage(request):
    city=request.GET.get('city','')
    searchquery=request.GET.get('q','')
    ajax=request.GET.get('ajax')
    grounds = Ground.objects.all()
    if city:
        grounds = grounds.filter(city=city)
    if searchquery:
        gptresults = interpret_ground_query(searchquery)
        filters = gptresults.get("filters", {})
        avail_date_str = filters.get("available_date")
        if avail_date_str:
            parsed_date = parse_natural_date(avail_date_str)
            if parsed_date:
                request.session['selected_date'] = parsed_date.strftime('%Y-%m-%d')
        search_ids = GroundDocument.search().query(
            "multi_match",
            query=searchquery,
            fields=["sporttype","name", "location","description","address","price"],
            fuzziness="AUTO"
        )
        if filters.get("price"):
            search_ids=search_ids.filter("match",price=filters["price"])
        if filters.get("address"):
            search_ids = search_ids.filter("match", address=filters["address"])
        if filters.get("location"):
            search_ids = search_ids.filter("match", location=filters["location"])
        if filters.get("sporttype"):
            search_ids = search_ids.filter("match", sporttype=filters["sporttype"])
        if filters.get("name"):
            search_ids= search_ids.filter("match", name=filters["name"])
        search_ids=search_ids.execute()
        ground_ids = [int(hit.meta.id) for hit in search_ids]
        grounds = grounds.filter(id__in=ground_ids)
    if ajax:
        data=[
          {"id": g.id, "name": g.name, "imageURL": g.imageURL, "price": g.price} #type: ignore
            for g in grounds
        ]  
        return JsonResponse({'grounds':data})
    cities= Ground.objects.values_list('city', flat=True).distinct()
    return render(request, 'bookings/checkpage.html', {'grounds': grounds, 'cities': cities,'selected_city':city})
    
def selectcity(request):
    cities=Ground.objects.values_list('city',flat=True).distinct()
    return render(request,'bookings/homepage.html',{'cities':cities})

def grounddetail(request, pk):
    date_str = request.session.pop('selected_date', None)
    if request.GET.get('date'):
      date_str = request.GET.get('date')
    ground = get_object_or_404(Ground, id=pk)
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date_obj = timezone.now().date()
    else:
        date_obj = timezone.now().date()
    date_for_input = date_obj.strftime('%Y-%m-%d')
    today = timezone.now().date().strftime('%Y-%m-%d')
    cities = Ground.objects.values_list('city', flat=True).distinct()

    if request.method == "POST":
        selectedslots = request.POST.get('selected_slots', '')
        slots_list = [s for s in selectedslots.split(',') if s]
        total = ground.price * len(slots_list) #type: ignore
        context = {
            'ground': ground,
            'slots_list': slots_list,
            'total': total
        }
        return render(request, 'bookings/checkoutpage.html', context)
    time_slots = slots.objects.filter(ground=ground, date=date_obj).order_by('starttime')
    booked = time_slots.filter(is_booked=True)
    reserved = time_slots.filter(is_blocked=True)
    available = time_slots.filter(is_blocked=False, is_booked=False)
    userreservedslots = []
    if request.user.is_authenticated:
        usersession = reservationsession.objects.filter(
            user=request.user, ground=ground, date=date_obj
        ).first()
        if usersession:
            userreservedslots = list(
                reservedslots.objects.filter(session=usersession, status='reserved')
            )
            reserved = reserved.exclude(id__in=[s.slot.id for s in userreservedslots])  # type: ignore
    context = {
        'ground': ground,
        'date': date_for_input,   
        'today': today,           
        'cities': cities,
        'selected_city': ground.city,
        'reserved': reserved,
        'booked': booked,
        'available': available,
        'all_slots': time_slots,
        'userreservedslots': userreservedslots,
    }
    return render(request, 'bookings/groundpage.html', context)

def cleanexpiredsessions():
    expired_sessions = reservationsession.objects.filter(expires_at__lt=timezone.now())
    for session in expired_sessions:
        reserved_slots = reservedslots.objects.filter(session=session, status='reserved')
        for rs in reserved_slots:
            slot = rs.slot
            slot.is_blocked = False
            slot.blocked_at = None
            slot.save()
        reserved_slots.delete()
        session.delete()
def tournamentBookingPage(request, pk):
    today = date.today()
    ground = get_object_or_404(Ground, id=pk)
    user = request.user if request.user.is_authenticated else None
    dates = []
    userreserved = set()
    othersreserved = set()
    booked = set()
    for i in range(30):
        d = today + timedelta(days=i)
        dates.append({
            "date": d,
            "day_num": d.day
        })
        day_slots = slots.objects.filter(ground=ground, date=d)
        if day_slots.filter(is_booked=True).exists():
            booked.add(d)
            continue
        blocked = day_slots.filter(is_blocked=True)
        if blocked.exists():
            session_users = blocked.values_list(
                "reservetournament__session__user_id", flat=True
            )

            if user and user.id in session_users:
                userreserved.add(d)
            else:
                othersreserved.add(d)
    context = {
        "ground": ground,
        "dates": dates,
        "booked": booked,
        "userreserveddates": userreserved,
        "reserved": othersreserved,
    }
    return render(request, "bookings/tournament.html", context)

from django.db import IntegrityError
@csrf_exempt
@transaction.atomic
def reservetournamentday(request):
    if request.method != "POST":
        return JsonResponse({"success": False})
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Login required"})
    try:
     cleantournamentexpiredsessions()
     user = request.user
     ground_id = request.POST.get("ground_id")
     date_obj = datetime.strptime(request.POST.get("date"), "%Y-%m-%d").date()
     session_type = request.POST.get("session_type")
     ground = get_object_or_404(Ground, id=ground_id)
     session = tournamentsession.objects.filter(
        user=user,
        ground=ground,
        expires_at__gt=timezone.now()
     ).first()
     if not session:
        session = tournamentsession.objects.create( #type:ignore
            user=user,
            ground=ground,
            start_date=date_obj,
            end_date=date_obj,
            expires_at=timezone.now() + timedelta(minutes=15)
        )
     existing = reservetournament.objects.filter(session=session, date=date_obj).first()
     if existing:
        existing.slots.update(is_blocked=False, blocked_at=None)
        existing.delete()
        remaining = reservetournament.objects.filter(session=session)
        if remaining.exists():
            session.start_date = remaining.order_by("date").first().date
            session.end_date = remaining.order_by("-date").first().date
        else:
            session.delete()
        session.save()
        return JsonResponse({"success": True, "action": "unreserved"})
     day_slots = slots.objects.filter(
        ground=ground,
        date=date_obj,
        is_booked=False,
        is_blocked=False
     )
     if session_type == "morning":
        selected_slots = day_slots.filter(starttime__lt=time(12, 0))
        if selected_slots.count() != 6:
            return JsonResponse({"success": False})
     elif session_type == "evening":
        selected_slots = day_slots.filter(
            starttime__gte=time(12, 0), starttime__lt=time(18, 0)
        )
        if selected_slots.count() != 6:
            return JsonResponse({"success": False})
     elif session_type == "night":
        selected_slots = day_slots.filter(starttime__gte=time(18, 0))
        if selected_slots.count() != 5:
            return JsonResponse({"success": False})
     else:  
        selected_slots = day_slots
        if selected_slots.count() != day_slots.count():
            return JsonResponse({"success": False})
     try:
        rt = reservetournament.objects.create(
            session=session,
            ground=ground,
            date=date_obj,
            status="reserved",
        )
        rt.slots.set(selected_slots)
        selected_slots.update(is_blocked=True, blocked_at=timezone.now())

     except IntegrityError:
        return JsonResponse({
            "success": False,
            "message": "Already reserved by someone else"
        })

     session.start_date = min(session.start_date, date_obj) if session.start_date else date_obj
     session.end_date = max(session.end_date, date_obj) if session.end_date else date_obj
     session.save()
     return JsonResponse({
        "success": True,
        "action": "selected",
        "session_id": session.id
     })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": f"Invalid request: {str(e)}"
        })

tournamentblock = timedelta(minutes=15)

def cleantournamentexpiredsessions():
    now = timezone.now()
    expired_sessions = tournamentsession.objects.filter(expires_at__lt=now)
    reservetournament.objects.filter(
        session__in=expired_sessions
    ).delete()
    expired_slots = slots.objects.filter(
        is_blocked=True,
        blocked_at__lt=now - tournamentblock
    )
    expired_slots.update(is_blocked=False, blocked_at=None)
    print(expired_sessions,expired_slots)
    
def gettournamentreserveddays(request):
    ground_id = request.GET.get("ground_id")
    if not ground_id:
        return JsonResponse({"success": False, "message": "Missing ground_id"})
    ground = get_object_or_404(Ground, id=ground_id)
    cleantournamentexpiredsessions()
    user = request.user if request.user.is_authenticated else None
    today = date.today()
    end_date = today + timedelta(days=29)
    reservations = reservetournament.objects.filter(
        ground=ground,
        date__range=(today, end_date),
        session__expires_at__gt=timezone.now()   
    ).select_related("session", "session__user")
    user_reserved = set()
    others_reserved = set()
    booked = set()
    for r in reservations:
        day_str = str(r.date)
        if r.status == "booked":
            booked.add(day_str)
            continue
        if not r.slots.filter(is_blocked=True).exists():
            continue
        if user and r.session.user_id == user.id:
            user_reserved.add(day_str)
        else:
            others_reserved.add(day_str)
    return JsonResponse({
        "success": True,
        "user_reserved": list(user_reserved),
        "others_reserved": list(others_reserved),
        "booked": list(booked)
    })

@csrf_exempt
def reserveslot(request):
    if request.method != "POST":
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'User not authenticated'})
    user = request.user
    groundid = request.POST.get('ground_id')
    slotid = request.POST.get('slot_id')
    date_str = request.POST.get('date')
    if not date_str:
     return JsonResponse({'success': False, 'message': f'Missing date in request. Received: {request.POST}'})
    if not (groundid and slotid and date_str):
        return JsonResponse({'success': False, 'message': 'Missing parameters'})
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid date format'})
    try:
        ground = Ground.objects.get(id=groundid)
        slot = slots.objects.get(id=slotid, ground=ground, date=date_obj)
    except (Ground.DoesNotExist, slots.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Invalid ground or slot'})
    cleanexpiredsessions()
    session, created = reservationsession.objects.get_or_create(
        user=user,
        ground=ground,
        date=date_obj,
        defaults={'expires_at': timezone.now() + timedelta(minutes=15)}
    )
    reserved_slot = reservedslots.objects.filter(session=session, slot=slot).first()
    if reserved_slot:
        reserved_slot.delete()
        slot.is_blocked = False
        slot.blocked_at = None
        slot.save()
        return JsonResponse({'success': True, 'action': 'unselected'})
    if reservedslots.objects.filter(slot=slot, status='reserved', session__expires_at__gt=timezone.now()).exists() or slot.is_booked:
        return JsonResponse({'success': False, 'message': 'Slot already reserved or booked'})
    reservedslots.objects.create(session=session, slot=slot, status='reserved')
    slot.is_blocked = True
    slot.blocked_at = timezone.now()
    slot.save()
    return JsonResponse({'success': True, 'action': 'selected',"session_id":session.id})
def getreservedslots(request):
    groundid = request.GET.get('ground_id')
    date = request.GET.get('date')
    if not (groundid and date):
        return JsonResponse({'success': False, 'message': 'Missing parameters'})
    try:
        ground = Ground.objects.get(id=groundid)
    except Ground.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid ground'})
    cleanexpiredsessions()
    all_reserved = slots.objects.filter(ground=ground, date=date, is_blocked=True, is_booked=False)
    booked_slots = slots.objects.filter(ground=ground, date=date, is_booked=True)
    user_reserved, others_reserved = [], []
    user = request.user if request.user.is_authenticated else None
    for s in all_reserved:
        rs = reservedslots.objects.filter(slot=s, status='reserved').first()
        if rs and user and rs.session.user == user:
            user_reserved.append(str(s.id)) #type: ignore
        else:
            others_reserved.append(str(s.id)) #type: ignore
    booked = [str(s.id) for s in booked_slots] #type: ignore
    return JsonResponse({
        'user_reserved': user_reserved,
        'others_reserved': others_reserved,
        'booked': booked
    })


client=razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
def tournamentcheckout(request, session_id):
    t_session = tournamentsession.objects.get(
        id=session_id,
        user=request.user
    )
    reserveddays = (
        reservetournament.objects
        .filter(session=t_session, status="reserved")
        .prefetch_related("slots")
    )
    all_slots = []
    for rd in reserveddays:
        all_slots.extend(rd.slots.all())
    total = sum(float(slot.price) for slot in all_slots)
    pay = payment.objects.create(
        user=request.user,
        tournament_session=t_session,  
        amount=total,
    )
    order = client.order.create({
        "amount": int(total * 100),
        "currency": "INR",
        "receipt": f"order_rcptid_{pay.id}",
    })
    pay.order_id = order["id"]
    pay.save(update_fields=["order_id"])
    return render(request, "bookings/tournamentcheckout.html", {
        "session": t_session,
        "reserved": reserveddays,
        "slots": all_slots,
        "total": total,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "order_id": order["id"],
        "ground": t_session.ground,
    })

def checkoutpage(request, session_id):
    session = reservationsession.objects.get(
        id=session_id,
        user=request.user
    )
    reserved = reservedslots.objects.filter(
        session=session,
    )
    total = sum(float(rs.slot.price) for rs in reserved)
    pay = payment.objects.create(
        user=request.user,
        session=session,         
        amount=total,
    )
    order = client.order.create({
        "amount": int(total * 100),
        "currency": "INR",
        "receipt": f"order_rcptid_{pay.id}",
    })
    pay.order_id = order["id"]
    pay.save(update_fields=["order_id"])
    return render(request, "bookings/checkoutpage.html", {
        "session": session,
        "reserved": reserved,
        "total": total,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "order_id": order["id"],
        "ground": session.ground,
    })

import hmac
import hashlib

def verifysignature(order_id, payment_id, signature):
    generated_signature = hmac.new(
        key=bytes(settings.RAZORPAY_KEY_SECRET, 'utf-8'),
        msg=bytes(order_id + "|" + payment_id, 'utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()
    return generated_signature == signature
@csrf_exempt
def payment_success(request):
    if request.method != "POST":
        return JsonResponse({"success": False}, status=400)
    data = request.POST
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not verifysignature(order_id, payment_id, signature):
        return JsonResponse({"success": False, "message": "Invalid signature"}, status=400)
    try:
        pay = payment.objects.get(
            order_id=order_id
        )
        pay.payment_id = payment_id
        pay.status = "success"
        pay.save()
        if pay.session:
            reserved = reservedslots.objects.filter(
                session=pay.session,
                status="reserved"
            )
            total_price = 0
            slots_booked = []
            for rs in reserved:
                rs.slot.is_booked = True
                rs.slot.is_blocked = False
                rs.slot.save()
                rs.status = "booked"
                rs.save()
                total_price += rs.slot.price
                slots_booked.append(rs.slot)
            Orders.objects.create(
                session=pay.session,
                user=pay.user,
                ground=pay.session.ground,
                date=pay.session.date,
                transaction_id=payment_id,
                booked=True,
                status="booked",
                price=total_price,
                Tournament_or_normal="normal"
            ).slotsbooked.set(slots_booked)
        if pay.tournament_session:
            t_session = pay.tournament_session
            reservations = reservetournament.objects.filter(
                session=t_session,
                status="reserved"
            ).prefetch_related("slots")
            total_price = 0
            all_slots = []
            for rd in reservations:
                for slot in rd.slots.all():
                    slot.is_booked = True
                    slot.is_blocked = False
                    slot.save()
                    total_price += slot.price
                    all_slots.append(slot)

                rd.status = "booked"
                rd.save()
            Orders.objects.create(
                session=pay.tournament_session,
                user=pay.user,
                ground=t_session.ground,
                date=t_session.start_date,
                transaction_id=payment_id,
                booked=True,
                status="booked",
                price=total_price,
                Tournament_or_normal="tournament"
            ).slotsbooked.set(all_slots)
        return render(request, "payment_success.html", {"payment": pay})
    except payment.DoesNotExist:
        return JsonResponse({"success": False, "message": "Payment not found"}, status=404)

        

def get_lat_long(address):
    api_key = "pk.9a6225b4ea47b4e24c62938d1d821a4f"
    url = "https://us1.locationiq.com/v1/search"
    params = {"q": address, "key": api_key, "format": "json"}
    headers = {"User-Agent": "CricStore-App/1.0"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    if isinstance(data, list) and data:
        loc = data[0]
        return loc["lat"], loc["lon"]
    return None, None


def getuserlocation(request):
    if request.method == "POST":
        address = request.POST.get("user_address")
        if not address:
            return JsonResponse({"success": False, "message": "Enter a valid address."})
        lat, lon = get_lat_long(address)
        if lat and lon:
            request.session["user_lat"] = float(lat)
            request.session["user_lon"] = float(lon)
            request.session["user_address"] = address
            return JsonResponse({
                "success": True,
                "message": "Location updated successfully!"
            })
        return JsonResponse({
            "success": False,
            "message": "Couldn't fetch location. Try again."
        })
    return JsonResponse({"success": False, "message": "Invalid request."})

def handle_ground_info(context):
    ground_name = context.get("ground_or_turf_name") or context.get("ground_name")
    city = context.get("city")
    area = context.get("area")
    if not ground_name:
        return {"message": "Please tell me the ground or turf name."}
    filters = {"name__icontains": ground_name}
    if city:
        filters["city__icontains"] = city
    if area:
        filters["address__icontains"] = area
    ground = Ground.objects.filter(**filters).first()
    if not ground:
        return {"message": f"Sorry, I couldn’t find any ground named {ground_name}."}
    if context.get("intent")=="address":
        return {"message":f"the address the ground is {ground.address}"}
    if context.get("intent") == "ground_status":
        is_open = bool(int.from_bytes(ground.opens, "little")) if ground.opens is not None else False
        if is_open:
            return {"message": f"Yes, {ground.name} is open today!"}
        else:
            return {"message": f" Sorry, {ground.name} is closed today."}
    if context.get("intent") == "ground_facilities":
        facilities = []
        if bool(int.from_bytes(ground.batballprovided, "little")):
            facilities.append("Bat and Ball Provided")
        if bool(int.from_bytes(ground.washroomsavailable, "little")):
            facilities.append("Washrooms Available")
        if ground.Grounddimensions:
            facilities.append(f"Dimensions: {ground.Grounddimensions} meters")

        if not facilities:
            return {"message": f"No specific facility information available for {ground.name}."}
        return {"message": f"{ground.name} offers: {', '.join(facilities)}."}
    is_open = bool(int.from_bytes(ground.opens, "little")) if ground.opens is not None else False
    rating = ground.rating or "N/A"
    price = ground.price or "N/A"
    sport = ground.sporttype.capitalize()
    facilities_list = []
    if bool(int.from_bytes(ground.batballprovided, "little")):
        facilities_list.append("Bat & Ball Provided")
    if bool(int.from_bytes(ground.washroomsavailable, "little")):
        facilities_list.append("Washrooms")
    if ground.Grounddimensions:
        facilities_list.append(f"Dimensions: {ground.Grounddimensions}m")
    facilities_str = ", ".join(facilities_list) if facilities_list else "Basic facilities available"
    response = (
        f"*{ground.name}* ({sport}) — located in {ground.city}.\n"
        f" Average price: ₹{price}\n Rating: {rating}\n"
        f"Facilities: {facilities_str}\n"
        f"Status: {' Open' if is_open else 'Closed'}"
    )
    return {"message": response}
from collections import defaultdict
def detect_booking_type(query: str) -> str:
    keywords = ["tournament", "league"]
    q = query.lower()
    return "tournament" if any(k in q for k in keywords) else "normal_booking"

def userquerychatbot(request):
    query = request.GET.get('query', '')
    if "booking_type" not in request.session:
      request.session["booking_type"] = detect_booking_type(query)
    booking_type=request.session["booking_type"]
    output = interpretgroundquery(query,booking_type)
    print(output)
    if "chatcontext" not in request.session:
        request.session["chatcontext"] = {}
    context = request.session["chatcontext"]
    raw_intent = (output.get("intent") or "").lower()
    INTENT_MAP = {
     "show": "show_ground",
     "find": "show_ground",
     "search": "show_ground",
     "recommend": "show_ground",
     "suggest": "show_ground",
     "view": "show_ground",

     "book": "book",
     "reserve": "book",
     "schedule": "book",

     "cancel": "cancel_booking",
     "change": "cancel_booking",
     "modify": "cancel_booking",

     "reschedule": "reschedule",

     "about": "ground_info",
     "info_ground": "ground_info",
     "tellme": "ground_info",
   }
    normalized_intent = INTENT_MAP.get(raw_intent, "unknown")
    context["intent"] = normalized_intent
    context['booking_type']=output.get('booking_type')
    context.update(output.get('filters',{}))
    print(context)
    request.session.modified = True
    sport_type = (context.get("sporttype") or "").lower().strip()
    ground_or_turf = (context.get("ground_or_turf") or "").lower().strip()
    if not sport_type:
       q = query.lower()
       if "football" in q:
          sport_type = "football"
       elif "cricket" in q:
          sport_type = "cricket"
       elif "hockey" in q:
          sport_type = "hockey"
       elif "badminton" in q:
          sport_type = "badminton"
       elif "tennis" in q:
          sport_type = "tennis"
       elif "volleyball" in q:
          sport_type = "volleyball"
    outdoor_sports = ["cricket", "football", "hockey"]
    if not sport_type:
        return JsonResponse({'message':"Which sport are you looking to book a ground for ?"})
    if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?"
            return JsonResponse({
                "message": response_message,
            })
    else:
        ground_or_turf = "turf"
    context["sporttype"] = sport_type
    context["ground_or_turf"] = ground_or_turf
    request.session.modified = True
    grounds = Ground.objects.filter(sporttype=sport_type, types=ground_or_turf)
    bookingtype= context.get("booking_type", "").lower().strip()
    if bookingtype=="normal_booking" and context.get("intent") == "show_ground":
        if not context.get("ground_or_turf_name"):
         if context.get("date"):
            parsed_date=parse_natural_date(context["date"])
            if parsed_date:
               context["date"]=parsed_date.isoformat()
         if not context.get("city"):
            if context.get("radius_km"):
              if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
              user_lat = float(request.session["user_lat"])
              user_lon = float(request.session["user_lon"])
              grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
              if isinstance(grounds, list):
                ground_ids = [g.id for g in grounds]
                grounds = Ground.objects.filter(id__in=ground_ids)
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("bookings/checkpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
            return JsonResponse({'message': "Please tell me which city you want to search grounds in."})
         if context.get("city"):
            grounds = grounds.filter(city__icontains=context["city"])
         if context.get("area"):
            grounds = grounds.filter(address__icontains=context["area"])
         if context.get("radius_km"):
            if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
            user_lat = float(request.session["user_lat"])
            user_lon = float(request.session["user_lon"])
            grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
            if isinstance(grounds, list):
              ground_ids = [g.id for g in grounds]
              grounds = Ground.objects.filter(id__in=ground_ids)
         if context.get("rating_min"):
            grounds = grounds.filter(rating__gte=float(context["rating_min"]))
         if context.get("rating_semantic") == "top_rated":
            grounds = grounds.filter(rating__gte=3).order_by('-rating')
         elif context.get("rating_semantic") == "low_rated":
            grounds = grounds.filter(rating__lte=3).order_by('rating')
         if context.get("price_semantic") == "cheaper" and not context.get("price"):
            avg_price = grounds.aggregate(Avg('price'))['price__avg']
            grounds = grounds.filter(price__lte=avg_price).order_by("price")
         elif context.get("price_semantic") == "expensive" and not context.get("price"):
            avg_price = grounds.aggregate(avg_price=Avg('price'))['avg_price']
            if avg_price:
                grounds = grounds.filter(price__gte=avg_price).order_by('-price')
         if context.get("price"):
            max_price = float(context["price"]) + 100
            grounds = grounds.filter(price__lte=max_price)
         if context.get("rating"):
            grounds = grounds.filter(rating__gte=float(context["rating"]))
         cities= Ground.objects.values_list('city', flat=True).distinct()
         html_page = render_to_string("bookings/checkpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
         return JsonResponse({"message":"these are grounds based on your requirements","html": html_page})
        if context.get("ground_or_turf_name"):
            if not context.get("area"):
                return JsonResponse({'message': "Please tell me which area this ground is in"})
            ground = Ground.objects.filter(
                name__iexact=context["ground_or_turf_name"],
                city__icontains=context["city"],
                address__icontains=context["area"]
            ).first()
            if not ground:
                grounds=Ground.objects.filter(address__icontains=context["area"])
                html_page=render_to_string("bookings/checkpage.html",{'grounds':grounds},request=request)
                return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
            if context.get("open"):
                if ground.opens:
                    return JsonResponse({'message':"yes it's open"})
                else:
                    return JsonResponse({"message":"sorry today ground is closed "})
            date_str = context.get("date")
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    date_obj = timezone.now().date()
            else:
                date_obj = timezone.now().date()
            date_for_input = date_obj.strftime('%Y-%m-%d')
            today = timezone.now().date().strftime('%Y-%m-%d')
            cities = Ground.objects.values_list('city', flat=True).distinct()
            time_slots = slots.objects.filter(ground=ground, date=date_obj).order_by('starttime')
            booked = time_slots.filter(is_booked=True)
            reserved = time_slots.filter(is_blocked=True)
            available = time_slots.filter(is_blocked=False, is_booked=False)
            userreservedslots = []
            if request.user.is_authenticated:
                usersession = reservationsession.objects.filter(
                    user=request.user, ground=ground, date=date_obj
                ).first()
                if usersession:
                    userreservedslots = list(
                        reservedslots.objects.filter(session=usersession, status='reserved')
                    )
                    reserved = reserved.exclude(id__in=[s.slot.id for s in userreservedslots])
            html_page=render_to_string("bookings/groundpage.html",{'ground': ground,'date': date_for_input,'today': today,'cities': cities,'selected_city': ground.city,'reserved': reserved,'booked': booked,'available': available,'all_slots': time_slots,'userreservedslots': userreservedslots},request=request)
            return JsonResponse({"message":"check the ground details and its slot details","html":html_page})
    if bookingtype=="normal_booking" and context.get("intent") == "book":
        required_fields = ["ground_or_turf_name", "city", "area", "date", "timings"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}."})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page=render_to_string("bookings/checkpage.html",{'grounds':grounds},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        try:
            date_obj = datetime.strptime(context["date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        constraint = context.get("constraint_type", "between")
        userslots = timingstoslots(
            context["timings"], context["sporttype"],context["ground_or_turf"], context["am_pm"],context["shift"],constraint
        )
        if not userslots:
            return JsonResponse({
                 "message": "I couldn’t understand the time. Please specify a time like '5 to 7 evening'."
                })
        if len(userslots) > 2 and not context.get("hours"):
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?"})
        if context.get("hours"):
            userneedstoplay = int(context.get("hours"))
        else:
            userneedstoplay=len(userslots)
        output_res = chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay)
        if not isinstance(output_res,dict):
            return JsonResponse({'message': 'Error reserving slots. Please try again.'})
        if not output_res.get("success"):
            message=output_res.get("message")
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if output_res.get('alternative_grounds'):
                altgrounds=output_res.get('alternative_grounds')
                message=output_res.get("message")
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("bookings/checkpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":message,"html": html_page})
            else:
                return JsonResponse({"message":message})
        reservedslot_ids=output_res.get("reserved_slots",[])
        session_id=output_res.get("session_id")
        total = len(reservedslot_ids) * float(ground.price)
        payments = payment.objects.create(session_id=session_id, user=request.user, amount=total)
        order_data = {
            "amount": int(total * 100),  
            "currency": "INR",
            "receipt": f"order_rcptid_{payments.id}",
            }
        order = client.order.create(order_data)
        payments.order_id = order['id']
        payments.save()
        session_obj = reservationsession.objects.get(id=session_id, user=request.user)
        reserved_qs = reservedslots.objects.filter(session=session_obj, status='reserved')
        html_page=render_to_string("bookings/checkoutpage.html",{"session": session_obj,"reserved": reserved_qs,"total": total,"razorpay_key": settings.RAZORPAY_KEY_ID,"order_id": order["id"], "payment_id": payments.id, "ground": session_obj.ground})
        return JsonResponse({"message":"please complete payment with 15 mins","html":html_page})                         
    if context.get("intent")=="cancel_booking":
        pastorders=Orders.objects.filter(user=request.user,date__gt=timezone.now().date(),booked=True).order_by("date")
        if not pastorders.exists():
            return JsonResponse({"message": "You have no upcoming bookings to cancel."})
        booking_id=request.POST.get("booking_id", None)
        if not booking_id:
            options = []
            for order in pastorders:
                slotlist=", ".join([s.time for s in order.slotsbooked.all()])
                options.append({"id":order.id,"text": f"{order.ground.name} on {order.date} — Slots: {slotlist}"})
            return JsonResponse({"message": "Which booking would you like to cancel?","options":options})
        booking = Orders.objects.filter(id=booking_id, user=request.user).first()
        if not booking:
           return JsonResponse({"message": "Invalid booking selected."})
        if booking.date < timezone.now().date():
           return JsonResponse({"message": "You can't cancel this booking anymore. If you need help, just ask."})
        with transaction.atomic():
            if booking.Tournament_or_normal=="normal":
             for slot in booking.slotsbooked.all():
                slot.is_blocked=False
                slot.is_booked=False
                slot.blocked_at=None
                slot.save(update_fields=["is_blocked", "is_booked","blocked_at"])
             booking.booked = False
             booking.status = "cancelled"
             booking.save(update_fields=["booked", "status"])
             return JsonResponse({
             "message": f"Your booking is cancelled successfully. Refund of ₹{booking.price} is initiated."
              })
            elif booking.Tournament_or_normal=="tournament":
                session_id=booking.session
                session = tournamentsession.objects.filter(id=session_id, user=request.user).first()
                if not session:
                    return JsonResponse({"message": "Invalid booking selected."})
                for days in reservetournament.objects.filter(session=session, status="booked"):
                    for slot in days.slots.all():
                        slot.is_blocked = False
                        slot.is_booked = False
                        slot.blocked_at=None
                        slot.save(update_fields=["is_blocked", "is_booked","blocked_at"])
                    days.delete()   
                session.status="cancelled"
                session.save(update_fields=["status"])
                booking.booked = False
                booking.status = "cancelled"
                booking.save(update_fields=["booked", "status"])
                return JsonResponse({
                    "message": f"Your tournament booking is cancelled successfully. Refund of ₹{booking.price} is initiated."
                }) 
    if context.get("intent") == "reschedule":
      booking_id = request.POST.get("booking_id")
      if not booking_id:
        pastorders = Orders.objects.filter(
            user=request.user,
            date__gt=timezone.now().date(),
            booked=True
        ).order_by("date")
        if not pastorders.exists():
            return JsonResponse({"message": "You have no upcoming bookings to reschedule."})
        options = []
        for order in pastorders:
            slots = ",".join([s.time for s in order.slotsbooked.all()])
            options.append({
                "id": order.id,
                "text": f"{order.ground.name} on {order.date} — Slots: {slots}"
            })
        return JsonResponse({
            "message": "Which booking would you like to reschedule?",
            "options": options
        })
      booking = Orders.objects.filter(id=booking_id, user=request.user).first()
      if not booking:
        return JsonResponse({"message": "Invalid booking selected."})
      if booking.date < timezone.now().date():
        return JsonResponse({"message": "This booking cannot be rescheduled now."})
      if not context.get("timings") or not context.get("start_date"):
        return JsonResponse({"message": "Tell me the new date and new timings you want to reschedule to."})
      if booking.Tournament_or_normal == "normal":
        required_fields = ["ground_or_turf_name", "city", "area", "date", "timings"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}."})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page=render_to_string("bookings/checkpage.html",{'grounds':grounds},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        try:
            date_obj = datetime.strptime(context["date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        constraint = context.get("constraint_type", "between")
        userslots = timingstoslots(
            context["timings"], context["sporttype"],context["ground_or_turf"], context["am_pm"],context["shift"],constraint
        )
        if not userslots:
            return JsonResponse({
                 "message": "I couldn’t understand the time. Please specify a time like '5 to 7 evening'."
                })
        if len(userslots) > 2 and not context.get("hours"):
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?"})
        if context.get("hours"):
            userneedstoplay = int(context.get("hours"))
        else:
            userneedstoplay=len(userslots)
        reserve = chatbot_reserve_slots(request, ground, date_obj,userslots,userneedstoplay)
        if not reserve.get("success"):
            message=reserve.get("message")
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if reserve.get('alternative_grounds'):
                altgrounds=reserve.get('alternative_grounds')
                message=reserve.get("message")
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("bookings/checkpage.html",{"grounds": altgrounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":message,"html": html_page})
            else:
                return JsonResponse({"message":message})
        with transaction.atomic():
         for s in booking.slotsbooked.all():
            s.is_blocked=False
            s.is_booked=False
            s.blocked_at=None
            s.save()
            booking.booked=False
            booking.status="cancelled"
            booking.save(update_fields=["booked", "status"])
        reserved_ids = reserve['reserved_slots']
        session_id = reserve['session_id']
        total = len(reserved_ids) * float(ground.price)
        pay = payment.objects.create(
          session_id=session_id,
          user=request.user,
          amount=total,
          )
        order_data = {
          "amount": int(total * 100),
          "currency": "INR",
          "receipt": f"order_rcptid_{pay.id}",
          }
        rp_order = client.order.create(order_data)
        pay.order_id = rp_order["id"]
        pay.save()
        session_obj = reservationsession.objects.get(id=session_id)
        reserved_qs = reservedslots.objects.filter(session=session_obj, status="reserved")
        html = render_to_string("bookings/checkoutpage.html", {
          "session": session_obj,
          "reserved": reserved_qs,
          "total": total,
          "razorpay_key": settings.RAZORPAY_KEY_ID,
          "order_id": rp_order["id"],
          "payment_id": pay.id,
          "ground": session_obj.ground
          })
        return JsonResponse({
          "message": "Please complete payment in 15 minutes.",
          "html": html
          })  
      if booking.Tournament_or_normal == "tournament":
          session_id=booking.session.id
          ground=booking.ground
          session= tournamentsession.objects.filter(id=session_id, user=request.user).first()
          if not context.get("start_date") or not context.get("end_date"):
            return JsonResponse({'message': "Please provide the start date and end date for the tournament booking."})
          if not context.get("sessions_per_day"):
            return JsonResponse({'message': "Please specify if you want full_day or morning, evening, or night sessions for the tournament booking."})
          start=context.get("start_date")
          end=context.get("end_date")
          start_date = datetime.strptime(start, "%Y-%m-%d").date()
          end_date = datetime.strptime(end, "%Y-%m-%d").date()
          session_type=context.get("shift")
          success, unavailable_days, session_id, datelist = chatbot_block_tournament_days(
                request.user, ground, start_date, end_date, session_type)
          if not success:
            return JsonResponse({
              'message': "Some dates are unavailable for your tournament. Please check below.",
              'html': render_to_string("bookings/tournament.html", {
                     'ground': ground,
                     'datelist': datelist
                     }, request=request)
                })
          if success:
            for days in reservetournament.objects.filter(session=session, status="booked"):
                for slot in days.slots.all():
                        slot.is_blocked = False
                        slot.is_booked = False
                        slot.save(update_fields=["is_blocked", "is_booked"])
                days.delete()   
            session.status="cancelled"
            session.save(update_fields=["status"])
            booking.booked = False
            booking.status = "cancelled"
            booking.save(update_fields=["booked", "status"])
            tournamentcheckout(request,session_id)
            return JsonResponse({
                "message": "Your tournament booking is cancelled successfully. Your rescedule is processing now.",})
    #############################################################################################################################################


         
    if context.get("intent") in ["ground_info", "ground_facilities", "ground_status"]:
        info_result = handle_ground_info(context)
        return JsonResponse(info_result)
    #############################################################################################################################################
    if context.get("type").lower()=="tournament" and context.get("intent") in ["check_availability",'checkavailability','check_conflict','checkconflict']:
        shifts={
            "fullday":(time(6,0),time(23,0)),
            "morning":(time(6,0),time(12,0)),
            "afternoon":(time(12,0),time(16,0)),
            "evening":(time(16,0),time(19,0)),
            "night":(time(19,0),time(23,0))
        }
        if context.get("start_date"):
            parsed_date = parse_natural_date(context["start_date"])
            if parsed_date:
                context["start_date"] = parsed_date.strftime("%Y-%m-%d")
        if context.get("end_date"):
            parsed_date = parse_natural_date(context["end_date"])
            if parsed_date:
                context["end_date"] = parsed_date.strftime("%Y-%m-%d")   
        if context.get("start_date") and context.get("end_date"):
            if context.get("ground_or_turf_name"):
                ground=context.get("ground_or_turf_name")
                if context.get("city") and context.get("area"):
                    ground=Ground.objects.filter(ground=ground,city__icontains=context["city"] ,address__icontains=context["area"])
                    if ground:
                        start,end=shifts["fullday"]
                        if context.get("shift"):
                            start,end=shifts[context.get("shift")]

                        
    if context.get("type")=="tournament" and context.get("intent") in ["show", "find", "search","recommend","suggest","view"]:
        if context.get("start_date"):
            parsed_date = parse_natural_date(context["start_date"])
            if parsed_date:
                context["start_date"] = parsed_date.strftime("%Y-%m-%d")
        if context.get("end_date"):
            parsed_date = parse_natural_date(context["end_date"])
            if parsed_date:
                context["end_date"] = parsed_date.strftime("%Y-%m-%d")     
        if not context.get("ground_or_turf_name"):
         if not context.get("city"):
            if context.get("radius_km"):
              if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
              user_lat = float(request.session["user_lat"])
              user_lon = float(request.session["user_lon"])
              grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
              if isinstance(grounds, list):
                ground_ids = [g.id for g in grounds]
                grounds = Ground.objects.filter(id__in=ground_ids)
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("bookings/checkpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
            return JsonResponse({'message': "Please tell me which city you want to search grounds in."})
         if context.get("city"):
            grounds = grounds.filter(city__icontains=context["city"])
         if context.get("area"):
            grounds = grounds.filter(address__icontains=context["area"])
         if context.get("radius_km"):
            if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})
            user_lat = float(request.session["user_lat"])
            user_lon = float(request.session["user_lon"])
            grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
            if isinstance(grounds, list):
              ground_ids = [g.id for g in grounds]
            grounds = Ground.objects.filter(id__in=ground_ids)
         if context.get("rating_min"):
            grounds = grounds.filter(rating__gte=float(context["rating_min"]))
         if context.get("rating_semantic") == "top_rated":
            grounds = grounds.filter(rating__gte=3).order_by('-rating')
         elif context.get("rating_semantic") == "low_rated":
            grounds = grounds.filter(rating__lte=3).order_by('rating')
         if context.get("price_semantic") == "cheaper" and not context.get("price"):
            avg_price = grounds.aggregate(Avg('price'))['price__avg']
            grounds = grounds.filter(price__lte=avg_price).order_by("price")
         elif context.get("price_semantic") == "expensive" and not context.get("price"):
            avg_price = grounds.aggregate(avg_price=Avg('price'))['avg_price']
            if avg_price:
                grounds = grounds.filter(price__gte=avg_price).order_by('-price')
         if context.get("price"):
            max_price = float(context["price"]) + 100
            grounds = grounds.filter(price__lte=max_price)
         if context.get("rating"):
            grounds = grounds.filter(rating__gte=float(context["rating"]))
         cities= Ground.objects.values_list('city', flat=True).distinct()
         html_page = render_to_string("bookings/checkpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
         return JsonResponse({"message":"these are grounds based on your requirements","html": html_page})
        if context.get("ground_or_turf_name"):
            if not context.get("area"):
                return JsonResponse({'message': "Please tell me which area this ground is in"})
            ground = Ground.objects.filter(
                name__iexact=context["ground_or_turf_name"],
                city__icontains=context["city"],
                address__icontains=context["area"]
            ).first()
            if not ground:
                grounds=Ground.objects.filter(address__icontains=context["area"])
                html_page=render_to_string("bookings/checkpage.html",{'grounds':grounds},request=request)
                return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
            if context.get("open"):
                if ground.opens:
                    return JsonResponse({'message':"yes it's open"})
                else:
                    return JsonResponse({"message":"sorry today ground is closed "})
            if request.session.get("start_date") and request.session.get("end_date"):
                start_date = request.session["start_date"]
                end_date = request.session["end_date"]
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                daterange=[start+timedelta(i) for i in range((end - start).days + 1)]
                allslots=(slots.objects.filter(ground__in=grounds,date__in=daterange))
                slotmap=defaultdict(list)
                for s in allslots:
                   slotmap[(s.ground_id, s.date)].append(s)
                unavailable_days=[]
                for d in daterange:
                    day_slots = slotmap.get((ground.id, d), [])
                    if not day_slots or any(s.is_booked or s.is_blocked for s in day_slots):
                        unavailable_days.append(d)
                if unavailable_days:
                    available_grounds = []
                    for g in grounds:
                        isavailable=True
                        for d in daterange:
                            day_slots = slotmap.get((g.id, d), [])
                            if not day_slots or any(s.is_booked or s.is_blocked for s in day_slots):
                                isavailable = False
                                break
                        if isavailable:
                            available_grounds.append(g)
                    message="The ground is not completely available on {unavailable_days} These are the grounds that are available in your area check once"
                    html_page= render_to_string("bookings/checkpage.html",{'grounds':available_grounds},request=request)
                    return JsonResponse({'message': message, 'html': html_page})
                else:
                    message="That ground is available on all days if you want to book click book"
                    return JsonResponse({"message":message})
            else:
                today = timezone.now().date().strftime('%Y-%m-%d')
                date_list=[]
                for i in range(30):
                    d = timezone.now().date() + timedelta(days=i)
                    day_slots = slots.objects.filter(ground=ground, date=d)
                    if not day_slots.exists():
                        status = "unavailable"
                    else:
                        all_free = not day_slots.filter(is_booked=True).exists() and \
                        not day_slots.filter(is_blocked=True).exists()
                    status = "available" if all_free else "unavailable"
                    date_list.append({
                        "date": d,
                        "day_num": d.day,
                        "status": status
                    })
                context={
                        "ground":ground,
                        "datelist":date_list,
                }
                html_page=render_to_string("bookings/tournament.html",context,request=request)
                return JsonResponse({'message':"the availability of 30 days of that ground are", 'html': html_page})
            
##################################################################################################################################################

    if output.get("type") == "Tournament" and output.get("intent") in ["book", "reserve", "schedule"]:
        if not context.get("ground_or_turf_name"):
            return JsonResponse({'message': "Please provide the ground or turf name for the tournament booking."})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page=render_to_string("bookings/checkpage.html",{'grounds':grounds},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        if not context.get("start_date") or not context.get("end_date"):
            return JsonResponse({'message': "Please provide the start date and end date for the tournament booking."})
        if not context.get("sessions_per_day"):
            return JsonResponse({'message': "Please specify if you want full_day or morning, evening, or night sessions for the tournament booking."})
        start=context.get("start_date")
        end=context.get("end_date")
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        session_type=context.get("shift")
        success, unavailable_days, session_id, datelist = chatbot_block_tournament_days(
                request.user, ground, start_date, end_date, session_type)
        if not success:
            return JsonResponse({
              'message': "Some dates are unavailable for your tournament. Please check below.",
              'html': render_to_string("bookings/tournament.html", {
                     'ground': ground,
                     'datelist': datelist
                     }, request=request)
                })
        if success:
            tournamentcheckout(request,session_id)
    return JsonResponse({
    "message": "I couldn't understand your request. Please refine it."
    })


def chatbot_block_tournament_days(user, ground, start_date, end_date, session_type):
    cleantournamentexpiredsessions()
    datelist = []
    unavailable_days = []
    success = True
    with transaction.atomic():
        for i in range((end_date - start_date).days + 1):
            d = start_date + timedelta(days=i)
            day_slots = slots.objects.filter(ground=ground, date=d)

            if not day_slots.exists():
                success = False
                unavailable_days.append(d)
                datelist.append({"date": d, "status": "unavailable"})
                continue
            if session_type == "full_day":
                all_free = not day_slots.filter(is_booked=True).exists() and \
                           not day_slots.filter(is_blocked=True).exists()

            elif session_type == "morning":
                all_free = day_slots.filter(is_booked=False, is_blocked=False,
                                            starttime__lt=time(12, 0)).exists()

            elif session_type == "evening":
                all_free = day_slots.filter(is_booked=False, is_blocked=False,
                                            starttime__gte=time(12, 0), starttime__lt=time(18, 0)).exists()

            elif session_type == "night":
                all_free = day_slots.filter(is_booked=False, is_blocked=False,
                                            starttime__gte=time(18, 0)).exists()
            else:
                all_free = False

            datelist.append({
                "date": d,
                "status": "available" if all_free else "unavailable",
                "session_type": session_type
            })

            if not all_free:
                success = False
                unavailable_days.append(d)
        
        if not success:
            transaction.set_rollback(True)
            return False, unavailable_days, None, datelist
        session = tournamentsession.objects.create( user=user,ground=ground,start_date=start_date,end_date=end_date, session_type=session_type,defaults={'expires_at': timezone.now() + timedelta(minutes=15)})
        reservation_objects = []
        slot_lists = [] 
        for day in datelist:
            if day["status"] != "available":
                continue
            d = day["date"]
            day_slots = slots.objects.filter(ground=ground, date=d)
            if session_type == "full_day":
                selected_slots = day_slots
            elif session_type == "morning":
                selected_slots = day_slots.filter(starttime__lt=time(12, 0))
            elif session_type == "evening":
                selected_slots = day_slots.filter(starttime__gte=time(12, 0),
                                                  starttime__lt=time(18, 0))
            elif session_type == "night":
                selected_slots = day_slots.filter(starttime__gte=time(18, 0))
            selected_slots.update(is_blocked=True, blocked_at=timezone.now())
            rt = reservetournament(
                session=session,
                ground=ground,
                date=d,
                status="reserved"
            )
            reservation_objects.append(rt)
            slot_lists.append(list(selected_slots))
        created_reservations = reservetournament.objects.bulk_create(reservation_objects)
        for rt, slots_for_day in zip(created_reservations, slot_lists):
            rt.slots.set(slots_for_day)
        return True, None, session.id, datelist
            
@transaction.atomic
def chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay):
    cleanexpiredsessions()
    if not request.user.is_authenticated:
        return {'success': False, 'message': 'Please log in to continue booking.'}
    user = request.user
    session = reservationsession.objects.get_or_create(
        user=user,
        ground=ground,
        date=date_obj,
        defaults={'expires_at': timezone.now() + timedelta(minutes=15)}
    )
    availableslots = slots.objects.select_for_update(skip_locked=True).filter(
        ground=ground, date=date_obj, is_blocked=False, is_booked=False
    )
    available_slot_strings = set()
    slotmap={}
    for s in availableslots:
        available_slot_strings.add(f"{s.starttime.strftime('%I:%M %p')} - {s.endtime.strftime('%I:%M %p')}")
        slotmap[(s.starttime, s.endtime)]=s
    matchslots = []
    if len(userslots) >= userneedstoplay:
        for slot_str in userslots:
            try:
                start_str, end_str = slot_str.split(" - ")
                start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
                end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
            except Exception:
                return {'success': False, 'message': f"Invalid slot format: {slot_str}"}
            slot_obj = slotmap.get((start_time, end_time))
            if slot_obj:
                matchslots.append(slot_obj)
            else:
                latitude = ground.latitude
                longitude = ground.longitude
                rating = ground.rating or 0
                nearby_grounds = Ground.objects.all()
                nearby_grounds = findgroundsnear(nearby_grounds, 5, latitude, longitude).filter(rating__gte=rating)
                altgrounds = []
                for g in nearby_grounds:
                    av = slots.objects.filter(ground=g, date=date_obj, is_blocked=False, is_booked=False)
                    if all(
                        av.filter(
                            starttime=datetime.strptime(s.split(" - ")[0].strip(), "%I:%M %p").time(),
                            endtime=datetime.strptime(s.split(" - ")[1].strip(), "%I:%M %p").time()
                        ).exists()
                        for s in userslots
                    ):
                        altgrounds.append(g)
                if altgrounds:
                   return {
                      'success': False,
                      "message": (
                        f"Slot {slot_str} is not available at {ground.name}. "
                        f"Available slots here are: {sorted(list(available_slot_strings))}"
                         ),
                        'alternative_grounds': altgrounds
                        }
                return {
                    'success': False,
                    'message': f"Slot {slot_str} not available in {ground.name}. Available slots: {sorted(list(available_slot_strings))}"
                }
    else:
        avail_flags = [1 if s in available_slot_strings else 0 for s in userslots]
        target = userneedstoplay
        cnt = 0
        start_idx = 0
        found = False
        for i, val in enumerate(avail_flags):
            if val == 1:
                if cnt == 0:
                    start_idx = i
                cnt += 1
            else:
                cnt = 0
            if cnt == target:
                found = True
                break
        if not found:
            return {'success': False, 'message': 'Could not find a contiguous block of requested length.'}
        for i in range(start_idx, start_idx + target):
            slot_str = userslots[i]
            start_str, end_str = slot_str.split(" - ")
            start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
            end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
            slot_obj = availableslots.filter(starttime=start_time, endtime=end_time).first()
            if slot_obj:
                matchslots.append(slot_obj)
            else:
                return {'success': False, 'message': 'Race condition: slot became unavailable.'}
    for slot in matchslots:
        if slot.is_blocked or slot.is_booked:
            transaction.set_rollback(True)
            return {'success': False, 'message': 'Slot already reserved by another user. Please refresh.'}
    now = timezone.now()
    reserved_objs = []
    for slot in matchslots:
        reserved_objs.append(reservedslots(session=session, slot=slot, status='reserved'))
        slot.is_blocked = True
        slot.blocked_at = now
    reservedslots.objects.bulk_create(reserved_objs)
    slots.objects.bulk_update(matchslots, ['is_blocked', 'blocked_at'])
    return {
        'success': True,
        'message': 'Slots reserved successfully.',
        'reserved_slots': [r.id for r in reservedslots.objects.filter(session=session)],
        'session_id':session.id
      }

