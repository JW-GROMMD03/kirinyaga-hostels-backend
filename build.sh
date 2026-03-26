#!/bin/bash
set -o errexit

# Upgrade pip
pip install --upgrade pip

# Install wheel and setuptools first
pip install wheel setuptools

# Install psycopg2-binary explicitly
pip install psycopg2-binary==2.9.9

# Install all other requirements
pip install -r requirements.txt

# Run migrations
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput