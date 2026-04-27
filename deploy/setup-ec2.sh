#!/bin/bash
# ============================================
# EC2 SETUP SCRIPT - IoT API Gateway
# ============================================
# Run as root (sudo) on your EC2 Ubuntu instance
# Usage: sudo bash setup-ec2.sh YOUR_DOMAIN

set -euo pipefail

DOMAIN="${1:-}"

if [ -z "$DOMAIN" ]; then
  echo "Usage: sudo bash setup-ec2.sh YOUR_DOMAIN"
  echo "Example: sudo bash setup-ec2.sh api.myiotproject.com"
  exit 1
fi

echo "============================================"
echo "Setting up IoT API Gateway for: $DOMAIN"
echo "============================================"

# Step 1: Update system
echo "[1/7] Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Step 2: Install Nginx
echo "[2/7] Installing Nginx..."
apt-get install -y nginx

# Step 3: Install Certbot
echo "[3/7] Installing Certbot..."
apt-get install -y certbot python3-certbot-nginx

# Step 4: Create certbot webroot
echo "[4/7] Setting up certbot webroot..."
mkdir -p /var/www/certbot

# Step 5: Copy nginx config
echo "[5/7] Configuring Nginx..."
# Replace domain placeholder
sed "s/YOUR_DOMAIN_HERE/$DOMAIN/g" /tmp/ec2-nginx.conf > /etc/nginx/sites-available/iot-api

# Enable the site
ln -sf /etc/nginx/sites-available/iot-api /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test config (will fail on SSL certs not yet existing — that's OK)
echo "Testing nginx config (SSL errors expected before certbot)..."
nginx -t 2>/dev/null || true

# Step 6: Get SSL certificate
echo "[6/7] Obtaining SSL certificate..."
# First, start nginx with just HTTP for the challenge
cat > /etc/nginx/sites-available/iot-api-temp << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 200 'Setting up SSL...';
    }
}
EOF
ln -sf /etc/nginx/sites-available/iot-api-temp /etc/nginx/sites-enabled/iot-api
systemctl restart nginx

certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --non-interactive --agree-tos --email admin@$DOMAIN

# Now restore the full config
sed "s/YOUR_DOMAIN_HERE/$DOMAIN/g" /tmp/ec2-nginx.conf > /etc/nginx/sites-available/iot-api
ln -sf /etc/nginx/sites-available/iot-api /etc/nginx/sites-enabled/iot-api
rm -f /etc/nginx/sites-available/iot-api-temp

# Step 7: Restart nginx
echo "[7/7] Starting Nginx..."
nginx -t
systemctl enable nginx
systemctl restart nginx

# Verify
echo ""
echo "============================================"
echo "✅ Setup complete!"
echo "============================================"
echo ""
echo "Your API is now available at:"
echo "  https://$DOMAIN/api/health"
echo "  https://$DOMAIN/api/list"
echo "  https://$DOMAIN/api/alerts"
echo ""
echo "Make sure:"
echo "  1. DNS for $DOMAIN points to this server's IP"
echo "  2. Security group allows ports 80 and 443"
echo "  3. Docker containers are running (docker-compose up -d)"
echo ""
echo "To auto-renew SSL certificates:"
echo "  sudo certbot renew --dry-run"
echo ""
