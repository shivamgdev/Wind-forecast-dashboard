# UK Wind Forecast Accuracy Dashboard

A full-stack application for evaluating UK wind generation forecasts against actual generation, helping electricity procurement teams understand forecast errors before making day-ahead purchasing decisions.

## Overview

Wind generation is variable, so electricity buyers need to understand how forecasts compare with actual output. This application analyses historical forecasts against measured generation and presents forecast accuracy, directional bias, coverage, and hourly discrepancies in an interactive dashboard.

The default analysis covers **1–31 January 2026**, with a configurable decision lead time of **24 hours**.

## Live Demo

- **Live Dashboard:** https://wind-forecast-dashboard-chi.vercel.app/
- **Backend API:** https://wind-forecast-dashboard-4nju.onrender.com
- **API Documentation:** https://wind-forecast-dashboard-4nju.onrender.com/docs
- **Health Check:** https://wind-forecast-dashboard-4nju.onrender.com/api/v1/health

The deployed application compares UK wind generation forecasts with actual generation using Elexon BMRS data. It presents forecast accuracy metrics, data coverage, hourly generation charts, and the largest forecast errors to support day-ahead electricity procurement analysis.

## Key Features

- Interactive dashboard for a configurable delivery-date range and decision lead time.
- Forecast selection based on information available by the decision cutoff.
- Comparison of hourly forecasts against actual generation.
- MAE, RMSE, and forecast bias metrics.
- Coverage statistics and identification of missing data.
- Hourly error analysis to investigate significant forecast misses.
- FastAPI backend with typed request validation and documented API endpoints.
- React, TypeScript, and Recharts frontend.
- Docker Compose setup for running the complete application locally.
- Automated backend tests covering forecast selection, calculations, and data-validation edge cases.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite |
| Charts | Recharts |
| Backend | Python 3.12, FastAPI |
| Data processing | Python, pandas, NumPy |
| Validation | Pydantic |
| Testing | pytest, pytest-asyncio |
| Web server | Nginx |
| Containerization | Docker, Docker Compose |
| Data provider | Elexon BMRS |

## Architecture

```text
User
 |
 v
React + TypeScript Dashboard
 |
 | HTTP requests to /api/*
 v
Nginx Reverse Proxy
 |
 v
FastAPI Backend
 |
 v
Analysis Service
 |
 +---- Elexon BMRS Actual Wind Generation
 |
 +---- Elexon BMRS Wind Forecasts
 |
 v
Forecast Selection and Validation
 |
 v
Hourly Matching and Accuracy Metrics
 |
 v
JSON Response to Dashboard
```

The frontend is served by Nginx. Requests to `/api/` are forwarded to the backend service through the Docker Compose network.

## Data Source

The application uses the **Elexon Balancing Mechanism Reporting Service (BMRS)** as its source for UK electricity generation data.

- **Actual generation:** FUELHH data filtered for wind generation.
- **Forecast generation:** WINDFOR forecast data.
- **Delivery time:** The target hourly period for which generation is forecast.
- **Publication time:** When the forecast became available.

Data provider: https://bmrs.elexon.co.uk/

The analysis uses UTC timestamps to align forecast publications, delivery periods, and actual generation consistently.

## Forecast Selection Method

For each hourly delivery period:

1. Calculate the decision cutoff by subtracting the configured decision lead time from the delivery time.
2. Consider forecasts for that delivery period published at or before the cutoff.
3. Select the latest eligible publication.
4. Compare the selected forecast with actual generation for the same delivery hour.

Forecasts published after the cutoff are excluded to avoid using information that would not have been available at the assumed procurement decision time.

The decision lead time is an analytical assumption. A 24-hour lead time is used by default and can be changed for sensitivity analysis.

### Actual Generation Matching

Actual generation is provided in half-hourly intervals. The application averages the two corresponding half-hourly values to calculate the hourly actual generation.

Incomplete actual-data pairs are marked as missing rather than being filled with zero.

## Accuracy Metrics

Let \(F_t\) represent forecast generation and \(A_t\) represent actual generation for each matched hour.

- **Mean Absolute Error (MAE):** Average absolute difference between forecast and actual generation.
- **Root Mean Squared Error (RMSE):** Square root of the average squared forecast error; larger misses have greater influence.
- **Bias:** Average signed error, calculated as forecast minus actual generation.

A positive bias indicates overforecasting; a negative bias indicates underforecasting.

Metrics are calculated only for hours with both a valid selected forecast and complete actual data.

## January 2026 Evaluation

The following results were verified using the application API for 1–31 January 2026 with a 24-hour decision lead time.

