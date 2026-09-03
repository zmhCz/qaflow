# 生产部署（Linux）

适用路径：`/opt/qaflow`
后端域名/IP：`your-domain.com` 或 `your-server-ip`
前端部署：独立部署在 `/opt/qaflow/frontend/dist`

---

## 1) 创建用户与目录

```bash
sudo useradd -m -s /bin/bash testhub
sudo mkdir -p /opt/qaflow
sudo chown -R testhub:testhub /opt/qaflow
```

将代码放到：
```
/opt/qaflow
```

目录结构示例：
```
/opt/qaflow/
├── backend/
├── apps/
├── manage.py
├── requirements.txt
├── media/
├── static/
└── frontend/
```

---

## 2) Python 依赖与虚拟环境

Ubuntu 22.04 默认 Python 通常是 3.10，但 QAFlow 的 AI/浏览器自动化依赖要求 Python 3.11+，推荐使用 Python 3.12：

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

```bash
cd /opt/qaflow
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install daphne channels channels-redis
```

---

## 3) 环境变量（.env）

创建 `/opt/qaflow/.env`：

```env
DEBUG=False
SECRET_KEY=replace-with-a-random-secret
ALLOWED_HOSTS=your-domain.com,your-server-ip
CSRF_TRUSTED_ORIGINS=https://your-domain.com

DB_NAME=qaflow
DB_USER=qaflow
DB_PASSWORD=replace-with-db-password
DB_HOST=127.0.0.1
DB_PORT=3306

REDIS_URL=redis://127.0.0.1:6379/0
```

---

## 4) 收集静态文件

```bash
source /opt/qaflow/venv/bin/activate
cd /opt/qaflow
python manage.py collectstatic --noinput
```

---

## 5) systemd 服务

### 5.1 ASGI 服务（Daphne）
`/etc/systemd/system/testhub-asgi.service`

```ini
[Unit]
Description=QAFlow ASGI (Daphne)
After=network.target

[Service]
User=testhub
WorkingDirectory=/opt/qaflow
Environment="DJANGO_SETTINGS_MODULE=backend.settings"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/qaflow/.env
ExecStart=/opt/qaflow/venv/bin/daphne -b 0.0.0.0 -p 8000 backend.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

### 5.2 Celery Worker 服务
`/etc/systemd/system/testhub-celery.service`

```ini
[Unit]
Description=QAFlow Celery Worker
After=network.target

[Service]
User=testhub
WorkingDirectory=/opt/qaflow
Environment="DJANGO_SETTINGS_MODULE=backend.settings"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/qaflow/.env
ExecStart=/opt/qaflow/venv/bin/celery -A backend worker --loglevel=info --pool=solo --concurrency=1
Restart=always

[Install]
WantedBy=multi-user.target
```

### 5.3 启动服务
```bash
sudo systemctl daemon-reload
sudo systemctl enable testhub-asgi testhub-celery
sudo systemctl start testhub-asgi testhub-celery
```

### 5.4 状态与日志
```bash
sudo systemctl status testhub-asgi
sudo systemctl status testhub-celery

journalctl -u testhub-asgi -f
journalctl -u testhub-celery -f
```

---

## 6) Nginx 配置（含 WebSocket）

`/etc/nginx/conf.d/testhub.conf`

```nginx
server {
    listen 80;
    server_name your-domain.com your-server-ip;

    # 静态与媒体
    location /static/ {
        alias /opt/qaflow/static/;
    }

    location /media/ {
        alias /opt/qaflow/media/;
    }

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # 前端独立部署
    location / {
        root /opt/qaflow/frontend/dist;
        try_files $uri /index.html;
    }
}
```

重启 Nginx：
```bash
sudo nginx -t
sudo systemctl restart nginx
```

---

## 7) 前端构建（独立部署）

```bash
cd /opt/qaflow/frontend
npm install
npm run build
```

---

## 8) 验证

- API：`http://your-domain.com/api/` 或 `http://your-server-ip/api/`
- WebSocket：`ws://your-domain.com/ws/app-automation/executions/<id>/`

---

## 9) 一键部署脚本（可选）

> 脚本会写入 `.env`、systemd 与 Nginx 配置，请先确认变量值（如域名、DB 密码）。

保存为 `/opt/qaflow/deploy_prod.sh`：

```bash
#!/usr/bin/env bash
set -e

APP_DIR="/opt/qaflow"
VENV_DIR="$APP_DIR/venv"
NGINX_CONF="/etc/nginx/conf.d/testhub.conf"

echo "=== 1) 创建虚拟环境 ==="
if [ ! -d "$VENV_DIR" ]; then
  python3.12 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "=== 2) 安装依赖 ==="
pip install -r "$APP_DIR/requirements.txt"
pip install daphne channels channels-redis

echo "=== 3) 写入 .env ==="
cat > "$APP_DIR/.env" <<EOF
DEBUG=False
SECRET_KEY=replace-with-a-random-secret
ALLOWED_HOSTS=your-domain.com,your-server-ip
CSRF_TRUSTED_ORIGINS=https://your-domain.com

DB_NAME=qaflow
DB_USER=qaflow
DB_PASSWORD=replace-with-db-password
DB_HOST=127.0.0.1
DB_PORT=3306

REDIS_URL=redis://127.0.0.1:6379/0
EOF

echo "=== 4) 收集静态文件 ==="
python "$APP_DIR/manage.py" collectstatic --noinput

echo "=== 5) systemd 服务 ==="
cat > /etc/systemd/system/testhub-asgi.service <<EOF
[Unit]
Description=QAFlow ASGI (Daphne)
After=network.target

[Service]
User=testhub
WorkingDirectory=$APP_DIR
Environment="DJANGO_SETTINGS_MODULE=backend.settings"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/daphne -b 0.0.0.0 -p 8000 backend.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/testhub-celery.service <<EOF
[Unit]
Description=QAFlow Celery Worker
After=network.target

[Service]
User=testhub
WorkingDirectory=$APP_DIR
Environment="DJANGO_SETTINGS_MODULE=backend.settings"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/celery -A backend worker --loglevel=info --pool=solo --concurrency=1
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable testhub-asgi testhub-celery
systemctl restart testhub-asgi testhub-celery

echo "=== 6) Nginx 配置 ==="
cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name your-domain.com your-server-ip;

    location /static/ {
        alias /opt/qaflow/static/;
    }

    location /media/ {
        alias /opt/qaflow/media/;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }

    location / {
        root /opt/qaflow/frontend/dist;
        try_files \$uri /index.html;
    }
}
EOF

nginx -t
systemctl restart nginx

echo "=== ✅ 部署完成 ==="
```

执行：
```bash
sudo chmod +x /opt/qaflow/deploy_prod.sh
sudo /opt/qaflow/deploy_prod.sh
```

