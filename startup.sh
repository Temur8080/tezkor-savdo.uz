#!/bin/bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py loaddata data.json
gunicorn --bind=0.0.0.0 --timeout 600 --chdir . pos.wsgi:application