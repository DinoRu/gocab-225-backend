from app.models.vehicle_model import VehicleModel
from app.repositories.base import BaseRepository


class VehicleModelRepository(BaseRepository[VehicleModel]):
    model = VehicleModel
    
    