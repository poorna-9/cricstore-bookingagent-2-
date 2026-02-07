from datetime import time, date, datetime, timedelta
import json
from django.urls import reverse
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render,get_object_or_404, redirect
from .models import *
from django.views.decorators.csrf import csrf_exempt
from .document import GroundDocument
import requests
import logging
logger = logging.getLogger(__name__)
from .utils import db_retry
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
import logging
logger = logging.getLogger(__name__)

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

from datetime import datetime, time, timedelta

def timingstoslots(timings, sporttype=None, groundorturf="turf", am_pm=None, shift="evening", constraint="between"):
    shift_ampm = {
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
    if shift and am_pm is None:
        am_pm = shift_ampm.get(shift)
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
        endtime, starttime = starttime, opening_time
    slotduration = timedelta(hours=3.5) if groundorturf == "ground" else timedelta(hours=1)
    current = datetime.combine(datetime.today(), starttime)
    end_dt = datetime.combine(datetime.today(), endtime)
    while current + slotduration <= end_dt:
        slot_end = current + slotduration
        userslots.append(f"{current.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}")
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
import re
from datetime import datetime, timedelta, date
def parse_natural_date(text):
    text = normalize_date_text(text)
    today = datetime.now().date()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    text = text.lower().strip()
    text = re.sub(r'\b(on|at|by|the)\b', '', text).strip()
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)

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
    current_year = today.year
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(year=current_year).date()
        except ValueError:
            pass
    return None
def infer_ampm(hour, shift=None, am_or_pm=None):
    if am_or_pm:
        return am_or_pm.upper()
    if shift in ("afternoon", "evening", "night"):
        return "PM"
    if shift == "morning":
        return "AM"
    return "PM" if hour >= 6 else "AM"
from datetime import datetime, time
def normalize_timings_text(t):
   if not t:
     return t
   t = t.lower().strip()
   t = re.sub(r'between\s+(\d+)\s+and\s+(\d+)', r'\1-\2', t)
   t = re.sub(r'from\s+(\d+)\s+to\s+(\d+)', r'\1-\2', t)
   t = re.sub(r'(\d+)\s+to\s+(\d+)', r'\1-\2', t)
   return t

def parse_natural_timings(timings, shift=None, am_or_pm=None):
    opening = time(6, 0)
    closing = time(23, 0)
    if not timings or not any(c.isdigit() for c in timings):
        timings = ""
    if not timings and shift:
        return {
            "morning": (opening, time(11, 0)),
            "afternoon": (time(11, 0), time(15, 0)),
            "evening": (time(15, 0), time(19, 0)),
            "night": (time(19, 0), closing),
        }.get(shift, (opening, closing))
    if timings:
        timings = normalize_timings_text(timings)
        print("Normalized timings:", timings)
    if "-" in timings:
        start, end = timings.split("-")
        start, end = start.strip(), end.strip()
        def parse_part(part):
            if "am" in part.lower() or "pm" in part.lower():
                return datetime.strptime(part.upper(), "%I %p").time()
            hour = int(part.split(":")[0])
            if hour > 12:
                return time(hour, 0)
            inferred = infer_ampm(hour, shift, am_or_pm)
            part = f"{part} {inferred}"
            return datetime.strptime(part.upper(), "%I %p").time()
        return parse_part(start), parse_part(end)
    start = timings.strip()
    if "am" in start.lower() or "pm" in start.lower():
        start_time = datetime.strptime(start.upper(), "%I %p").time()
    else:
        hour = int(start.split(":")[0])
        inferred = infer_ampm(hour, shift, am_or_pm)
        start_time = datetime.strptime(f"{start} {inferred}".upper(), "%I %p").time()
    if shift == "morning":
        return start_time, time(12, 0)
    if shift == "afternoon":
        return start_time, time(17, 0)
    if shift == "evening":
        return start_time, time(21, 0)
    if shift == "night":
        return start_time, closing
    print("opening", opening, "closing", closing)
    return opening, closing


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
        slot_ids = [int(s) for s in selectedslots.split(',') if s]
        selected_slot_objs = slots.objects.filter(id__in=slot_ids)
        total = sum(slot.price for slot in selected_slot_objs)
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
            userreservedslots = [rs.slot.id for rs in reservedslots.objects.filter(session=usersession, status='reserved')]
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
              "tournament_days__session__user_id", flat=True
            ).distinct()
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

@csrf_exempt
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

        valid_types = dict(
            reservetournament._meta.get_field("session_type").choices
        )
        if session_type not in valid_types:
            return JsonResponse({"success": False, "message": "Invalid session type"})
        with transaction.atomic():
            session = tournamentsession.objects.select_for_update().filter(
                user=user,
                ground=ground,
                expires_at__gt=timezone.now()
            ).first()
            if not session:
                session = tournamentsession.objects.create(
                    user=user,
                    ground=ground,
                    start_date=date_obj,
                    end_date=date_obj,
                    expires_at=timezone.now() + timedelta(minutes=15)
                )
            existing = reservetournament.objects.filter(
                session=session,
                date=date_obj
            ).first()

            if existing:
                blocked = existing.blocked_slots.select_for_update()
                blocked.update(is_blocked=False, blocked_at=None)
                existing.blocked_slots.clear()
                existing.delete()
                remaining = reservetournament.objects.filter(session=session)
                if remaining.exists():
                    session.start_date = remaining.order_by("date").first().date
                    session.end_date = remaining.order_by("-date").first().date
                    session.save()
                else:
                    session.delete()

                return JsonResponse({"success": True, "action": "unreserved"})
            if reservetournament.objects.filter(
                ground=ground,
                date=date_obj,
                status__in=["reserved", "booked"]
            ).exclude(session=session).exists():
                return JsonResponse({
                    "success": False,
                    "message": "Day already reserved by another user"
                })

            SHIFT_MAP = {
                "morning": ["morning"],
                "afternoon": ["afternoon"],
                "evening": ["evening"],
                "night": ["night"],
                "full_day": ["morning", "afternoon", "evening", "night"]
            }
            selected_slots = slots.objects.select_for_update().filter(
                ground=ground,
                date=date_obj,
                shift__in=SHIFT_MAP[session_type]
            )
            available = selected_slots.filter(
                is_booked=False,
                is_blocked=False
            )
            if selected_slots.count() != available.count():
                return JsonResponse({
                    "success": False,
                    "message": "One or more slots in this shift are already reserved"
                })
            rt = reservetournament.objects.create(
                session=session,
                ground=ground,
                date=date_obj,
                status="reserved",
                session_type=session_type
            )
            rt.blocked_slots.set(selected_slots)
            selected_slots.update(
                is_blocked=True,
                blocked_at=timezone.now()
            )
            session.start_date = min(session.start_date, date_obj)
            session.end_date = max(session.end_date, date_obj)
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
    expired_rts = reservetournament.objects.filter(session__in=expired_sessions)
    slots.objects.filter(
        tournament_days__in=expired_rts
    ).update(is_blocked=False, blocked_at=None)
    expired_rts.delete()
    expired_sessions.delete()
    

