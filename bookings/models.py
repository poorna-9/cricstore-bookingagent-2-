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
    name=models.CharField(max_length=100,unique=True,null=False)
    types=models.CharField(max_length=50,null=False,choices=TYPE_CHOICES,default='turf')
    city=models.CharField(max_length=100,null=False)
    address=models.TextField(null=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True,blank=True)
    image = models.ImageField(upload_to='grounds/',null=True,blank=True)
    sporttype=models.CharField(max_length=50,null=False,choices=TYPE_CHOICES,default='turf')
    longitude=models.FloatField(null=True,blank=True)
    lattitude=models.FloatField(null=True,blank=True)
    rating=models.FloatField(null=True,blank=True)
    opens=models.BinaryField(default=True)
    batballprovided=models.BinaryField(default=True)
    washroomsavailable=models.BinaryField(default=False)
    Grounddimensions=models.FloatField(null=True,blank=True)
    
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
            GOOGLE_MAPS_API=""
            url=f"https://maps.googleapis.com/maps/api/geocode/json"
            params={"address":self.address,"key":GOOGLE_MAPS_API}
            response=requests.get(url,params=params)
            data=response.json()
            if data['status']=="OK":
                loc=data['results'][0]['geometry']['location']
                self.lattitude=loc['lat']
                self.longitude=loc['lng']
        super().save(*args,**kwargs)



class slots(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name='slots')
    starttime=models.TimeField()
    endtime=models.TimeField()
    date = models.DateField()  
    price=models.DecimalField(max_digits=8, decimal_places=2,blank=True,null=True)                   
    is_booked = models.BooleanField(default=False)
    is_blocked=models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True) 
    def __str__(self):
        return f"{self.ground.name} {self.date} {self.starttime.strftime('%I:%M %p')} - {self.endtime.strftime('%I:%M %p')}"

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
    
    


    



    