| Metric | Result |
|---|---:|
| Mean Absolute Error (MAE) | 2,064.14 MW |
| Root Mean Squared Error (RMSE) | 2,524.28 MW |
| Bias | +1,854.60 MW |
| Total hourly intervals | 744 |
| Matched intervals | 744 |
| Coverage | 100% |
| Missing forecast hours | 0 |
| Missing actual hours | 0 |

### Interpretation

The positive bias indicates that the selected forecasts overestimated actual wind generation on average during the evaluation period. Overforecasting may lead a buyer to underestimate the amount of electricity that must be procured from other sources.

RMSE is higher than MAE, indicating that larger errors have a meaningful influence on overall forecast performance.

Complete coverage means every hourly interval had both a selected forecast and complete actual data. It does not mean the forecasts were accurate.

These results describe the selected historical period and decision-lead assumption. They should not be treated as a guarantee of future forecast performance or financial savings.

## Prerequisites

- Docker Desktop with Docker Compose support.
- Alternatively, Python 3.12 and Node.js 22 or a compatible version for local development.

An active internet connection is required when retrieving live data from Elexon BMRS.

## Run with Docker Compose

From the project root:

```bash
docker compose up --build -d
```

Open the application:

- Dashboard: http://localhost:8080
- API documentation: http://localhost:8000/docs
- Health endpoint: http://localhost:8000/api/v1/health

Check running containers:

```bash
docker compose ps
```

Check backend health:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

View backend logs:

```bash
docker compose logs -f backend
```

Stop the application:

```bash
docker compose down
```

## API Reference

### Health Check

`GET /api/v1/health`

Returns the backend health status.

### Wind Forecast Analysis

`GET /api/v1/analysis`

Supported query parameters:

| Parameter | Default | Description |
|---|---|---|
| `start_date` | `2026-01-01` | First delivery date |
| `end_date` | `2026-01-31` | Last delivery date, inclusive |
| `decision_lead_hours` | `24` | Hours before delivery used as the decision cutoff |

The date range cannot exceed 31 calendar days, and the decision lead time must be between 0 and 168 hours.

Example:

```text
http://localhost:8000/api/v1/analysis?start_date=2026-01-01&end_date=2026-01-31&decision_lead_hours=24
```

The response contains:

- `metrics`: MAE, RMSE, and bias in MW.
- `coverage`: Total, matched, and missing hourly intervals.
- `intervals`: Delivery time, selected publication time, forecast, actual, error, and status for each hour.

Interactive API documentation is available at `/docs`.

## Testing

Run the backend test suite inside the running Docker container:

```bash
docker compose exec backend pytest -q
```

The backend test suite has been verified with **27 passing tests**.

Build the frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

Run the frontend linter:

```bash
npm --prefix frontend run lint
```

The frontend build has been verified successfully. The linter can be run separately to check the current source code.

## Project Structure

```text
energy-wind-accuracy/
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- analysis.py
|   |   |-- analysis_service.py
|   |   `-- elexon_client.py
|   |-- tests/
|   |-- requirements.txt
|   `-- Dockerfile
|-- frontend/
|   |-- src/
|   |-- public/
|   |-- package.json
|   |-- nginx.conf
|   `-- Dockerfile
`-- docker-compose.yml
```

## Assumptions and Limitations

- The analysis covers UK national wind generation, not an individual wind farm or a specific procurement portfolio.
- The 24-hour decision lead is an explicit analytical assumption, not proof of a particular trading desk's operational cutoff.
- Hourly actual generation is derived by averaging the two corresponding half-hourly values.
- Accuracy metrics exclude intervals where either the selected forecast or complete actual data is unavailable.
- Historical accuracy does not directly measure procurement cost, imbalance exposure, or realised financial savings.
- Forecast availability, source-data revisions, and API behavior may affect future live queries.
- This is an analytical decision-support prototype, not an automated trading system or a guarantee of procurement outcomes.

## AI Tool Disclosure

ChatGPT was used to assist with implementation planning, debugging, analysis review, and documentation. The developer reviewed the implementation, ran the automated tests, and verified the January 2026 analysis through the running API.

AI assistance does not replace validation against the source data or independent review of procurement decisions.

## Deployment

The application is deployed with a Vercel frontend and a Render-hosted FastAPI backend.

 Frontend: https://wind-forecast-dashboard-chi.vercel.app/

 Backend: https://wind-forecast-dashboard-4nju.onrender.com

 API documentation: https://wind-forecast-dashboard-4nju.onrender.com/docs

 Health check: https://wind-forecast-dashboard-4nju.onrender.com/api/v1/health

The deployed dashboard was verified to load the January 2026 analysis, including forecast accuracy metrics, hourly charts, and interval-level results.

## Demo

**Unlisted YouTube demonstration:** To be added after recording and uploading the final walkthrough.

The planned demonstration will cover the customer-facing problem and dashboard first, followed by the technical architecture, forecast-selection logic, accuracy calculations, and test results.
