# Deployment Guide

---

# Requirements

Python 3.11+

Docker Desktop

Git

---

# Install Dependencies

pip install -r requirements.txt

---

# Run Backend

uvicorn app.main:app --reload

---

# Backend URL

http://localhost:8000

---

# Swagger

http://localhost:8000/docs

---

# Docker Build

docker compose build

---

# Docker Run

docker compose up

---

# Detached Mode

docker compose up -d

---

# Stop

docker compose down

---

# Verify

docker ps

---

# Health Check

GET

/health

---

# Environment Variables

DATABASE_URL

HOST

PORT

LOG_LEVEL

APP_VERSION

# Production Checklist

Dependencies Installed
Backend Running
Docker Running
Health Endpoint Working
OpenAPI Accessible
Logs Enabled
Capability Registered
Deployment Successful