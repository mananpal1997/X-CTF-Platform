#!/bin/bash

# X-CTF Django Platform Configuration Setup Script
# This script generates configuration files from templates

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== X-CTF Django Platform Configuration Setup ==="
echo ""

if [ -n "$CONDA_PREFIX" ]; then
    DEFAULT_PYTHON_BIN="$CONDA_PREFIX/bin"
    DEFAULT_LD_LIBRARY_PATH="$CONDA_PREFIX/lib"
    echo "Detected conda environment: $CONDA_PREFIX"
    USE_CONDA=true
elif [ -d "venv" ] || [ -d ".venv" ]; then
    VENV_DIR=""
    if [ -d "venv" ]; then
        VENV_DIR="$SCRIPT_DIR/venv"
    else
        VENV_DIR="$SCRIPT_DIR/.venv"
    fi
    DEFAULT_PYTHON_BIN="$VENV_DIR/bin"
    DEFAULT_LD_LIBRARY_PATH=""
    echo "Detected Python virtual environment: $VENV_DIR"
    USE_CONDA=false
else
    PYTHON_PATH=$(which python3 2>/dev/null || which python 2>/dev/null || echo "")
    if [ -z "$PYTHON_PATH" ]; then
        echo "ERROR: Could not find Python. Please activate your conda/venv environment or install Python."
        exit 1
    fi
    DEFAULT_PYTHON_BIN=$(dirname "$PYTHON_PATH")
    DEFAULT_LD_LIBRARY_PATH=""
    USE_CONDA=false
    echo "Using system Python: $PYTHON_PATH"
fi

CURRENT_USER=${USER:-$(whoami)}

echo ""
echo "Configuration values (press Enter to use defaults):"
echo ""

read -p "Python binary directory [$DEFAULT_PYTHON_BIN]: " PYTHON_BIN
PYTHON_BIN=${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}

if [ "$USE_CONDA" = true ]; then
    read -p "LD_LIBRARY_PATH (usually conda lib directory) [$DEFAULT_LD_LIBRARY_PATH]: " LD_LIBRARY_PATH
    LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-$DEFAULT_LD_LIBRARY_PATH}
else
    LD_LIBRARY_PATH=""
fi

read -p "System user to run services [$CURRENT_USER]: " SERVICE_USER
SERVICE_USER=${SERVICE_USER:-$CURRENT_USER}

read -p "Web server user (nginx user, usually www-data or nginx) [www-data]: " WEB_USER
WEB_USER=${WEB_USER:-www-data}

read -p "Web server group (nginx group, usually www-data or nginx) [www-data]: " WEB_GROUP
WEB_GROUP=${WEB_GROUP:-www-data}

read -p "Server domain name (for production, or 'localhost' for local dev) [localhost]: " DOMAIN
DOMAIN=${DOMAIN:-localhost}

read -p "Environment (local/production) [local]: " ENV_TYPE
ENV_TYPE=${ENV_TYPE:-local}

read -p "Django project directory (absolute path) [$SCRIPT_DIR]: " DJANGO_DIR
DJANGO_DIR=${DJANGO_DIR:-$SCRIPT_DIR}

echo ""
echo "Generating configuration files..."

mkdir -p logs

echo "  - supervisord.conf"
cat > supervisord.conf <<EOF
[unix_http_server]
file=/tmp/supervisor.sock

[supervisord]
logfile=$SCRIPT_DIR/logs/supervisord.log
logfile_maxbytes=10MB
logfile_backups=5
loglevel=info
pidfile=$SCRIPT_DIR/supervisord.pid
nodaemon=false
minfds=1024
minprocs=200
user=$SERVICE_USER

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock

[program:django-server]
command=$PYTHON_BIN/gunicorn xctf.wsgi:application -c $DJANGO_DIR/gunicorn_config.py
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/gunicorn.log
stderr_logfile=$SCRIPT_DIR/logs/gunicorn-error.log
priority=2
user=$SERVICE_USER
stopwaitsecs=30
killasgroup=true
stopasgroup=true

[program:celery-beat]
command=$PYTHON_BIN/celery -A xctf.celery beat --loglevel info --logfile $SCRIPT_DIR/logs/celery-beat.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=3
user=$SERVICE_USER

[program:celery-worker-1]
command=$PYTHON_BIN/celery -A xctf.celery worker --loglevel info --concurrency=2 --hostname=worker1@%%h --logfile $SCRIPT_DIR/logs/celery-worker-1.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=4
user=$SERVICE_USER

[program:celery-worker-2]
command=$PYTHON_BIN/celery -A xctf.celery worker --loglevel info --concurrency=2 --hostname=worker2@%%h --logfile $SCRIPT_DIR/logs/celery-worker-2.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=4
user=$SERVICE_USER

[program:celery-worker-3]
command=$PYTHON_BIN/celery -A xctf.celery worker --loglevel info --concurrency=2 --hostname=worker3@%%h --logfile $SCRIPT_DIR/logs/celery-worker-3.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=4
user=$SERVICE_USER

[program:celery-worker-4]
command=$PYTHON_BIN/celery -A xctf.celery worker --loglevel info --concurrency=2 --hostname=worker4@%%h --logfile $SCRIPT_DIR/logs/celery-worker-4.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=4
user=$SERVICE_USER

