"""Aggregates all v1 routers."""

from fastapi import APIRouter

from app.api.v1 import customer, health, public
from app.api.v1.admin import auth as admin_auth
from app.api.v1.admin import catalog as admin_catalog
from app.api.v1.admin import config as admin_config
from app.api.v1.admin import orders as admin_orders
from app.api.v1.admin import reports as admin_reports

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(public.router)
api_router.include_router(customer.router)
api_router.include_router(admin_auth.router)
api_router.include_router(admin_catalog.router)
api_router.include_router(admin_orders.router)
api_router.include_router(admin_config.router)
api_router.include_router(admin_reports.router)