def gettournamentreserveddays(request):
    ground_id = request.GET.get("ground_id")
    if not ground_id:
        return JsonResponse({"success": False, "message": "Missing ground_id"})
    ground = get_object_or_404(Ground, id=ground_id)
    cleantournamentexpiredsessions()
    cleanexpiredsessions()  
    user = request.user if request.user.is_authenticated else None
    today = date.today()
    end_date = today + timedelta(days=29)
    user_reserved = set()
    others_reserved = set()
    booked = set()
    tournament_reservations = reservetournament.objects.filter(
        ground=ground,
        date__range=(today, end_date),
        session__expires_at__gt=timezone.now()
    ).select_related("session", "session__user")
    for r in tournament_reservations:
        day = str(r.date)
        if r.status == "booked":
            booked.add(day)
        elif user and r.session.user_id == user.id:
            user_reserved.add(day)
        else:
            others_reserved.add(day)
    blocked_days = (
        slots.objects.filter(
            ground=ground,
            date__range=(today, end_date),
            is_blocked=True
        )
        .values_list("date", flat=True)
        .distinct()
    )
    for d in blocked_days:
        day = str(d)
        if day not in booked and day not in user_reserved:
            others_reserved.add(day)
    return JsonResponse({
        "success": True,
        "user_reserved": list(user_reserved),
        "others_reserved": list(others_reserved),
        "booked": list(booked),
    })

@csrf_exempt
@db_retry(max_attempts=3)
def reserveslot(request):
    logger.info("reserveslot called user=%s", request.user.id if getattr(request, 'user', None) and request.user.is_authenticated else None)
    try:
        if request.method != "POST":
            return JsonResponse({'success': False, 'message': 'Invalid request method'})
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'User not authenticated'})
        user = request.user
        groundid = request.POST.get('ground_id')
        slotid = request.POST.get('slot_id')
        date_str = request.POST.get('date')
        if not (groundid and slotid and date_str):
            return JsonResponse({'success': False, 'message': 'Missing parameters'})

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            ground = Ground.objects.get(id=groundid)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid input'})
        cleanexpiredsessions()
        cleantournamentexpiredsessions()
        session, _ = reservationsession.objects.get_or_create(
            user=user,
            ground=ground,
            date=date_obj,
            defaults={'expires_at': timezone.now() + timedelta(minutes=15)}
        )
        with transaction.atomic():
            slot = slots.objects.select_for_update().get(
                id=slotid,
                ground=ground,
                date=date_obj
            )
            reserved_slot = reservedslots.objects.filter(
                session=session,
                slot=slot
            ).first()
            if reserved_slot:
                reserved_slot.delete()
                slot.is_blocked = False
                slot.blocked_at = None
                slot.save()
                return JsonResponse({'success': True, 'action': 'unselected'})
            if reservedslots.objects.filter(
                slot=slot,
                status='reserved',
                session__expires_at__gt=timezone.now()
            ).exists() or slot.is_booked:
                return JsonResponse({
                    'success': False,
                    'message': 'Slot already reserved or booked'
                })
            reservedslots.objects.create(
                session=session,
                slot=slot,
                status='reserved'
            )
            slot.is_blocked = True
            slot.blocked_at = timezone.now()
            slot.save()
        logger.info("reserveslot success user=%s session=%s slot=%s", user.id, session.id, slotid)
        return JsonResponse({
            'success': True,
            'action': 'selected',
            'session_id': session.id
        })
    except Exception as e:
        logger.exception("reserveslot failed: %s", e)
        return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)

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
    cleantournamentexpiredsessions()
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
    PRICE_MAP = {
        "morning": "t_morning_price",
        "afternoon": "t_afternoon_price",
        "evening": "t_evening_price",
        "night": "t_night_price",
    }

    t_session = get_object_or_404(
        tournamentsession,
        id=session_id,
        user=request.user,
        expires_at__gt=timezone.now()
    )

    reserved_days = (
        reservetournament.objects
        .filter(session=t_session, status="reserved")
        .prefetch_related("blocked_slots")
    )
    total_amount = 0
    breakdown = []   
    for rd in reserved_days:
        shifts_used = (
            rd.blocked_slots
            .values_list("shift", flat=True)
            .distinct()
        )
        day_total = 0
        for shift in shifts_used:
            price_field = PRICE_MAP.get(shift)
            if not price_field:
                continue
            shift_price = getattr(t_session.ground, price_field, 0) or 0
            day_total += shift_price
        total_amount += day_total
        breakdown.append({
            "date": rd.date,
            "shifts": list(shifts_used),
            "amount": day_total
        })
    pay = payment.objects.create(
        user=request.user,
        tournament_session=t_session,
        amount=total_amount
    )

    order = client.order.create({
        "amount": int(total_amount * 100),
        "currency": "INR",
        "receipt": f"tournament_{pay.id}",
    })

    pay.order_id = order["id"]
    pay.save(update_fields=["order_id"])

    return render(
        request,
        "bookings/tournamentcheckout.html",
        {
            "session": t_session,
            "reserved": reserved_days,
            "total": total_amount,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "order_id": order["id"],
            "ground": t_session.ground,
        }
    )


def checkoutpage(request, session_id):
    session = reservationsession.objects.get(
        id=session_id,
        user=request.user
    )
    reserved = reservedslots.objects.filter(
        session=session,
    )
    if not reserved.exists():
        return redirect("grounds_page")
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
                for slot in rd.blocked_slots.all():
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
        lat=request.POST.get("lat")
        lon=request.POST.get("lon")
        if lat and lon:
            request.session["user_lat"] = float(lat)
            request.session["user_lon"] = float(lon)
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

def detect_booking_type(query):
    keywords = ["tournament", "league"]
    q = query.lower()
    return "tournament" if any(k in q for k in keywords) else "normal_booking"
import re
from datetime import datetime, timedelta
from django.utils import timezone

import re

