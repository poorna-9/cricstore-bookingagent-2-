from datetime import timezone
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
        distance = haversine(userlat, userlon, ground.latitude, ground.longitude)
        if distance <= radius:
            nearby_grounds.append(ground)
    return nearby_grounds


def timingstoslots(timings, sporttype=None, groundorturf, am_or_pm=None):#type:ignore
    opening_time = datetime.strptime("06:00 AM", "%I:%M %p").time()
    closing_time = datetime.strptime("11:00 PM", "%I:%M %p").time()
    userslots = []
    constraint = timings.get("constraint_type")
    start = timings.get("start_time")
    end = timings.get("end_time")
    starttime = datetime.strptime(start, "%I:%M %p").time() if start else None
    endtime = datetime.strptime(end, "%I:%M %p").time() if end else None
    if constraint == "after":
        starttime = starttime or opening_time
        endtime = closing_time
    elif constraint == "before":
        endtime = starttime or closing_time
        starttime = opening_time
    elif constraint == "between":
        starttime = starttime or opening_time
        endtime = endtime or closing_time
    if groundorturf=="ground":
        slotduration = timedelta(hours=3.5)
    else:
        slotduration = timedelta(hours=1)
    current = datetime.combine(datetime.today(), starttime)
    end_dt = datetime.combine(datetime.today(), endtime)
    while current + slotduration <= end_dt:
        slot_end = current + slotduration
        userslots.append(f"{current.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}")
        current = slot_end
    if am_or_pm and am_or_pm.lower() in ["am", "pm"]:
        userslots = [s for s in userslots if am_or_pm.upper() in s]
    return userslots
def parse_natural_date(text):
    text = text.lower().strip()
    today = datetime.now().date()
    if text in ("today", "tonight"):
        return today
    elif text == "tomorrow":
        return today + timedelta(days=1)
    elif text == "day after tomorrow":
        return today + timedelta(days=2)
    elif text == "this weekend":
        days_until_saturday = (5 - today.weekday()) % 7 
        return today + timedelta(days=days_until_saturday)
    elif text == "next weekend":
        days_until_saturday = (5 - today.weekday()) % 7
        return today + timedelta(days=days_until_saturday + 7)
    elif text == "next week":
        return today + timedelta(days=7)
    else:
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
        
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
    print("DEBUG reserveslot received POST:", request.POST)
    print("date:", date_str)
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

    if reservedslots.objects.filter(session=session, status='reserved').count() >= 3:
        return JsonResponse({'success': False, 'message': 'You can reserve a maximum of 3 slots per session'})

    reservedslots.objects.create(session=session, slot=slot, status='reserved')
    slot.is_blocked = True
    slot.blocked_at = timezone.now()
    slot.save()
    return JsonResponse({'success': True, 'action': 'selected'})

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



def book_slots(request):
    session_id = request.POST.get('session_id')
    session = get_object_or_404(reservationsession, id=session_id, user=request.user)
    for reserved_slot in session.slots.all(): #type: ignore
        reserved_slot.status = 'booked'
        reserved_slot.save()
        reserved_slot.slot.is_booked = True
        reserved_slot.slot.save()
    session.delete()
    return redirect('home')
def checkoutpage(request):
    selectedslots=request.GET.get('selected_slots')
    price=len(selectedslots)
    context={}
    return render(request,'bookings/checkoutpage.html',context)

def processpayment(request):
    if request.method=="POST":
        # Integration of  payment gateway 
        return JsonResponse({'success': True, 'message': 'Payment processed successfully'})
    return JsonResponse({'success': False, 'message': 'Invalid request'})


def get_lat_long(address):
    api_key = "YOUR_GOOGLE_API_KEY"
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    if data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    return None, None


def getuserlocation(request):
    if request.method=="POST":
        address=request.POST.get("user_address")
        if address:
            lat,long=get_lat_long(address)
            if lat is not None and long is not None:
               request.session["user_lat"] = lat
               request.session["user_lon"] = long
               request.session["user_address"] = address
               messages.success(request, "Location updated successfully!")
            else:
              messages.error(request, "Couldn't fetch location. Please try again.")
        else:
            messages.warning(request, "Please enter a valid address.")
    return redirect("grounds")
