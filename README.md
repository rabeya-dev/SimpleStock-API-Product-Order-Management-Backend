# SimpleStock API

## Overview

SimpleStock API is a Django REST Framework backend for product and order management. It includes JWT authentication, product CRUD and search, authenticated order creation, inventory protection, order status management, and cancellation with stock restoration.

## Features

- User registration and JWT authentication
- Authenticated product CRUD
- Case-insensitive product search by name
- Authenticated order creation with nested items
- Backend price snapshots and total calculation
- Stock validation and atomic deduction
- Order status transitions
- Order cancellation and atomic stock restoration
- OpenAPI schema, Swagger UI, and ReDoc

## Technologies

- Python 3.14+
- Django 6.1
- Django REST Framework 3.18
- Simple JWT 5.5.1
- drf-spectacular 0.30.0
- SQLite for local development

## Project Structure

```text
accounts/       Registration, JWT URLs, and current-user API
products/       Product model, serializer, CRUD, and search
orders/         Order models, creation, status, cancellation, and tests
config/         Django settings, root URLs, ASGI, and WSGI
manage.py       Django management entry point
requirements.txt
```

## Installation

From the project directory, create and activate a virtual environment:

```powershell
py -m venv myenv
.\myenv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Configuration and Database

The project uses SQLite. Set `DJANGO_SECRET_KEY` in the environment for deployments. The development fallback in `config/settings.py` must not be used in production; also set `DEBUG = False` and configure `ALLOWED_HOSTS` before deployment.

Apply migrations:

```powershell
python manage.py migrate
```

Run the development server:

```powershell
python manage.py runserver
```

## JWT Authentication

Register a user:

```http
POST /api/auth/register/
Content-Type: application/json

{
  "username": "demo-user",
  "password": "use-a-local-password",
  "password_confirm": "use-a-local-password"
}
```

Get tokens:

```http
POST /api/auth/token/
Content-Type: application/json

{
  "username": "demo-user",
  "password": "use-a-local-password"
}
```

Send the access token on protected requests:

```text
Authorization: Bearer <access-token>
```

The current user endpoint is `GET /api/auth/me/`.

## Product API

All product endpoints require authentication.

- `GET /api/products/` lists products.
- `POST /api/products/` creates a product with `name`, `description`, `price`, and `stock`.
- `GET /api/products/<id>/` retrieves a product.
- `PUT` or `PATCH /api/products/<id>/` updates a product.
- `DELETE /api/products/<id>/` deletes a product.
- `GET /api/products/?search=phone` searches product names case-insensitively.

Example product response:

```json
{
  "id": 1,
  "name": "Notebook",
  "description": "A simple notebook",
  "price": "25.50",
  "stock": 10,
  "created_at": "2026-08-25T10:00:00Z",
  "updated_at": "2026-08-25T10:00:00Z"
}
```

## Orders

### Create an Order

`POST /api/orders/` requires authentication. The client sends only products and quantities:

```json
{
  "items": [
    {"product": 1, "quantity": 2},
    {"product": 3, "quantity": 1}
  ]
}
```

The backend supplies the authenticated user, status, product prices, subtotals, and total. It rejects empty items, invalid quantities, invalid products, duplicate products, and insufficient stock. Product rows are locked during the atomic workflow.

Example response:

```json
{
  "id": 1,
  "user": 1,
  "status": "pending",
  "total": "61.00",
  "created_at": "2026-08-25T10:00:00Z",
  "updated_at": "2026-08-25T10:00:00Z",
  "items": [
    {
      "product": 1,
      "quantity": 2,
      "unit_price": "25.50",
      "subtotal": "51.00"
    },
    {
      "product": 3,
      "quantity": 1,
      "unit_price": "10.00",
      "subtotal": "10.00"
    }
  ]
}
```

Stock is deducted only after every requested product passes validation. A failed order leaves no partial order, item, or stock change.

### Order Status

`PATCH /api/orders/<id>/status/` requires the order owner and accepts one status value:

```json
{"status": "confirmed"}
```

Allowed transitions are:

```text
pending -> confirmed -> completed
```

Status is backend-controlled. The endpoint does not change stock, prices, quantities, or totals. Completed orders cannot move backward. Cancellation is not available through this endpoint.

### Cancel an Order

`POST /api/orders/<id>/cancel/` requires the order owner and an order in `pending` or `confirmed` status. It restores each `OrderItem.quantity` to its product stock and changes the order to `cancelled` atomically.

```http
POST /api/orders/1/cancel/
Authorization: Bearer <access-token>
```

Completed and already-cancelled orders are rejected. Cancellation does not change order totals, item prices, subtotals, or quantities, and repeated cancellation does not restore stock twice.

## Swagger/OpenAPI

- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- ReDoc: `http://127.0.0.1:8000/api/redoc/`

The schema documents authentication, products, orders, status transitions, cancellation, validation errors, and protected fields.

## Testing

Run system checks, the order tests, the full suite, and migration drift checks:

```powershell
python manage.py check
python manage.py test orders
python manage.py test
python manage.py makemigrations --check --dry-run
```

## Git and GitHub

Do not commit local secrets, virtual environments, SQLite databases, Python caches, or IDE metadata. Review the working tree before committing:

```powershell
git status
git diff
git diff --stat
```

A suggested final commit is:

```powershell
git add .
git commit -m "Complete SimpleStock order management API"
```
