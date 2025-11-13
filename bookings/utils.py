from datetime import datetime, timedelta, time
from .models import slots

def generateslots(ground, slot_date):
    if ground.types == 'ground':
        slot_duration = timedelta(hours=3, minutes=30)
    else:
        slot_duration = timedelta(hours=1)
    start_datetime = datetime.combine(slot_date, time(6, 0))
    end_datetime = datetime.combine(slot_date, time(23, 59))
    current = start_datetime
    while current + slot_duration <= end_datetime:
        slot_endtime = current + slot_duration
        slots.objects.get_or_create(
            ground=ground,
            starttime=current.time(),
            endtime=slot_endtime.time(),
            date=slot_date,
            defaults={
                'price': ground.price,
                'is_booked': False,
                'is_blocked': False
            }
        )
        current += slot_duration