def normalize_date_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\b(on|at|by|the|from|to)\b', ' ', text)
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)
    keywords = ["this", "next", "coming", "upcoming", "current"]
    weekdays = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday"
    ]
    SHIFTS=["morning", "afternoon", "evening", "night"]
    for k in keywords:
        for d in weekdays:
            text = re.sub(rf'\b{k}{d}\b', f"{k} {d}", text)
    text = re.sub(r'\b(this|next)(weekend)\b', r'\1 \2', text)
    for d in weekdays + ["weekend"]:
        for s in SHIFTS:
            text = re.sub(rf'\b{d}{s}\b', f"{d} {s}", text)
    for k in keywords:
        for d in weekdays + ["weekend"]:
            for s in SHIFTS:
                text = re.sub(
                    rf'\b{k}{d}{s}\b',
                    f"{k} {d} {s}",
                    text
                )
    text = re.sub(r'\s+', ' ', text).strip()
    return text
SHIFTS=["morning", "afternoon", "evening", "night"]
def strip_shifts(text):
    if not text:
        return ""
    pattern = r'\b(' + '|'.join(SHIFTS) + r')\b'
    return re.sub(pattern, '', text).strip()


def parse_natural_date_tournament(text):
    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    if not text:
        return None
    text = normalize_date_text(text)
    today = timezone.now().date()
    for fmt in (
        "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
        "%d %b %Y", "%d %B %Y",
        "%d-%m-%y", "%d/%m/%y"
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d %b", "%d %B"):
        try:
            parsed = datetime.strptime(text, fmt)
            current_year = today.year
            if parsed.month < today.month or (parsed.month == today.month and parsed.day < today.day):
                current_year += 1
            return parsed.replace(year=current_year).date()
        except ValueError:
            pass
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "day after tomorrow":
        return today + timedelta(days=2)
    words = text.split()
    current_day = today.weekday()
    if len(words) == 1 and words[0] in WEEKDAYS:
        words = ["this", words[0]]
    if "weekend" in words:
        days_until_sat = (5 - current_day) % 7
        if "next" in words:
            days_until_sat += 7
        return today + timedelta(days=days_until_sat)
    if words[-1] in WEEKDAYS:
        target = WEEKDAYS[words[-1]]
        delta = (target - current_day) % 7
        if delta == 0 :
            if words[0] in ["this", "current"]:
                return today
            elif words[0] in ["next", "upcoming"]:
                delta = 7
        return today + timedelta(days=delta)
    if text.isdigit():
        day = int(text)
        month = today.month
        year = today.year
        if day < today.day:
            month += 1
            if month > 12:
                month = 1
                year += 1
        return datetime(year, month, day).date()
    return None
def parse_date_constraints(start,end,total_days):
    duration_days = int(total_days) if total_days and str(total_days).isdigit() else None
    if start and "weekend" in start.lower():
        today = timezone.now().date()
        current_day = today.weekday()
        days_until_sat = (5 - current_day) % 7
        if "next" in start.lower():
            days_until_sat += 7
        start_date = today + timedelta(days=days_until_sat)
        if not end:
            end_date = start_date + timedelta(days=1)
            return {"success": True, "start": start_date, "end": end_date}
        else:
            end_clean=strip_shifts(end)
            end_date = parse_natural_date_tournament(end_clean)
            if end_date and end_date >= start_date:
                return {"success": True, "start": start_date, "end": end_date}
            else:
                end_date = start_date + timedelta(days=7)
                if end_date >= start_date:
                    return {"success": True, "start": start_date, "end": end_date}
                else:
                    return {"success": False, "message": "End date must be after start date."}
    start_clean = strip_shifts(normalize_date_text(start))
    end_clean = strip_shifts(normalize_date_text(end))
    start_date = parse_natural_date_tournament(start_clean)
    end_date = parse_natural_date_tournament(end_clean)
    today= timezone.now().date()
    if start_date and end_date and start_date <= end_date:
        return {"success": True, "start": start_date, "end": end_date}
    if start_date and end_date and start_date > end_date:
        end_date = end_date + timedelta(days=7)
        return {"success": True, "start": start_date, "end": end_date}
    if start_date and duration_days:
        return {
            "success": True,
            "start": start_date,
            "end": start_date + timedelta(days=duration_days - 1)
        }
    return {
        "success": False,
        "message": "Unable to understand tournament dates. Please specify start and end clearly."
    }

def shifts(allowedshifts, start, end):
    default = ["morning", "afternoon", "evening", "night"]
    result = {}
    constraint = allowedshifts.get("constraint_type") if allowedshifts else ""
    if constraint == "only":
        allowed = allowedshifts.get("start_day", [])
        current = start
        while current <= end:
            result[current] = allowed.copy()
            current += timedelta(days=1)
        return result
    current = start
    dayindex = 0
    totaldays = (end - start).days
    while current <= end:
        if dayindex == 0:
            if allowedshifts and allowedshifts.get("start_day"):
                idx = default.index(allowedshifts["start_day"][0])
                result[current] = default[idx:]
            else:
                result[current] = default.copy()
        elif dayindex == totaldays:
            if allowedshifts and allowedshifts.get("end_day"):
                idx = default.index(allowedshifts["end_day"][0])
                result[current] = default[:idx + 1]
            else:
                result[current] = default.copy()
        else:
            result[current] = default.copy()
        current += timedelta(days=1)
        dayindex += 1
    return result


def calculatematchtimings(overs):
    balltime=1
    inningsbreak=20
    oneover_minutes=4.5 
    return (overs*oneover_minutes) + inningsbreak
SHIFT_DURATION_MINUTES = {
    "morning": 240,     
    "afternoon": 240, 
    "evening": 300,    
    "night": 300,       
}
timings={
    "morning":(time(6,0),time(11,0)),
    "afternoon":(time(11,0),time(15,0)),
    "evening":(time(15,0),time(19,0)),
    "night":(time(19,0),time(23,59))
}

from functools import lru_cache
SHIFT_LIST = ["morning", "afternoon", "evening", "night"]
SHIFT_BIT = {s: 1 << i for i, s in enumerate(SHIFT_LIST)}

def check(ground, start, end, shiftperday, budget, matches, overs, show=False):
    timepermatch = calculatematchtimings(overs)
    matches_per_shift = {
        shift: (SHIFT_DURATION_MINUTES[shift] // timepermatch
                if SHIFT_DURATION_MINUTES[shift] >= timepermatch else 0)
        for shift in SHIFT_LIST
    }
    avail_mask_per_day = {}
    total_possible_matches = 0
    current = start
    while current <= end:
        day_slots = Slot.objects.filter(ground=ground, date=current)
        slotbyshift = {}
        for slot in day_slots:
            slotbyshift.setdefault(slot.shift, []).append(slot)
        day_mask = 0
        for shift in SHIFT_LIST:
            shift_slots = slotbyshift.get(shift, [])
            if not shift_slots:
                continue
            blocked = any(s.is_booked or s.is_blocked for s in shift_slots)
            if not blocked:
                day_mask |= SHIFT_BIT[shift]
                total_possible_matches += matches_per_shift[shift]

        avail_mask_per_day[current] = day_mask
        current += timedelta(days=1)
    if total_possible_matches < matches:
        return {
            "success": False,
            "message": "This tournament cannot be played within the given dates"
        }
    dates = list(avail_mask_per_day.keys())
    max_matches_per_day = sum(matches_per_shift.values())
    @lru_cache(None)
    def dfs(index, currmatches, currbudget):
        if currmatches >= matches:
            return (True, []) if show else (0, [])
        if index == len(dates):
            return (False, None) if show else (float("inf"), None)
        remaining_days = len(dates) - index
        if currmatches + remaining_days * max_matches_per_day < matches:
            return (False, None) if show else (float("inf"), None)
        current_date = dates[index]
        allowed_mask = avail_mask_per_day[current_date]
        user_mask = 0
        for s in shiftperday.get(current_date, []):
            user_mask |= SHIFT_BIT[s]
        valid_mask = allowed_mask & user_mask
        res = dfs(index + 1, currmatches, currbudget)
        if show and res[0]:
            return True, res[1]
        if not show and res[0] < float("inf"):
            return res
        submask = valid_mask
        while submask:
            cost = 0
            gained = 0
            shifts = []
            for shift in SHIFT_LIST:
                if submask & SHIFT_BIT[shift]:
                    price = getattr(ground, f"t_{shift}_price", None)
                    if price is None:
                        break
                    cost += price
                    gained += matches_per_shift[shift]
                    shifts.append(shift)
            else:
                if currbudget + cost <= budget:
                    nxt = dfs(
                        index + 1,
                        currmatches + gained,
                        currbudget + cost
                    )

                    if show and nxt[0]:
                        return True, [(current_date, shifts)] + nxt[1]

                    if not show:
                        total_cost = cost + nxt[0]
                        if total_cost < res[0]:
                            res = (total_cost, [(current_date, shifts)] + nxt[1])
            submask = (submask - 1) & valid_mask
        return res
    result = dfs(0, 0, 0)
    if show:
        return {
            "success": result[0],
            "total_cost": None,
            "schedule": result[1]
        }
    else:
        if result[1] is None:
            return {
                "success": False,
                "total_cost": None,
                "schedule": None,
                "message": "No valid shift combination found within budget"
            }
        return {
            "success": True,
            "total_cost": result[0],
            "schedule": result[1]
        }


def showavailability(grounds, start, end, shiftsperday):
    available_grounds = []
    for ground in grounds:
        is_valid = True
        current = start
        while current <= end:
            day_slots = slots.objects.filter(ground=ground, date=current)
            slotbyshift = {}
            for slot in day_slots:
                slotbyshift.setdefault(slot.shift, []).append(slot)
            for required_shift in shiftsperday.get(current, []):
                shift_slots = slotbyshift.get(required_shift, [])
                if not shift_slots:
                    is_valid = False
                    break
                if any(slot.is_booked or slot.is_blocked for slot in shift_slots):
                    is_valid = False
                    break
            if not is_valid:
                break
            current += timedelta(days=1)
        if is_valid:
            available_grounds.append(ground)
    return available_grounds

from django.utils.dateparse import parse_datetime
from django.db.models import Q, Avg
def price_lte_q(value):
  return (
  Q(morning_price__lte=value) |
  Q(afternoon_price__lte=value) |
  Q(evening_price__lte=value) |
  Q(night_price__lte=value)
  )

def parsehours(hours_text):
    wordtonum={
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10
    }
    if not hours_text:
      return None
    text = str(hours_text).lower()
    digit_match=re.search(r'(\d+)',text)
    if digit_match:
        return int(digit_match.group())
    for word, value in wordtonum.items():
       if word in text:
         return value
    return None
 
    
def price_gte_q(value):
  return (
  Q(morning_price__gte=value) |
  Q(afternoon_price__gte=value) |
  Q(evening_price__gte=value) |
  Q(night_price__gte=value)
  )

from .models import slots as Slot
def userquerychatbot(request):
    query = request.GET.get('query', '')
    mode=request.GET.get("mode")
    if not mode:
        return JsonResponse({'message':"Mode parameter is missing."})
    rawrequired=request.GET.get("required_fields")
    if rawrequired:
        try:
          required_fields = json.loads(rawrequired)
        except json.JSONDecodeError:
          required_fields = []
    else:
        required_fields = []
    if mode=="normal_booking":
      booking_type="normal_booking"
      print("Required fields sent to backend:", required_fields)
      output = interpretgroundquery(query,booking_type,required_fields)
      print("Chatbot Output:",output)
      if "chatcontext" not in request.session:
        request.session["chatcontext"] = {}
      context = request.session["chatcontext"]
      print("previouscontext:", context)
      lasttimeraw=context.get("last_modified_at")
      lasttime = parse_datetime(lasttimeraw) if lasttimeraw else None
      if lasttime and timezone.now() > lasttime + timedelta(minutes=10):
        print("Session cleared due to timeout.")
        request.session["chatcontext"] = {}
        context = request.session["chatcontext"]
      if output.get("intent")=="unknown" and "intent" in context:
          output["intent"]=context["intent"]
      raw_intent = (output.get("intent") or "").lower()
      print("raw_intent:", raw_intent)
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
      if raw_intent in ["show_ground","book","cancel_booking","reschedule","ground_info"]:
          normalized_intent = raw_intent
      else:
         normalized_intent = INTENT_MAP.get(raw_intent, "unknown")
      print("Normalized Intent:", normalized_intent)
      for k,v in output.get("filters", {}).items():
        if v not in ("", None):
            context[k]=v
      print("output context:",output)
      if normalized_intent != "unknown":
        context["intent"] = normalized_intent
      context['booking_type']=output.get('booking_type')
      context["last_modified_at"]=timezone.now().isoformat()
      request.session.modified = True
      print("Updated Chatbot Context:",context)
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
        return JsonResponse({'message':"Which sport are you looking to book a ground for ?","required_fields":["sport_type"]})
      if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?,"
            return JsonResponse({
                "message": response_message,"required_fields":["ground_or_turf"],
            })
      else:
        ground_or_turf = "turf"
      context["sporttype"] = sport_type
      context["ground_or_turf"] = ground_or_turf
      request.session.modified = True
      if sport_type:
       grounds = Ground.objects.filter(sporttype__icontains=sport_type)
       print("grounds by sport_type:", grounds)
      if ground_or_turf:
          grounds=grounds.filter(types__icontains=ground_or_turf)
          print("grounds by ground_or_turf:", grounds)
      bookingtype= context.get("booking_type", "").lower().strip()
      if bookingtype=="normal_booking" and context.get("intent") == "show_ground":
        if not context.get("ground_or_turf_name"):
         if context.get("date"):
            parsed_date=parse_natural_date(context["date"])
            if not parsed_date:
             return JsonResponse({
                "message": "I couldn't understand the date. Please say something like '28 Jan' or 'tomorrow'.",
                "required_fields": ["date"]
               })
            context["date"]=parsed_date.isoformat()
         if context.get("nearme") and not context.get("radius_km"):
            context["radius_km"] = 15
            if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})      
            user_lat = float(request.session["user_lat"])
            user_lon = float(request.session["user_lon"])
            print("Finding grounds near user at:", user_lat, user_lon)
            grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
            if isinstance(grounds, list):
                ground_ids = [g.id for g in grounds]
                grounds = Ground.objects.filter(id__in=ground_ids)
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
         if not context.get("city"):
            if context.get("nearme") and not context.get("radius_km"):
              context["radius_km"] = 15
            if context.get("radius_km"):
              if not request.session.get("user_lat") or not request.session.get("user_lon"):
                html_page=render_to_string("bookings/location-detection.html",request=request)
                return JsonResponse({"message": "Please provide your location to find grounds near you.","html": html_page})      
              user_lat = float(request.session["user_lat"])
              user_lon = float(request.session["user_lon"])
              print("Finding grounds near user at:", user_lat, user_lon)
              grounds = findgroundsnear(grounds,context.get("radius_km"), user_lat, user_lon)
              if isinstance(grounds, list):
                ground_ids = [g.id for g in grounds]
                grounds = Ground.objects.filter(id__in=ground_ids)
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
            return JsonResponse({'message': "Please tell me which city you want to search grounds in.","required_fields":["city"]})
         if context.get("city"):
            grounds = grounds.filter(city__icontains=context["city"])
            print("grounds by city:", grounds)
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
            avg_price = grounds.aggregate(
              avg_morning=Avg("morning_price"),
              avg_afternoon=Avg("afternoon_price"),
              avg_evening=Avg("evening_price"),
              avg_night=Avg("night_price"),
            )
            prices = [
              avg_price["avg_morning"],
              avg_price["avg_afternoon"],
              avg_price["avg_evening"],
              avg_price["avg_night"],
             ]
            prices = [p for p in prices if p is not None]
            if prices:
              overall_avg = sum(prices) / len(prices)
            grounds = grounds.filter(price_lte_q(overall_avg))
         elif context.get("price_semantic") == "expensive" and not context.get("price"):
            avg_price = grounds.aggregate(
              avg_morning=Avg("morning_price"),
              avg_afternoon=Avg("afternoon_price"),
              avg_evening=Avg("evening_price"),
              avg_night=Avg("night_price"),
            )
            prices = [
              avg_price["avg_morning"],
              avg_price["avg_afternoon"],
              avg_price["avg_evening"],
              avg_price["avg_night"],
             ]
            prices = [p for p in prices if p is not None]
            if prices:
               overall_avg = sum(prices) / len(prices)
            grounds = grounds.filter(price_gte_q(overall_avg))
         if context.get("price"):
            max_price = float(context["price"]) + 100
            grounds = grounds.filter(price_lte_q(max_price))
         if context.get("rating"):
            grounds = grounds.filter(rating__gte=float(context["rating"]))
         cities= Ground.objects.values_list('city', flat=True).distinct()
         html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
         return JsonResponse({"message":"these are grounds based on your requirements","html": html_page})
        if context.get("ground_or_turf_name"):
            if not context.get("area"):
                return JsonResponse({'message': "Please tell me which area this ground is in","required_fields":["area"]})
            ground = Ground.objects.filter(
                name__icontains=context["ground_or_turf_name"],
                city__icontains=context["city"],
                address__icontains=context["area"]
            ).first()
            if not ground:
                grounds=Ground.objects.filter(address__icontains=context["area"])
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
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
            time_slots = Slot.objects.filter(ground=ground, date=date_obj).order_by('starttime')
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
        if not context.get("date"):
            return JsonResponse({
               "message": "Please tell me the date you want to book.",
               "required_fields": ["date"]
           })
        date_str = context["date"]
        parsed_date = parse_natural_date(date_str)
        if not parsed_date:
         return JsonResponse({
        "message": f"I couldn’t understand the date '{date_str}'. Please specify a date like '28 Jan', 'tomorrow', or '2026-01-28'.",
        "required_fields": ["date"]
        })
        date_obj = parsed_date
        context["date"] = date_obj.isoformat()
        request.session.modified = True
        required_fields = ["ground_or_turf_name", "city", "area", "timings"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}.","required_fields":[field]})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        )
        if ground.count() == 1:
            ground = ground.first()
            print(ground)
        elif ground.count() > 1:
           cities = Ground.objects.values_list('city', flat=True).distinct()
           html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
           return JsonResponse({
           "message": "I found multiple grounds in that area. Please select one.",
            "html": html_page
           })
        else:
            cities = Ground.objects.values_list('city', flat=True).distinct()
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page=render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({'message': "There is no ground of that name ,I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        try:
            date_obj = datetime.strptime(context["date"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        constraint = context.get("constraint_type", "between")
        userslots = timingstoslots(
            context.get("timings"), context.get("sporttype"),context.get("ground_or_turf"), context.get("am_pm"),context.get("shift"),constraint
        )
        if not userslots:
            return JsonResponse({
                 "message": "I couldn’t understand the time. Please specify a time like '5 to 7 evening'.","required_fields":["timings"]
                })
        if len(userslots) > 2 and not context.get("hours"):
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?","required_fields":["hours"]})
        if context.get("hours"):
            hrs=parsehours(context.get("hours"))
            if not hrs:
                return JsonResponse({'message': "I couldn't understand the number of hours you want to play. Please specify a number like '2' or 'three'.","required_fields":["hours"]})
            userneedstoplay = hrs
        else:
            userneedstoplay=len(userslots)
        print("User Slots:", userslots)
        output_res = chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay)
        if not isinstance(output_res,dict):
            return JsonResponse({'message': 'Error reserving slots. Please try again.'})
        if not output_res.get("success"):
            message=output_res.get("message")
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if output_res.get('alternative_grounds'):
                altgrounds=output_res['alternative_grounds']
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
                return JsonResponse({"message":output_res.get("message"),"html": html_page})
            else:
                return JsonResponse({"message":output_res.get("message")})
        return JsonResponse({"message": "Slots reserved successfully. Redirecting to checkout…","redirect_url": reverse("checkout", args=[output_res.get("session_id")])})
      if bookingtype=="normal_booking" and context.get("intent") in ["ground_info", "ground_facilities", "ground_status"]:
        info_result = handle_ground_info(context)
        return JsonResponse(info_result)   

    if mode=="cancellation":
      context["intent"]="cancel_booking"
      request.session.modified = True
      if context.get("intent")=="cancel_booking":
        pastorders=Orders.objects.filter(user=request.user,date__gt=timezone.now().date(),booked=True).order_by("date")
        if not pastorders.exists():
            return JsonResponse({"message": "You have no upcoming bookings to cancel."})
        booking_id=request.GET.get("booking_id")
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
             reservedslots.objects.filter(slot__in=booking.slotsbooked.all()).delete()
             for slot in booking.slotsbooked.select_for_update():
                 slot.is_blocked=False
                 slot.is_booked=False
                 slot.blocked_at=None
                 slot.save(update_fields=["is_blocked","is_booked","blocked_at"])
             booking.booked=False
             booking.status="Cancelled"
             booking.save(update_fields=["booked","status"])
             return JsonResponse({"message": f"Your booking is cancelled successfully. Refund of ₹{booking.price} is initiated."})
            elif booking.Tournament_or_normal=="tournament":
                session_id=booking.session
                session = tournamentsession.objects.filter(id=session_id, user=request.user).first()
                if not session:
                    return JsonResponse({"message": "Invalid booking selected."})
                for days in reservetournament.objects.filter(session=session, status="booked"):
                    for slot in days.blocked_slots.all():
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
    if mode == "reschedule":
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
            html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
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
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":context.get("city")},request=request)
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
        return JsonResponse({
            "message": "Tournament booking rechedule would be added soon sorry.",})
    #############################################################################################################################################   
    if mode=="tournament":
      mode="tournament_booking"
      rawrequired=request.GET.get("required_fields")
      if rawrequired:
        try:
          required_fields = json.loads(rawrequired)
        except json.JSONDecodeError:
          required_fields = []
      else:
        required_fields = []
      booking_type="tournament_booking"
      print("Required fields sent to backend:", required_fields)
      output = interpretgroundquery(query,booking_type,required_fields)  
      print("Chatbot Output:",output)
      if "chatcontext" not in request.session:
        request.session["chatcontext"] = {}
      context = request.session["chatcontext"]
      print("previouscontext:", context)
      lasttimeraw=context.get("last_modified_at")
      lasttime = parse_datetime(lasttimeraw) if lasttimeraw else None
      if lasttime and timezone.now() > lasttime + timedelta(minutes=10):
        print("Session cleared due to timeout.")
        request.session["chatcontext"] = {}
        context = request.session["chatcontext"]
      if output.get("intent")=="unknown" and "intent" in context:
          output["intent"]=context["intent"]
      raw_intent = (output.get("intent") or "").lower()
      print("raw_intent:", raw_intent)
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
      if raw_intent in ["show_ground","book","cancel_booking","reschedule","ground_info"]:
          normalized_intent = raw_intent
      else:
         normalized_intent = INTENT_MAP.get(raw_intent, "unknown")
      print("Normalized Intent:", normalized_intent)
      for k,v in output.get("filters", {}).items():
        if k=="shifts":
           if any(v.get(h) for h in ("start_day", "middle_days", "end_day")):
            context[k] = v
           continue
        if v not in ("", None):
            context[k]=v
      print("output context:",output)
      if normalized_intent != "unknown":
        context["intent"] = normalized_intent
      context['booking_type']=output.get('booking_type')
      context["last_modified_at"]=timezone.now().isoformat()
      request.session.modified = True
      print("Updated Chatbot Context:",context)
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
        return JsonResponse({'message': "What sport is this tournament for?", "required_fields":["sport_type"]})
      if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?,"
            return JsonResponse({
                "message": response_message,"required_fields":["ground_or_turf"],
            })
      if not ground_or_turf:
          response_message = f"For tournaments, would you like to book a ground or a turf?"
          return JsonResponse({
             "message": response_message,
             "required_fields": ["ground_or_turf"]
            })
      request.session.modified = True
      if sport_type:
       grounds = Ground.objects.filter(sporttype__icontains=sport_type)
       print("grounds by sport_type:", grounds)
      if ground_or_turf:
          grounds=grounds.filter(types__icontains=ground_or_turf)
          print("grounds by ground_or_turf:", grounds)
      bookingtype= context.get("booking_type", "").lower().strip()
      if booking_type=="tournament_booking" and context.get("intent") == "show_ground":   
        if not context.get("ground_or_turf_name"):
          if context.get("nearme") and not context.get("radius_km"):
              context["radius_km"] = 15
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
            html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({"message":"these are the grounds near to you","html": html_page})
          if context.get("city"):
               grounds=grounds.filter(city__icontains=context["city"])
          if context.get("area"):
               grounds = grounds.filter(address__icontains=context["area"])
          if context.get("rating_min"):
              grounds=grounds.filter(rating__gte=float(context["rating_min"]-2))
          if context.get("rating_semantic"):
              if context.get("rating_sematic") in ["top","high","good"]:
                  grounds=grounds.filter(rating__gte=3)
              elif context.get("rating_semantic") in ["low","bad","poor"]:
                  grounds=grounds.filter(rating__lte=3)
          if context.get("start"):
             dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
             print("Parsed date constraints:", dicti)
             if not dicti["success"]:
               return JsonResponse({"message": dicti["message"]})
             start,end=dicti["start"],dicti["end"]
             shiftsperday=shifts(context["shifts"],start,end)
             context["start"]=start.isoformat()
             context["end"]=end.isoformat()
             print("Start:", start, "End:", end, "Shifts per day:", shiftsperday)
          if not context.get("budget"):
                grounds=showavailability(grounds,start,end,shiftsperday)
                if isinstance(grounds, list):
                  grounds = Ground.objects.filter(id__in=[g.id for g in grounds])
                grounds=grounds.order_by('-t_fullday_price') 
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
          if context.get("budget"):
                if not context.get("total_matches"):
                    return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
                if not context.get("overs_per_match"):
                    return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
                if not context.get("start"):
                    return JsonResponse({"message":"please provided start_date and end_date of tournament","required_fields":["start","end"]})
                valid_grounds=[]
                if context.get("start") and context.get("end"):
                 for g in grounds:
                    result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                        )
                    if result["success"]:
                           valid_grounds.append(g)
                if not valid_grounds:
                    grs=Ground.objects.filter(city=context["city"])
                    cities= Ground.objects.values_list('city', flat=True).distinct()
                    html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                    return JsonResponse({
                        "message": "No grounds can host this tournament within your budget you can check in the grounds provided","html":html_page
                        })
                grounds=valid_grounds
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })
        if context.get("ground_or_turf_name"):
            if not context.get("area") or not context.get("city"):
                return JsonResponse({"message":"please provide city and area of the ground you are looking","required_fields":["area","city"]})
            grounds = Ground.objects.filter(
              name__icontains=context.get("ground_or_turf_name")
             )
            grounds = grounds.filter(city=context["city"])
            grounds = grounds.filter(address__icontains=context["area"])
            cities = Ground.objects.values_list('city', flat=True).distinct()
            if not grounds.exists():
                fallback = Ground.objects.all()
                if context.get("city"):
                  fallback = fallback.filter(city=context["city"])
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": fallback, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                     "message": "Requested ground not found. Showing similar grounds.",
                      "html": html_page
                    })
            if len(grounds)>1:
                html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({
                     "message": "Multiple grounds of same name found. Please be more specific.",
                      "html": html_page
                    })
            ground = grounds.first()
            if not context.get("start"):
              return JsonResponse({"message": "Please provide the start date of your tournament.","required_fields":["start"]})
            dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
            if not dicti["success"]:
              return JsonResponse({"message": dicti["message"]})
            start,end=dicti["start"],dicti["end"]
            shiftsperday=shifts(context["shifts"],start,end)
            context["start"]=start.isoformat()
            context["end"]=end.isoformat()
            if not context.get("budget"):
                  today = timezone.now().date().strftime('%Y-%m-%d')
                  date_list=[]
                  for i in range(30):
                    d = timezone.now().date() + timedelta(days=i)
                    day_slots = Slot.objects.filter(ground=ground, date=d)
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
            if context.get("budget"):
                if not context.get("total_matches"):
                    return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
                if not context.get("overs_per_match"):
                    return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
                result=check(ground=ground,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                        )
                if result["success"]:
                        message="yes you can book this ground with your budget"
                        today = timezone.now().date().strftime('%Y-%m-%d')
                        date_list=[]
                        for i in range(30):
                          d = timezone.now().date() + timedelta(days=i)
                          day_slots = Slot.objects.filter(ground=ground, date=d)
                          if not day_slots.exists():
                            status = "unavailable"
                          else:
                           all_free = (not day_slots.filter(is_booked=True).exists() and not day_slots.filter(is_blocked=True).exists())
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
                else:
                        grounds=Ground.objects.filter(city=context["city"])
                        valid_grounds=[]
                        for g in grounds:
                            result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=int(context["budget"]),
                                 matches=int(context["total_matches"]) ,
                                 overs=int(context["overs_per_match"]),
                                 show=True
                            )
                            if result["success"]:
                              valid_grounds.append(g)
                        if not valid_grounds:
                          grs=Ground.objects.filter(city=context["city"])
                          cities= Ground.objects.values_list('city', flat=True).distinct()
                          html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grs, "cities": cities, "selected_city":""},request=request)
                          return JsonResponse({
                            "message": "No grounds can host this tournament within your budget,the grounds of your city are provided below you can check them out",
                            "html": html_page
                           })
                        grounds=valid_grounds
                        html_page =  render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                        return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })       
