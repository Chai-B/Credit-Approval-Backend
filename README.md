# Credit Approval System Backend

A highly optimized, brutally minimal Django 4 + Django REST Framework backend for a Credit Approval System.

Built strictly under a monolithic architecture constraint, consolidating standard Django boilerplate (routing, settings, celery tasks, REST serializers, and business logic mapping) entirely into an extremely lean footprint.

## Tech Stack
- Django 4.2+ / DRF
- PostgreSQL 15
- Redis 7
- Celery
- Pandas (for asynchronous data ingestion)
- Gunicorn
- Docker & Docker Compose

## Core Features
1. **Background Data Ingestion**: Zero-downtime `.xlsx` data parsing using Pandas & Celery `bulk_create` UPSERTs on boot.
2. **EMI Calculation Engine**: Dynamic compound interest mathematically isolated and executed on DB transactions.
3. **Credit Scoring Heuristics Engine**: Real-time scoring out of 100 based upon historical payment ratios, loan volumes, and active constraints.
4. **Stateless Scale**: Decoupled HTTP workers, persistent database voluming, and strict broker decoupling.

## Local Deployment (Dockerized)

Ensure you have Docker & Docker Compose installed. You do not need Python installed locally.

```bash
# 1. Clone the repository
git clone https://github.com/Chai-B/Credit-Approval-System-Backend.git
cd Credit-Approval-System-Backend

# 2. Add your excel files
# Ensure `customer_data.xlsx` and `loan_data.xlsx` exist in the `data/` folder.

# 3. Boot the cluster
docker-compose up --build -d
```
*Note: The moment the web container turns on, it will automatically push a signal to Celery to read the Excel files and hydrate your PostgreSQL database natively.*

## API Endpoints

Once running, the application binds to `http://localhost:8000`.

- `POST /register`: Ingests an individual and mathematically rounds their `monthly_salary * 36` to create an approved limit.
- `POST /check-eligibility`: Calculates if a customer is safe to provide a loan to based on historical repayment activity, capping limits at 50% max-EMI-to-Salary margins.
- `POST /create-loan`: Formally binds a loan to a user, incrementing their dynamic real-time `current_debt` active trackers.
- `GET /view-loan/{loan_id}`: Standard serialized output of a specific historic loan.
- `GET /view-loans/{customer_id}`: Standard serialized output of all active loans attached to a specific Customer ID.
