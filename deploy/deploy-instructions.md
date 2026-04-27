# EC2 Deployment Instructions

## Prerequisites

- EC2 instance running Ubuntu (20.04+ or Amazon Linux 2)
- SSH access to the instance
- A domain name pointed to your EC2 public IP (`3.27.44.79`)
- Security group allowing ports: **22** (SSH), **80** (HTTP), **443** (HTTPS), **5000** (internal only)

---

## Step 1: Ensure Docker Containers Are Running

SSH into your EC2 instance and verify:

```bash
ssh -i your-key.pem ubuntu@3.27.44.79

cd /path/to/iot-aggregation-master
docker-compose up -d
docker-compose ps   # All services should be "Up"

# Verify Flask is responding
curl http://localhost:5000/health
# Expected: {"status": "ok"}
```

---

## Step 2: Upload Nginx Config

From your **local machine**, copy the nginx config to EC2:

```bash
scp -i your-key.pem deploy/ec2-nginx.conf ubuntu@3.27.44.79:/tmp/ec2-nginx.conf
scp -i your-key.pem deploy/setup-ec2.sh ubuntu@3.27.44.79:/tmp/setup-ec2.sh
```

---

## Step 3: Run Setup Script

SSH back into EC2 and run:

```bash
ssh -i your-key.pem ubuntu@3.27.44.79

sudo bash /tmp/setup-ec2.sh YOUR_DOMAIN_NAME
```

Replace `YOUR_DOMAIN_NAME` with your actual domain (e.g., `api.myiotproject.com`).

---

## Step 4: Verify

```bash
# From anywhere:
curl https://YOUR_DOMAIN/api/health
# Expected: {"status": "ok"}

curl https://YOUR_DOMAIN/api/list
# Expected: {"data": [...]}

curl https://YOUR_DOMAIN/api/alerts
# Expected: {"data": [...]}
```

---

## Step 5: Update Frontend API URL

In `frontend/app.js`, update the API_BASE_URL:

```javascript
return 'https://YOUR_DOMAIN/api';
```

Then push to your git repo — Amplify will auto-deploy.

---

## If You Don't Have a Domain (Self-Signed SSL)

If you want to use the raw IP (`3.27.44.79`) without a domain:

```bash
# On EC2:
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/selfsigned.key \
  -out /etc/nginx/ssl/selfsigned.crt \
  -subj "/CN=3.27.44.79"
```

Then update the nginx config to use these paths instead of Let's Encrypt:
```
ssl_certificate     /etc/nginx/ssl/selfsigned.crt;
ssl_certificate_key /etc/nginx/ssl/selfsigned.key;
```

And change `server_name` to `3.27.44.79`.

> ⚠️ Browsers will show a security warning with self-signed certs. This is normal for IP-based HTTPS.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `502 Bad Gateway` | Flask not running: `docker-compose up -d && curl localhost:5000/health` |
| `Mixed Content` error | Frontend still using `http://`. Update `API_BASE_URL` in `app.js` |
| Certbot fails | Check DNS: `dig YOUR_DOMAIN` should resolve to EC2 IP |
| Port 443 refused | Open port 443 in AWS Security Group |
| CORS errors | Check `api/app.py` CORS origins include your Amplify URL |
