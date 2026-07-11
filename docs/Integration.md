# Integration Guide

# Purpose

This document explains how the capability integrates with external systems.

---

# Integration Architecture

External Client

↓

REST API

↓

FastAPI

↓

Capability Layer

↓

Database

---

# Supported Interfaces

REST API

JSON

HTTP

OpenAPI

Swagger

---

# API Base URL

http://localhost:8000

---

# Available Services

GET /health

GET /dashboard

GET /coordination

GET /users

GET /documents

POST /users

POST /documents

---

# Authentication

Current Version

No Authentication

Future Support

JWT

OAuth2

API Key

---

# Request Format

Content-Type

application/json

---

# Response Format

application/json

---

# Error Handling

400

Bad Request

404

Not Found

422

Validation Error

500

Internal Server Error

---

# Integration Workflow

Client Request

↓

Router

↓

CRUD

↓

Database

↓

JSON Response

# OpenAPI

/docs

/openapi.json

---

# Integration Checklist

Backend Running

Swagger Accessible

Health Endpoint Working

Database Connected

Docker Running