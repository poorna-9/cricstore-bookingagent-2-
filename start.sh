#!/bin/sh
echo "Applying migrations..."
python manage.py migrate

echo "Collecting static files..."
mkdir -p static
mkdir -p staticfiles
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
gunicorn cricketstore.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --log-level info