##################################################################################################################################################
      if output.get("booking_type") == "tournament_booking" and output.get("intent") in ["book", "reserve", "schedule"]:
        if not context.get("ground_or_turf_name"):
            return JsonResponse({"message":"please provide ground_or_turf_name and city and area of the ground you are looking","required_fields":["ground_or_turf_name"]})
        if not context.get("area"):
            return JsonResponse({"message":"please provide area of the ground you are looking","required_fields":["area"]})
        if not context.get("city"):
            return JsonResponse({"message":"please provide area of the ground you are looking","required_fields":["city"]})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            grounds=Ground.objects.filter(address__icontains=context["area"])
            html_page= render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
            return JsonResponse({'message': "I found multiple grounds in that area. Please select one from the list below.","html":html_page})
        if not context.get("start"):
              return JsonResponse({"message": "Please provide the start date of your tournament.","required_fields":["start"]})
        dicti = parse_date_constraints(context["start"],context.get("end"),context.get("total_days"))
        if not dicti["success"]:
            return JsonResponse({"message": dicti["message"]})
        start, end = dicti["start"], dicti["end"]
        shiftsperday = shifts(context["shifts"], start,end)
        context["start"]=start.isoformat()
        context["end"]=end.isoformat()
        if not context.get("budget"):
            dicti_no_budget=checkwithoutbudget(ground,start,end,shiftsperday)
            print("Check without budget result:", dicti_no_budget)
            if dicti_no_budget["success"]:
                plan=build_plan_from_shifts(shiftsperday)
                print(plan)
                success,session_id=booktournament(request.user,ground,plan)
                print("Booking result:", success, session_id)
                if not success:
                    return JsonResponse({"message": "cannot book someone else booked some shifts"})
                else:
                    return JsonResponse({"message": "Tournament slots reserved. Please complete payment within 15 minutes.","redirect_url": reverse("tournamentcheckout", args=[session_id])})
            else:
                grounds=Ground.objects.filter(city=context["city"])
                cities= Ground.objects.values_list('city', flat=True).distinct()
                html_page = render_to_string("partials/partialcheckpage.html",{"grounds": grounds, "cities": cities, "selected_city":""},request=request)
                return JsonResponse({"message":"these are the grounds near to you","html": html_page})
        if context.get("budget"):
            if not context.get("total_matches"):
                return JsonResponse({"message":"please provide total no of matches in the tournament","required_fields":["total_matches"]})
            if not context.get("overs_per_match"):
                return JsonResponse({"message":"please provide total no of overs per match","required_fields":["overs_per_match"]})
            dicti=check(ground=ground,
                        start=context["start"],
                        end=context["end"],
                        shiftperday=shiftsperday,
                        budget=context["budget"],
                        matches=context["total_matches"] ,
                        overs=context["overs_per_match"],
                        show=False)
            if not dicti.get("success"):
                grounds=Ground.objects.filter(city=context["city"])
                valid_grounds=[]
                for g in grounds:
                            result=check(ground=g,
                                 start=context["start"],
                                 end=context["end"],
                                 shiftperday=shiftsperday,
                                 budget=context["budget"],
                                 matches=context["total_matches"] ,
                                 overs=context["overs_per_match"],
                                 show=True
                            )
                            if result["success"] and result["schedule"]:
                              valid_grounds.append(g)
                if not valid_grounds:
                    return JsonResponse({
                            "message": "No grounds can host this tournament within your budget"
                           })
                html_page = render_to_string(
                          "partials/partialcheckpage.html",
                           {"grounds": valid_grounds, "cities": cities, "selected_city":""},
                           request=request
                           )
                return JsonResponse({
                         "message": "These grounds fit your budget and schedule",
                         "html": html_page
                        })
            else:
                if not dicti.get("schedule"):
                    return JsonResponse({
                        "message": "No valid schedule found for the tournament within your budget."
                    })
                success, session_id = booktournament(
                  user=request.user,
                  ground=ground,
                  plan=dicti["schedule"]
                )
                if not success:
                  return JsonResponse({
                      "message": "Unable to reserve tournament slots"
                    })
                else:
                    return JsonResponse({"message": "Tournament slots reserved. Please complete payment within 15 minutes.","redirect_url": reverse("checkout", args=[session_id])})
