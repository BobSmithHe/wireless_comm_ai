# Deployment Guide

## Prerequisites

- Python 3.9+
- Node.js 16+
- MySQL 8.0
- Redis 6.0+

## Quick Start

```bash
# 1. Clone & init
bash scripts/init.sh

# 2. Configure .env files
vim backend/.env   # set DB credentials, DeepSeek API key

# 3. Start
bash scripts/start.sh
```

## Manual Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
python scripts/init_database.py
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run serve
```

## Production

Use gunicorn + nginx:

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.main:app
```
