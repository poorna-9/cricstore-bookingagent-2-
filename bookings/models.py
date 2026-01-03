from pyclbr import Class
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta,datetime,date
import requests


class Customer(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE,null=True,blank=True,related_name='bookings_customer')
    name=models.CharField(max_length=50,null=True)
    email=models.EmailField(max_length=50,null=True)

    def __str__(self):
        return self.name or ""

class Ground(models.Model):
    TYPE_CHOICES = [
        ('football', 'Football'),
        ('tennis', 'Tennis'),
        ('badminton', 'Badminton'),
        ('ground', 'Ground'),
        ('cricket','Cricket'),
        ('Volleyball','Volleyball'),
    ]
    type_choices=[
        ('turf','Turf'),
        ('astro','Astro'),
        ('hardcourt','Hardcourt'),
        ('grass','Grass'),
    ]
    name=models.CharField(max_length=100,unique=True,null=False)
    types=models.CharField(max_length=50,null=False,choices=type_choices,default='turf')
    city=models.CharField(max_length=100,null=False)
    address=models.TextField(null=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True,blank=True)
    image = models.ImageField(upload_to='grounds/',null=True,blank=True)
    sporttype=models.CharField(max_length=50,null=False,choices=TYPE_CHOICES,default='turf')
    lattitude=models.FloatField(null=True,blank=True)
    longitude=models.FloatField(null=True,blank=True)
    rating=models.FloatField(null=True,blank=True)
    opens= models.BooleanField(default=True)
    batballprovided=models.BooleanField(default=True)
    washroomsavailable=models.BooleanField(default=False)
    Grounddimensions=models.CharField(max_length=100,null=True,blank=True)
    morning_price=models.IntegerField(null=True,blank=True)
    afternoon_price=models.IntegerField(null=True,blank=True)
    evening_price=models.IntegerField(null=True,blank=True)
    night_price=models.IntegerField(null=True,blank=True)
    t_morning_price=models.IntegerField(null=True,blank=True)
    t_afternoon_price=models.IntegerField(null=True,blank=True)
    t_evening_price=models.IntegerField(null=True,blank=True)
    t_night_price=models.IntegerField(null=True,blank=True)
    t_fullday_price=models.IntegerField(null=True,blank=True)
    def __str__(self):
        return self.name
    @property
    def imageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url
    
    def save(self,*args,**kwargs):
        if not self.lattitude or not self.longitude:
            LOCATIONIQ_API_KEY="pk.9a6225b4ea47b4e24c62938d1d821a4f"
            url="https://us1.locationiq.com/v1/search"
            params={"address":self.address,"key": LOCATIONIQ_API_KEY,"format": "json"}
            headers = {"User-Agent": "CricStore-App/1.0"}
            response=requests.get(url,params=params,headers=headers)
            data=response.json()
            if isinstance(data, list) and data:
                loc=data[0]
                self.lattitude=loc['lat']
                self.longitude=loc['lng']
        super().save(*args,**kwargs)

class slots(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name='slots')
    starttime=models.TimeField()
    endtime=models.TimeField()
    date = models.DateField()  
    shift = models.CharField(choices=[
        ("morning", "Morning"),
        ("afternoon", "Afternoon"),
        ("evening", "Evening"),
        ("night", "Night"),
    ])                  
    is_booked = models.BooleanField(default=False)
    is_blocked=models.BooleanField(default=False)
    price=models.IntegerField(null=True,blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True) 
    def __str__(self):
        return f"{self.ground.name} {self.date} {self.starttime.strftime('%I:%M %p')} - {self.endtime.strftime('%I:%M %p')}"
    
class tournamentsession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    start_date = models.DateField(null=True,blank=True)
    end_date = models.DateField(null=True,blank=True)
    session_type = models.CharField(max_length=20,default="full_day")  
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)


class reservetournament(models.Model):
    session = models.ForeignKey(tournamentsession, on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date = models.DateField()
    blocked_slots = models.ManyToManyField(
        'slots',
        related_name='tournament_days'
    )
    status = models.CharField(max_length=10, choices=[('reserved', 'Reserved'), ('booked', 'Booked')])
    session_type = models.CharField(
        max_length=20,
        choices=[
            ("morning", "Morning"),
            ("afternoon", "Afternoon"),
            ("evening", "Evening"),
            ("night", "Night"),
            ("full_day", "Full Day"),
        ]
    )
    class Meta:
        constraints = [
        models.UniqueConstraint(
            fields=["ground", "date"],
            condition=models.Q(status__in=["reserved", "booked"]),
            name="unique_active_tournament_day"
        )
    ]


class Orders(models.Model):
    STATUS_CHOICES = [
        ('booked', 'Booked'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ground = models.ForeignKey('Ground', on_delete=models.CASCADE)
    session= models.ForeignKey(tournamentsession,on_delete=models.SET_NULL,null=True,blank=True)  
    date = models.DateField()
    slotsbooked = models.ManyToManyField('slots')
    transaction_id = models.CharField(max_length=100)
    booked = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    price = models.FloatField(default=0.0)
    payment_status = models.CharField(
        max_length=20,
        choices=[('success', 'Success'), ('failed', 'Failed'), ('refunded', 'Refunded')],
        default='success'
    )
    refund_amount = models.FloatField(default=0.0)
    cancel_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    Tournament_or_normal= models.CharField(max_length=20, default='normal')

    def __str__(self):
        return f"{self.user.username} - {self.ground.name} on {self.date}"
class reservationsession(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date=models.DateField()
    expires_at = models.DateTimeField()
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)
class reservedslots(models.Model):
    STATUS_CHOICES = [
        ('reserved', 'Reserved'),
        ('booked', 'Booked')
    ]
    session=models.ForeignKey(reservationsession,on_delete=models.CASCADE)
    slot = models.ForeignKey(slots, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='reserved')
    class Meta:
        unique_together = ('slot',)
    def __str__(self):
        return f"{self.slot} - {self.status}"
    

class payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(
        reservationsession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    tournament_session = models.ForeignKey(
        tournamentsession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    order_id = models.CharField(max_length=100, null=True, blank=True)
    payment_id = models.CharField(max_length=100, null=True, blank=True)

    amount = models.FloatField()
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed')],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)


    
    


    



    