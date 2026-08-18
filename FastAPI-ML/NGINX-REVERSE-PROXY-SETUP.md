# Nginx Reverse Proxy Setup für parkhaus-wetter.roil.ch

## Übersicht

Dieses Dokument beschreibt die Konfiguration eines Nginx Reverse Proxy auf einem Linux-Server (Ubuntu) zur Ausführung der FastAPI-Anwendung hinter einer Domain mit SSL/TLS-Verschlüsselung.

**Setup-Datum:** August 2026  
**Domain:** parkhaus-wetter.roil.ch  
**Server-IP:** 87.106.21.252  
**FastAPI-Port:** 8000 (lokal)  
**Nginx-Port:** 80 (öffentlich)

---

## Architektur

```
Browser/Client
    ↓
Internet (parkhaus-wetter.roil.ch)
    ↓
Nginx Port 80/443 (Reverse Proxy)
    ↓ (intern via 127.0.0.1:8000)
FastAPI Port 8000
    ↓
Anwendung
```

---

## Komponenten

### 1. Nginx (Reverse Proxy)
- Läuft auf Port 80 (HTTP) und 443 (HTTPS)
- Leitet Anfragen zu FastAPI auf Port 8000 weiter
- Handhabt SSL/TLS-Verschlüsselung
- HTTP → HTTPS Redirect

### 2. FastAPI Anwendung
- Läuft auf Port 8000 (nur lokal, 127.0.0.1)
- Nicht direkt vom Internet erreichbar
- Wird nur von Nginx angesprochen

### 3. DNS
- Domain: parkhaus-wetter.roil.ch
- A-Record: 87.106.21.252
- NS-Records: ns141/142.servertown.ch
- CNAME für www: zeigt auf root-Domain

### 4. SSL/TLS Zertifikat
- Let's Encrypt (kostenlos)
- Auto-Renewal via Certbot

---

## Installation & Konfiguration

### Schritt 1: Nginx installieren

```bash
sudo apt update
sudo apt install nginx
```

Überprüfen:
```bash
sudo nginx -t
sudo systemctl status nginx
```

### Schritt 2: FastAPI auf Port 8000 starten

**Option A: Manuell (Entwicklung)**
```bash
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 > fastapi-ml.log 2>&1 &
```

**Option B: Systemd Service (Produktion)**

Erstelle `/etc/systemd/system/fastapi-parkhaus.service`:
```ini
[Unit]
Description=FastAPI Parkhaus ML Service
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/path/to/FastAPI-ML
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktivieren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fastapi-parkhaus
sudo systemctl start fastapi-parkhaus
```

### Schritt 3: Nginx konfigurieren

Erstelle `/etc/nginx/sites-available/parkhaus`:

```nginx
# HTTP → HTTPS Redirect
server {
    listen 80;
    server_name parkhaus-wetter.roil.ch;
    
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name parkhaus-wetter.roil.ch;
    
    # SSL Zertifikat (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/parkhaus-wetter.roil.ch/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/parkhaus-wetter.roil.ch/privkey.pem;
    
    # SSL Konfiguration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Reverse Proxy zu FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket Support (falls benötigt)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

Aktivieren:
```bash
sudo ln -s /etc/nginx/sites-available/parkhaus /etc/nginx/sites-enabled/parkhaus
sudo nginx -t
sudo systemctl restart nginx
```

### Schritt 4: SSL/TLS Zertifikat einrichten

**Installation:**
```bash
sudo apt install certbot python3-certbot-nginx
```

**Zertifikat ausstellen:**
```bash
sudo certbot certonly --standalone -d parkhaus-wetter.roil.ch
```

**Auto-Renewal überprüfen:**
```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### Schritt 5: DNS konfigurieren

Bei deinem DNS-Provider (servertown.ch):

**A-Record:**
- Host: parkhaus-wetter.roil.ch
- Typ: A
- Wert: 87.106.21.252
- TTL: 3600

**Optional - www:**
- Host: www.parkhaus-wetter.roil.ch
- Typ: CNAME
- Wert: parkhaus-wetter.roil.ch

---

## Überprüfung

### Alle Services aktiv?
```bash
sudo systemctl status nginx
sudo systemctl status fastapi-parkhaus  # falls Systemd verwendet
sudo lsof -i :80 -i :443 -i :8000
```

