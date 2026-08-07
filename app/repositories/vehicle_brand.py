from app.models.vehicle_brand import VehicleBrand
from app.repositories.base import BaseRepository


class VehicleBrandRepository(BaseRepository[VehicleBrand]):
    model = VehicleBrand
    
    