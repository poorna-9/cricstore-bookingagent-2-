from django.db import models
from django.utils import timezone

class Queryrecordground(models.Model):
    userquery=models.TextField()
    gptresponse=models.JSONField()

    def __str__(self):
        return f"Query on {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
class Queryrecordproduct(models.Model):
    userquery=models.TextField()
    gptresponse=models.JSONField()

    def __str__(self):
        return f"Query on {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
