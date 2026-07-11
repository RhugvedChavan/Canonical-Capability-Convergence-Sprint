# API Documentation

Base URL

http://localhost:8000

---

# Health

GET /health

Response

{
    "status":"healthy",
    "version":"1.0.0"
}

---

# Dashboard

GET /dashboard

Returns dashboard statistics.

---

# Coordination

GET /coordination

Returns workflow status.

---

# Users

GET /users

Returns user list.

POST /users

Creates user.

Example

{
"name":"John",
"email":"john@example.com"
}

---

# Documents

GET /documents

Returns document list.

POST /documents

Creates document.

Example

{
"title":"Architecture",
"content":"Capability Documentation"
}

---

# Standard Response

Success

{
"success":true,
"data":{}
}

Error

{
"success":false,
"error":"Validation Error"
}

---