### Ist FastAPI erreichbar?
```bash
curl http://127.0.0.1:8000
```

### DNS korrekt?
```bash
nslookup parkhaus-wetter.roil.ch
# Sollte: 87.106.21.252 zeigen
```

### HTTPS funktioniert?
```bash
curl https://parkhaus-wetter.roil.ch
```

---

## Fehlerbehandlung

### Problem: 403 Forbidden
**Ursache:** Nginx kann FastAPI nicht erreichen  
**Lösung:**
```bash
# FastAPI läuft?
sudo lsof -i :8000

# Nginx Config ok?
sudo nginx -t

# Log checken:
sudo tail -f /var/log/nginx/error.log
```

### Problem: SSL Zertifikat existiert nicht
**Ursache:** Certbot wurde nicht ausgeführt  
**Lösung:**
```bash
sudo certbot certonly --standalone -d parkhaus-wetter.roil.ch
```

### Problem: DNS zeigt alte IP
**Ursache:** DNS-Cache nicht aktualisiert  
**Lösung:**
- Warten (TTL: bis 2 Stunden)
- Oder: DNS-Cache leeren auf Client:
  ```bash
  ipconfig /flushdns  # Windows
  sudo dscacheutil -flushcache  # macOS
  sudo systemctl restart systemd-resolved  # Linux
  ```

### Problem: Let's Encrypt Fehler "IP-Adresse stimmt nicht"
**Ursache:** DNS zeigt auf neue IP, aber Plesk auf alter IP verwaltet  
**Lösung:**
- Certbot auf dem Linux-Server (nicht Plesk) verwenden
- DNS komplett auf neue IP umgestellt haben

---

## Logging & Monitoring

### Nginx Logs
```bash
# Access Log
sudo tail -f /var/log/nginx/access.log

# Error Log
sudo tail -f /var/log/nginx/error.log
```

### FastAPI Log (manuell gestartet)
```bash
tail -f fastapi-ml.log
```

### SystemD Journal
```bash
sudo journalctl -u fastapi-parkhaus -f
```

---

## Backup & Restoration

### SSL Zertifikate sichern
```bash
sudo tar czf parkhaus-certs-backup.tar.gz /etc/letsencrypt/
```

### Nginx Konfiguration sichern
```bash
sudo tar czf nginx-config-backup.tar.gz /etc/nginx/
```

---

## Performance-Tipps

### Worker Processes (Nginx)
```nginx
worker_processes auto;  # In /etc/nginx/nginx.conf
```

### FastAPI Workers (Produktiv)
```bash
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
```

### Caching (optional)
```nginx
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## Häufige Befehle

```bash
# Nginx neu starten
sudo systemctl restart nginx

# Nginx testen
sudo nginx -t

# FastAPI neu starten (Systemd)
sudo systemctl restart fastapi-parkhaus

# Ports überprüfen
sudo lsof -i -P -n | grep LISTEN

# SSL Zertifikat Info
sudo certbot certificates

# Logs in Echtzeit
sudo tail -f /var/log/nginx/access.log
```

---

## Wartung

### Regelmäßig prüfen:
- [ ] Nginx läuft: `sudo systemctl status nginx`
- [ ] FastAPI läuft: `sudo systemctl status fastapi-parkhaus`
- [ ] Zertifikat gültig: `sudo certbot certificates`
- [ ] Disk-Platz: `df -h`
- [ ] Logs auf Fehler prüfen

### Monatlich:
- System-Updates: `sudo apt update && sudo apt upgrade`
- Certbot testen: `sudo certbot renew --dry-run`

### Jährlich:
- Zertifikate erneuern (automatisch via Certbot)
- Nginx-Version updaten

---

## Sicherheit

### Firewall (UFW)
```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### Nginx Security Header (optional)
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
```

---

## Referenzen

- Nginx Dokumentation: https://nginx.org/en/docs/
- Let's Encrypt: https://letsencrypt.org/
- FastAPI: https://fastapi.tiangolo.com/
- Certbot: https://certbot.eff.org/

---

**Letztes Update:** August 18, 2026  
**Autor:** Roger  
**Status:** Produktion aktiv ✅
