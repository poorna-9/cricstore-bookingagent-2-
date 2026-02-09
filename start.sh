#!/bin/sh

echo "Applying migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn cricketstore.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --log-level info