def build_plan_from_shifts(shiftsperday):
    plan = {}
    for date, shifts in shiftsperday.items():
        if shifts:
            plan[date] = shifts
    return plan
             
def checkwithoutbudget(ground, start, end, shiftperday):
    availableshiftperday = {}
    current = start
    while current <= end:
        availableshiftperday[current] = {}
        day_slots = Slot.objects.filter(ground=ground, date=current)
        slotbyshift = {}
        for slot in day_slots:
            slotbyshift.setdefault(slot.shift, []).append(slot)
        for shift in ["morning", "afternoon", "evening", "night"]:
            shift_slots = slotbyshift.get(shift, [])
            if not shift_slots:
                availableshiftperday[current][shift] = False
                continue
            is_unavailable = any(slot.is_booked or slot.is_blocked for slot in shift_slots)
            availableshiftperday[current][shift] = not is_unavailable
        required_shifts = shiftperday.get(current, [])
        for shift in required_shifts:
           if not availableshiftperday[current].get(shift, False):
             return {
            "success": False,
            "message": f"{shift} shift on {current} is not available"
             }
        current += timedelta(days=1)
    return {"success":True}

def booktournament(user, ground, plan):
    cleantournamentexpiredsessions()
    with transaction.atomic():
        session = tournamentsession.objects.create(
            user=user,
            ground=ground,
            start_date=min(plan.keys()),
            end_date=max(plan.keys()),
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        for date, shift in plan.items():
            shifts_to_filter = shift if isinstance(shift, (list, tuple)) else [shift]
            locked_slots = Slot.objects.select_for_update().filter(
                ground=ground,
                date=date,
                shift__in=shifts_to_filter
            )
            if not locked_slots.exists():
                raise Exception(f"No slots available for {date}")
            if any(sl.is_blocked==True or sl.is_booked==True for sl in locked_slots):
                raise Exception(f"Some slots already booked on {date}")
            reserve = reservetournament.objects.create(
                session=session,
                ground=ground,
                date=date,
                status="reserved"
            )
            reserve.blocked_slots.set(locked_slots)
            locked_slots.update(
                is_blocked=True,
                blocked_at=timezone.now()
            )
    return True,session.id
            
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from django.utils import timezone

@transaction.atomic
def chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay):
    logger.info(
        "chatbot_reserve_slots called user=%s ground=%s date=%s requested_slots=%s need=%s",
        request.user.id if request.user.is_authenticated else None,
        ground.id,
        date_obj,
        len(userslots),
        userneedstoplay
    )
    if not request.user.is_authenticated:
        return {'success': False, 'message': 'Please log in to continue booking.'}
    user = request.user
    now = timezone.now()
    try:
        cleanexpiredsessions()
        cleantournamentexpiredsessions()
        with transaction.atomic():
            session, _ = reservationsession.objects.select_for_update().get_or_create(
                user=user,
                ground=ground,
                date=date_obj,
                defaults={'expires_at': now + timedelta(minutes=15)}
            )
            session.expires_at = now + timedelta(minutes=15)
            session.save(update_fields=["expires_at"])
            availableslots = list(
                Slot.objects.select_for_update().filter(
                    ground=ground,
                    date=date_obj,
                    is_blocked=False,
                    is_booked=False
                )
            )
            if not availableslots:
                return {'success': False, 'message': 'No slots available.'}
            slotmap = {(s.starttime, s.endtime): s for s in availableslots}
            parsed_user_slots = []
            for slot_str in userslots:
                try:
                    start_str, end_str = slot_str.split(" - ")
                    start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
                    end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
                    parsed_user_slots.append((start_time, end_time, slot_str))
                except ValueError:
                    return {'success': False, 'message': f"Invalid slot format: {slot_str}"}
            parsed_user_slots.sort(key=lambda x: x[0])
            availability = []
            prices = []
            slot_objs = []
            for start_time, end_time, slot_str in parsed_user_slots:
                slot_obj = slotmap.get((start_time, end_time))
                if slot_obj and not slot_obj.is_blocked and not slot_obj.is_booked:
                    availability.append(True)
                    prices.append(slot_obj.price)
                    slot_objs.append(slot_obj)
                else:
                    availability.append(False)
                    prices.append(0)
                    slot_objs.append(None)
            l = 0
            curr_price = 0
            min_price = float('inf')
            best_window = None
            for r in range(len(availability)):
                if not availability[r]:
                    l = r + 1
                    curr_price = 0
                    continue
                curr_price += prices[r]
                while (r - l + 1) > userneedstoplay:
                    curr_price -= prices[l]
                    l += 1
                if (r - l + 1) == userneedstoplay and curr_price < min_price:
                    min_price = curr_price
                    best_window = (l, r)
            if not best_window:
                return {'success': False,
                        'message': 'No continuous slots available for selected hours.'}
            matchslots = [slot_objs[i] for i in range(best_window[0], best_window[1] + 1)]
            for slot in matchslots:
                if slot.is_blocked or slot.is_booked:
                    raise Exception('Slot already reserved by another user. Please refresh.')
            reserved_objs = []
            for slot in matchslots:
                slot.is_blocked = True
                slot.blocked_at = now
                reserved_objs.append(
                    reservedslots(
                        session=session,
                        slot=slot,
                        status='reserved'
                    )
                )
            Slot.objects.bulk_update(matchslots, ['is_blocked', 'blocked_at'])
            reservedslots.objects.bulk_create(reserved_objs, ignore_conflicts=True)
            reserved_ids = list(
                reservedslots.objects.filter(
                    session=session,
                    status='reserved'
                ).values_list('id', flat=True)
            )
            return {
                'success': True,
                'message': 'Slots reserved successfully.',
                'reserved_slots': reserved_ids,
                'session_id': session.id
            }
    except ValidationError as e:
        logger.warning("Validation error: %s", e)
        raise
    except Exception as e:
        logger.exception("chatbot_reserve_slots failed: %s", e)
        return {'success': False, 'message': str(e)}