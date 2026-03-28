#!/bin/bash
set -o errexit

echo "🚀 Starting build process..."

# Upgrade pip
pip install --upgrade pip

# Install requirements (psycopg 3 installs without compilation!)
pip install -r requirements.txt

# Verify database driver installation
echo "🔍 Verifying database driver installation..."
python -c "import psycopg; print(f'✓ psycopg version: {psycopg.__version__}')"

# Run database migrations
echo "📦 Running database migrations..."
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

echo "✅ Build completed successfully!"