from django.utils import timezone

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
        return {"message": f"🏟️ {ground.name} offers: {', '.join(facilities)}."}
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
        f"🏟️*{ground.name}* ({sport}) — located in {ground.city}.\n"
        f" Average price: ₹{price}\n Rating: {rating}\n"
        f"Facilities: {facilities_str}\n"
        f"Status: {' Open' if is_open else 'Closed'}"
    )
    return {"message": response}

def userquerychatbot(request):
    query = request.GET.get('query', '')
    output = interpretgroundquery(query)
    ajax = request.GET.get('ajax')
    if "chatcontext" not in request.session:
        request.session["chatcontext"] = {}
    context = request.session["chatcontext"]
    for key, value in output.items():
        if value:
            context[key] = value
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
    if sport_type in outdoor_sports:
        if not ground_or_turf:
            response_message = f"For {sport_type.capitalize()}, would you like to book a ground or a turf?"
            return JsonResponse({
                "message": response_message,
                "need_ground_turf_choice": True,
                "sporttype": sport_type
            })
    if not ground_or_turf:
        if sport_type in ["badminton", "tennis", "volleyball"]:
            ground_or_turf = "turf"
        else:
            ground_or_turf = "ground"
    context["sporttype"] = sport_type
    context["ground_or_turf"] = ground_or_turf
    request.session.modified = True
    grounds = Ground.objects.filter(sportype=sport_type,types=ground_or_turf)
    intents=output.get("intent")
    if intents in ["show", "find", "search","recommend","suggest","view"]:
            output["intent"]="show_ground"
    elif intents in ["book", "reserve","schedule","play"]:
        output["intent"]="book"
    elif intents in ["cancel","change","modify"]:
        output["intent"]="cancel_booking"
    elif intents in ["reschedule"]:
        output["intent"]="reshedule"
    elif intents in ["about", "info_ground", "tellme"]:
        output["intent"] = "ground_info"
    if output.get("intent") == "show_ground":
        if not context.get("city"):
            if context.get("radius_km"):
                if request.session.get("user_lat") and request.session.get("user_lon"):
                    grounds = findgroundsnear(
                        grounds,
                        float(context["radius_km"]),
                        float(request.session["user_lat"]),
                        float(request.session["user_lon"])
                    )
                if isinstance(grounds, list) and len(grounds) > 0:
                    ground_ids = [g.id for g in grounds]
                    grounds = Ground.objects.filter(id__in=ground_ids)
            else:
                return JsonResponse({'message': "Please tell me which city you want to book a ground or turf"})
        if context.get("datetime"):
            parsed_date = parse_natural_date(context["datetime"])
            if parsed_date:
                request.session["selected_date"] = parsed_date.strftime("%Y-%m-%d")
        if context.get("ground or turf"):
            request.session["ground_type"] = context["ground or turf"]
        if context.get("timings"):
            request.session["selected_slots"] = context["timings"]
        if context.get("city"):
            grounds = grounds.filter(city__icontains=context["city"])
        if context.get("area"):
            grounds = grounds.filter(address__icontains=context["area"])
        if context.get("radius_km"):
            user_lat = request.session.get("user_lat")
            user_lon = request.session.get("user_lon")
            if user_lat and user_lon:
                grounds = findgroundsnear(
                    grounds,
                    float(context["radius_km"]),
                    float(user_lat),
                    float(user_lon)
                )
        if context.get("rating_min"):
            grounds = grounds.filter(rating__gte=float(context["rating_min"]))
        if context.get("rating_semantic") == "top_rated":
            grounds = grounds.filter(rating__gte=4).order_by('-rating')
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

        if ajax:
            data = [
                {"id": g.id, "name": g.name, "imageURL": g.imageURL, "price": g.price}
                for g in grounds
            ]
            return JsonResponse({'grounds': data})
        if context.get("ground_or_turf_name"):
            if not context.get("area"):
                return JsonResponse({'message': "Please tell me which area this ground is in"})
            ground = Ground.objects.filter(
                name__iexact=context["ground_or_turf_name"],
                city__icontains=context["city"],
                address__icontains=context["area"]
            ).first()
            if not ground:
                return JsonResponse({'message': "Sorry, I couldn't find that ground."})
            if context.get("open"):
                if ground[open]:
                    return JsonResponse({'message':"yes it's open"})
                else:
                    return JsonResponse({"message":"sorry today ground is closed "})
            date_str = request.session.get("selected_date")
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
                total = ground.price * len(slots_list)
                return render(request, 'bookings/checkoutpage.html', {
                    'ground': ground,
                    'slots_list': slots_list,
                    'total': total
                })
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

            return render(request, 'bookings/groundpage.html', {
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
            })
    if output.get("intent") == "book":
        required_fields = ["ground_or_turf_name", "city", "area", "datetime", "timings", "am or pm"]
        for field in required_fields:
            if not context.get(field):
                return JsonResponse({'message': f"Please tell me the {field.replace('_', ' ')}."})
        ground = Ground.objects.filter(
            name__icontains=context["ground_or_turf_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        if not ground:
            return JsonResponse({'message': "Sorry, I couldn't find that ground."})

        try:
            date_obj = datetime.strptime(context["datetime"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        userslots = timingstoslots(
            context["timings"], context["sporttype"],context["ground_or_turf"], context["am or pm"]
        )
        if len(userslots) > 2:
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?"})
        userneedstoplay = len(userslots)
        if int(output.get("hours", userneedstoplay)) < len(userslots):
            userneedstoplay = int(output.get("hours"))
        output = chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay)
        if output.status_code == 200:
            data = output.json()
            if not data.get("success"):
                return JsonResponse({'message': data.get("message")})
            else:
                reservedslots_ids = data.get("reserved_slots", [])
                price = len(reservedslots_ids) * ground.price
                context = {'ground': ground, 'slots_list': userslots, 'total': price}
                return render(request, 'bookings/checkoutpage.html', context)
        else:
            return JsonResponse({'message': 'Error reserving slots. Please try again.'})
    if output.get("intent")=="cancel_booking":
        pastorders=Orders.objects.filter(user=request.user,date__gt=timezone.now().date(),booked=True).order_by("date")
        booking_id=request.POST.get("booking_id", None)
        if not booking_id:
            options = [
            {
                'id': order.id,
                'text': f"{order.ground.name} on {order.date} — Slots: {order.slotsbooked}"
            }
            for order in pastorders
            ]
            return JsonResponse({
            "message": "Select which booking you'd like to cancel:",
            "options": options
            })
        booking=Orders.objects.filter(id=booking_id,user=request.user).first()
        if not booking:
            return JsonResponse({"message": "Invalid booking selected."})
        if booking.date<timezone.now().date():
            return JsonResponse({"message": "Sorry, you can’t cancel this booking need any help with this order speak about that"})
        with transaction.atomic():
            for slot in booking.slotsbooked.all():
              slot.is_blocked=False
              slot.is_booked=False
              slot.save(update_fields=["is_blocked", "is_booked"])
            booking.booked=False
            booking.status="cancelled"
            booking.save(update_fields=["booked", "status"])
        return JsonResponse({"message": f"Your booking is cancelled. Refund amount of ₹{booking.price} is initiated."})
    if output.get("intent")=="reschedule":
        date=output.get("date")
        pastslots=output.get("slots")
        newslots=output.get("newslots")
        ground = Ground.objects.filter(
            name__icontains=context["ground_name"],
            city__icontains=context["city"],
            address__icontains=context["area"]
        ).first()
        try:
            date_obj = datetime.strptime(context["datetime"], "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'message': "Invalid date format. Please use YYYY-MM-DD."})
        if len(newslots) > 2:
            return JsonResponse({'message': f"Among all hours {context['timings']}, how many hours do you want to play?"})
        userneedstoplay = len(newslots)
        if int(output.get("hours", userneedstoplay)) < len(newslots):
            userneedstoplay = int(output.get("hours"))
        outputofavailable=checkavailabilityslots(request,ground,date_obj,newslots,userneedstoplay)
        if outputofavailable["success"]==True:
            pastorder=Orders.objects.filter(user=request.user,date=date,slotsbooked__in=pastslots).distinct().first()
            if pastorder:
                for slot in pastslots:
                    slot.is_blocked=False
                    slot.is_booked=False
                    slot.save(update_fields=["is_blocked", "is_booked"])
                pastorder.booked=False
                pastorder.status="cancelled"
                pastorder.save()
                outputofbooking=chatbot_reserve_slots(request,ground,date_obj,newslots,userneedstoplay)
                datarescedule=outputofbooking.json()
                if not datarescedule.get("success"):
                    return JsonResponse({'message': datarescedule.get("message")})
                else:
                   reservedslots_ids = data.get("reserved_slots", [])
                   price = len(reservedslots_ids) * ground.price
                   context = {'ground': ground, 'slots_list': newslots, 'total': price}
                   return render(request, 'bookings/checkoutpage.html', context)
            else:
                return JsonResponse({"message":"sorry that slots order is not booked on that date"})
        else:   
          return JsonResponse({"message":outputofavailable["message"]})
    if output.get("intent") in ["ground_info", "ground_facilities", "ground_status"]:
        info_result = handle_ground_info(context)
        return JsonResponse(info_result)
def checkavailabilityslots(request, ground, date_obj, userslots, userneedstoplay):
    cleanexpiredsessions()
    if not request.user.is_authenticated:
        return {'success': False, 'message': 'Please log in to continue booking.'}
    availableslots = slots.objects.filter(ground=ground, date=date_obj, is_blocked=False, is_booked=False)
    available_slot_strings = {
        f"{s.starttime.strftime('%I:%M %p')} - {s.endtime.strftime('%I:%M %p')}" for s in availableslots
    }
    matchslots = []
    if len(userslots) >= userneedstoplay:
        for slot_str in userslots:
            try:
                start_str, end_str = slot_str.split(" - ")
                start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
                end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
            except Exception:
                return {'success': False, 'message': f"Invalid slot format: {slot_str}"}
            slot_obj = availableslots.filter(starttime=start_time, endtime=end_time).first()
            if not slot_obj:
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
                    data = [
                        {"id": g.id, "name": g.name, "imageURL": g.imageURL, "price": g.price}
                        for g in altgrounds
                    ]
                    return {
                        'success': False,
                        'message': f"Slot {slot_str} not available in {ground.name}. Alternatives found.",
                        'alternative_grounds': data,
                        'available_slots_same_ground': sorted(list(available_slot_strings))
                    }
                return {
                    'success': False,
                    'message': f"Slot {slot_str} not available in {ground.name}. Available slots: {sorted(list(available_slot_strings))}"
                }

            matchslots.append(slot_obj)
        if len(matchslots) >= userneedstoplay:
            return {'success': True, 'message': "Yes — requested slots are available."}
        else:
            return {'success': False, 'message': "Not enough contiguous/available slots found."}
    else:
        avail_order = [1 if s in available_slot_strings else 0 for s in userslots]
        target = userneedstoplay
        found_range = None
        cnt = 0
        l = 0
        for r in range(len(avail_order)):
            if avail_order[r] == 1:
                cnt += 1
            else:
                cnt = 0
                l = r + 1
            if cnt == target:
                found_range = (r - target + 1, r)
                break
        if found_range:
            return {'success': True, 'message': "Found contiguous block of slots available."}
        else:
            return {'success': False, 'message': "Could not find contiguous block of required length."}

    

from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse

@transaction.atomic
def chatbot_reserve_slots(request, ground, date_obj, userslots, userneedstoplay):
    cleanexpiredsessions()
    if not request.user.is_authenticated:
        return {'success': False, 'message': 'Please log in to continue booking.'}

    user = request.user
    session, _ = reservationsession.objects.get_or_create(
        user=user,
        ground=ground,
        date=date_obj,
        defaults={'expires_at': timezone.now() + timedelta(minutes=15)}
    )
    availableslots = slots.objects.select_for_update(skip_locked=True).filter(
        ground=ground, date=date_obj, is_blocked=False, is_booked=False
    )
    available_slot_strings = {
        f"{s.starttime.strftime('%I:%M %p')} - {s.endtime.strftime('%I:%M %p')}" for s in availableslots
    }
    matchslots = []
    if len(userslots) >= userneedstoplay:
        for slot_str in userslots:
            try:
                start_str, end_str = slot_str.split(" - ")
                start_time = datetime.strptime(start_str.strip(), "%I:%M %p").time()
                end_time = datetime.strptime(end_str.strip(), "%I:%M %p").time()
            except Exception:
                return {'success': False, 'message': f"Invalid slot format: {slot_str}"}

            slot_obj = availableslots.filter(starttime=start_time, endtime=end_time).first()
            if slot_obj:
                matchslots.append(slot_obj)
            else:
                return {
                    'success': False,
                    'message': f"Slot {slot_str} not available.",
                    'available_slots_same_ground': sorted(list(available_slot_strings))
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
        'reserved_slots': [r.id for r in reservedslots.objects.filter(session=session)]
    }
