# VPS deploy med domener (Nginx + Let's Encrypt)

Denne guiden beskriver host-basert routing for to RAG-tjenester:

- `innorag.haven.digipomps.org` -> `127.0.0.1:8101`
- `doc.haven.digipomps.org` -> `127.0.0.1:8102`

## 1) Nginx host routing (HTTP)

Eksempel konfig (`/etc/nginx/sites-available/rag_proxy.conf`):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name innorag.haven.digipomps.org;

    location / {
        proxy_pass http://127.0.0.1:8101;
        include /etc/nginx/proxy_params;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name doc.haven.digipomps.org;

    location / {
        proxy_pass http://127.0.0.1:8102;
        include /etc/nginx/proxy_params;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 300;
    }
}
```

Aktiver og reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 2) HTTPS med Let's Encrypt

Installer certbot:

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
```

Opprett/oppdater sertifikat:

```bash
sudo certbot --nginx \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  -d innorag.haven.digipomps.org \
  -d doc.haven.digipomps.org \
  --redirect
```

Certbot oppretter automatisk renew timer (`certbot.timer`).

## 3) Verifisering

```bash
curl -fsS https://innorag.haven.digipomps.org/health
curl -fsS https://doc.haven.digipomps.org/health
```

Begge skal returnere:

```json
{"ok":true}
```
