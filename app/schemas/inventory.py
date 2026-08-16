import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator


class InventoryCountItemCreate(BaseModel):
    part_id: uuid.UUID
    counted_quantity: int = Field(ge=0)


class InventoryCountCreate(BaseModel):
    count_date: date
    notes: str | None = None
    items: list[InventoryCountItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup_parts(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans un comptage.")
        return self


class InventoryCountUpdate(BaseModel):
    count_date: date | None = None
    notes: str | None = None
    items: list[InventoryCountItemCreate] | None = None

    @model_validator(mode="after")
    def _validate(self):
        if self.items is not None:
            if not self.items:
                raise ValueError("Un comptage doit contenir au moins une ligne.")
            ids = [i.part_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("Une même pièce ne peut apparaître qu'une fois.")
        return self


# --- Lecture : la ligne enrichie avec le calcul des sorties ---
class InventoryCountItemRead(BaseModel):
    id: uuid.UUID
    part_id: uuid.UUID
    reference: str
    designation: str
    counted_quantity: int                    # stock compté maintenant
    previous_quantity: int | None            # None = premier comptage de cette pièce
    previous_count_date: date | None
    entries_between: int                     # entrées (commandes) depuis le précédent
    outflow: int | None                      # sorties calculées, None si premier comptage
    anomaly: bool                            # True si outflow < 0 (incohérence)


class InventoryCountRead(BaseModel):
    id: uuid.UUID
    count_number: str
    count_date: date
    notes: str | None
    items: list[InventoryCountItemRead]
    created_at: datetime


# --- Suivi d'une pièce dans le temps ---
class PartInventoryHistoryRow(BaseModel):
    count_number: str
    count_date: date
    counted_quantity: int
    previous_quantity: int | None
    entries_between: int
    outflow: int | None
    anomaly: bool
    


class InventoryCountItemEdit(BaseModel):
    part_id: uuid.UUID
    counted_quantity: int = Field(ge=0)


class InventoryCountEdit(BaseModel):
    """État final voulu du comptage (les lignes non listées sont retirées)."""
    notes: str | None = None
    items: list[InventoryCountItemEdit] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup(self):
        ids = [i.part_id for i in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Une même pièce ne peut apparaître qu'une fois dans le comptage.")
        return self


class PosteriorCount(BaseModel):
    id: uuid.UUID
    count_number: str
    count_date: date


class InventoryEditImpact(BaseModel):
    is_leaf: bool                       # True = aucun comptage postérieur ne dépend de lui
    editable_by_magazinier: bool        # = is_leaf
    posterior: list[PosteriorCount]     # comptages qui seront recalculés


class InventoryAuditEntry(BaseModel):
    id: uuid.UUID
    username: str | None
    changes: list[str]
    created_at: datetime