[program:flower]
command=$PYTHON_BIN/celery -A xctf.celery flower --url-prefix=/flower-monitoring --basic_auth=admin:admin --logfile $SCRIPT_DIR/logs/flower.log
directory=$DJANGO_DIR
environment=LD_LIBRARY_PATH="$LD_LIBRARY_PATH",DJANGO_SETTINGS_MODULE="xctf.settings"
process_name=%(program_name)s
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=$SCRIPT_DIR/logs/%(program_name)s.log
priority=5
user=$SERVICE_USER

EOF

if [ ! -f "flower_env.sh" ]; then
    cat > flower_env.sh <<FLOWEREOF
export FLOWER_USER="admin"
export FLOWER_PASSWORD="admin"
FLOWEREOF
    chmod +x flower_env.sh 2>/dev/null || true
fi

echo "  - gunicorn_config.py"
cat > gunicorn_config.py <<EOF
# Gunicorn configuration file
import multiprocessing
import os

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1  # Recommended: (2 x CPU cores) + 1
worker_class = "gevent"
timeout = 120
keepalive = 120

loglevel = "info"
accesslog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn-access.log")
errorlog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn-error.log")

max_requests = 1000
max_requests_jitter = 50
worker_connections = 1000

wsgi_app = "xctf.wsgi:application"

EOF

echo "  - nginx.conf"

if [ "$ENV_TYPE" = "production" ]; then
    cat > nginx.conf <<EOF
upstream django_server {
    server 127.0.0.1:8000;
}

server {
    if (\$host = $DOMAIN) {
        return 301 https://\$host\$request_uri;
    }

    listen 80;
    server_name $DOMAIN;

    client_max_body_size 100M;

    location / {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static/ {
        alias $DJANGO_DIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias $DJANGO_DIR/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location /health-check {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        access_log off;
    }

    location /flower-monitoring/ {
        proxy_pass http://127.0.0.1:5555/flower-monitoring/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
    }
}

server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    # SSL certificates (update these paths after running certbot)
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    client_max_body_size 100M;

    location / {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static/ {
        alias $DJANGO_DIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias $DJANGO_DIR/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location /health-check {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        access_log off;
    }

    location /flower-monitoring/ {
        proxy_pass http://127.0.0.1:5555/flower-monitoring/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
    }
}
EOF
else
    cat > nginx.conf <<EOF
upstream django_server {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name localhost;

    client_max_body_size 100M;

    location / {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static/ {
        alias $DJANGO_DIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias $DJANGO_DIR/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    location /health-check {
        proxy_pass http://django_server;
        proxy_set_header Host \$host;
        access_log off;
    }

    location /flower-monitoring/ {
        proxy_pass http://127.0.0.1:5555/flower-monitoring/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
    }
}
EOF
fi

echo "  - .env.example"
cat > .env.example <<EOF
# Django Secret Key (generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,*
DEBUG=True  # Set to False in production

# Sentry DSN for error tracking (optional)
# SENTRY_DSN=your-sentry-dsn-here

# DISABLE RATE LIMITING=true/false (default: false)

SQLALCHEMY_DATABASE_URI=mysql://user:password@localhost:3306/xctf

# Option 2: Use individual database variables (alternative to SQLALCHEMY_DATABASE_URI)
# DB_ENGINE=mysql
# DB_NAME=xctf
# DB_USER=root
# DB_PASSWORD=your-password
# DB_HOST=localhost
# DB_PORT=3306

DB_CONN_MAX_AGE=600  # 0 = no pooling, None = persistent connections for process lifetime (use with caution)

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-redis-password

CELERY_BROKER_URL=redis://:your-redis-password@localhost:6379/0
CELERY_RESULT_BACKEND=redis://:your-redis-password@localhost:6379/0

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=465
MAIL_USE_SSL=True
MAIL_USE_TLS=False
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

SERVER_NAME=localhost:8080
SESSION_COOKIE_SECURE=False  # Set to True in production with HTTPS

CHALLENGE_CONTAINER_VOLUME_BASE=/tmp/xctf_volumes
CHALLENGE_DIRECTORY=challenges  # Path to the challenges directory

EOF

echo ""
echo "Configuration files generated successfully!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and fill in your values:"
echo "     cp .env.example .env"
echo "     # Edit .env with your actual configuration"
echo ""
echo "  2. Generate Django secret key:"
echo "     python manage.py shell -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
echo ""
echo "  3. Run Django migrations:"
echo "     python manage.py migrate"
echo ""
echo "  4. Collect static files:"
echo "     python manage.py collectstatic --noinput"
echo ""
echo "  5. Setup challenges (if needed):"
echo "     python manage.py setup_challenges"
echo ""
echo "  6. For Flower: Create flower_env.sh with credentials (optional):"
echo "     cp flower_env.sh.example flower_env.sh"
echo "     # Edit flower_env.sh and set FLOWER_USER and FLOWER_PASSWORD"
echo ""
echo "  7. For production: Update SSL certificate paths in nginx.conf after running certbot"
echo ""
echo "  8. Start services:"
echo "     supervisord -c supervisord.conf"
echo "     supervisorctl -c supervisord.conf start all"
echo ""
echo "Configuration summary:"
echo "  - Python: $PYTHON_BIN"
echo "  - Django directory: $DJANGO_DIR"
echo "  - User: $SERVICE_USER"
echo "  - Web server: $WEB_USER:$WEB_GROUP"
echo "  - Domain: $DOMAIN"
echo "  - Environment: $ENV_TYPE"
echo ""

