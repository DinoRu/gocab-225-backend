from fastapi import APIRouter

from app.api.v1 import (
    vehicle_brand, vehicle_model, parts, 
    supplier, 
    purchase_order, 
    statistics,
    dashboard,
    export,
    payment_request,
    inventory,
    purchase_request,
    auth,
    user,
    supply_request
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(vehicle_brand.router)
api_router.include_router(vehicle_model.router)
api_router.include_router(parts.router)
api_router.include_router(supplier.router)
api_router.include_router(purchase_order.router)
api_router.include_router(statistics.router)
api_router.include_router(dashboard.router)
api_router.include_router(export.router)
api_router.include_router(payment_request.router)
api_router.include_router(inventory.router)
api_router.include_router(purchase_request.router)
api_router.include_router(user.router)
api_router.include_router(supply_request.router)