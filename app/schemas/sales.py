import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Clients ----------
class SalesClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class SalesClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class SalesClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    notes: str | None
    created_at: datetime


# ---------- Produits ----------
class SalesProductCreate(BaseModel):
    reference: str | None = Field(default=None, max_length=100)
    designation: str = Field(min_length=1, max_length=255)
    default_purchase_price: Decimal | None = Field(default=None, ge=0)
    default_sale_price: Decimal | None = Field(default=None, ge=0)
    default_unit: str | None = None
    notes: str | None = None


class SalesProductUpdate(BaseModel):
    reference: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, min_length=1, max_length=255)
    default_purchase_price: Decimal | None = Field(default=None, ge=0)
    default_sale_price: Decimal | None = Field(default=None, ge=0)
    default_unit: str | None = None
    notes: str | None = None


class SalesProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reference: str | None
    designation: str
    default_purchase_price: Decimal | None
    default_sale_price: Decimal | None
    default_unit: str | None = None
    notes: str | None
    created_at: datetime


# ---------- Ventes ----------
class SalesOrderItemCreate(BaseModel):
    product_id: uuid.UUID | None = None       # None = ligne libre (hors catalogue)
    designation: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit: str = Field(default="pièce", max_length=20)
    purchase_price: Decimal = Field(ge=0)     # obligatoire → marge toujours calculable
    sale_price: Decimal = Field(ge=0)
    add_to_catalog: bool = False              # Nouveau


class SalesOrderCreate(BaseModel):
    client_id: uuid.UUID
    sale_date: date
    notes: str | None = None
    items: list[SalesOrderItemCreate] = Field(min_length=1)


class SalesOrderUpdate(BaseModel):
    client_id: uuid.UUID | None = None
    sale_date: date | None = None
    notes: str | None = None
    items: list[SalesOrderItemCreate] | None = None


class SalesOrderItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    designation: str
    quantity: int
    unit: str  
    purchase_price: Decimal
    sale_price: Decimal
    line_total: Decimal        # sale_price * quantity
    line_margin: Decimal       # (sale_price - purchase_price) * quantity
    delivered_quantity: int = 0        # 


class SalesOrderRead(BaseModel):
    id: uuid.UUID
    sale_number: str
    client_id: uuid.UUID
    client_name: str
    sale_date: date
    notes: str | None
    items: list[SalesOrderItemRead]
    total_sale: Decimal        # HT
    total_purchase: Decimal
    total_margin: Decimal
    vat_rate: Decimal          # 0.18
    vat_amount: Decimal        # TVA
    delivery_status: Literal["non_livree", "partiellement_livree", "livree"]
    payment_status: Literal["impayee", "partiellement_payee", "payee"]
    amount_paid: Decimal
    amount_due: Decimal
    total_ttc: Decimal         # TTC
    created_at: datetime
    
    
# ---------- Paiements ----------
class SalesPaymentCreate(BaseModel):
    client_id: uuid.UUID
    payment_date: date
    amount: Decimal = Field(gt=0)
    method: str | None = None
    notes: str | None = None


class PaymentAllocationRead(BaseModel):
    sales_order_id: uuid.UUID
    sale_number: str
    amount: Decimal


class SalesPaymentRead(BaseModel):
    id: uuid.UUID
    payment_number: str
    client_id: uuid.UUID
    client_name: str
    payment_date: date
    amount: Decimal
    method: str | None
    notes: str | None
    allocations: list[PaymentAllocationRead]
    created_at: datetime
    

class SaleLineEdit(BaseModel):
    id: uuid.UUID | None = None          # présent = ligne existante ; absent = nouvelle
    product_id: uuid.UUID | None = None
    designation: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit: str = Field(default="pièce", max_length=20)
    purchase_price: Decimal = Field(ge=0)
    sale_price: Decimal = Field(ge=0)


class SaleLinesUpdate(BaseModel):
    items: list[SaleLineEdit] = Field(min_length=1)
    # ids de lignes livrées qu'on retire volontairement (retours confirmés)
    returned_item_ids: list[uuid.UUID] = Field(default_factory=list)


# ---------- Grand livre ----------
class LedgerSaleRow(BaseModel):
    id: uuid.UUID
    sale_number: str
    sale_date: date
    total_sale: Decimal
    paid: Decimal
    remaining: Decimal


class LedgerEntry(BaseModel):
    date: date
    kind: str            # "sale" | "payment"
    ref: str             # VNT-… ou PAY-…
    debit: Decimal | None
    credit: Decimal | None
    running_balance: Decimal


class ClientLedgerRead(BaseModel):
    client_id: uuid.UUID
    client_name: str
    total_sold: Decimal
    total_paid: Decimal
    balance: Decimal            # solde dû
    unpaid_sales: list[LedgerSaleRow]      # vue « ventes impayées »
    entries: list[LedgerEntry]             # vue « relevé chronologique »
    
class SalesMonthly(BaseModel):
    month: str
    ca: Decimal
    benefice: Decimal


class SalesTopClient(BaseModel):
    client_id: uuid.UUID
    name: str
    ca: Decimal

class DashboardPeriodLike(BaseModel):
    start_date: date
    end_date: date

class SalesDashboardResponse(BaseModel):
    period: DashboardPeriodLike  # voir note ci-dessous
    ca: Decimal
    tva_collectee: Decimal
    depenses: Decimal
    benefice: Decimal
    creances: Decimal
    by_month: list[SalesMonthly]
    top_clients: list[SalesTopClient]
    
    
# ---------- Proformas ----------
class ProformaItemCreate(BaseModel):
    product_id: uuid.UUID | None = None
    designation: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit: str = Field(default="pièce", max_length=20)  
    sale_price: Decimal = Field(ge=0)
    add_to_catalog: bool = False


class SalesProformaCreate(BaseModel):
    client_id: uuid.UUID
    proforma_date: date
    notes: str | None = None
    items: list[ProformaItemCreate] = Field(min_length=1)


class SalesProformaUpdate(BaseModel):
    client_id: uuid.UUID | None = None
    proforma_date: date | None = None
    notes: str | None = None
    items: list[ProformaItemCreate] | None = None


class ProformaItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    designation: str
    quantity: int
    unit: str = Field(default="pièce", max_length=20)
    sale_price: Decimal
    line_total: Decimal
   

class SalesProformaRead(BaseModel):
    id: uuid.UUID
    proforma_number: str
    client_id: uuid.UUID
    client_name: str
    proforma_date: date
    status: Literal["en_cours", "convertie"]
    notes: str | None
    converted_sale_id: uuid.UUID | None
    converted_sale_number: str | None
    items: list[ProformaItemRead]
    total: Decimal
    created_at: datetime


# --- Conversion : on saisit les prix d'achat par ligne ---
class ProformaConvertItem(BaseModel):
    proforma_item_id: uuid.UUID
    purchase_price: Decimal = Field(ge=0)   # le prix de vente vient de la proforma


class ProformaConvertInput(BaseModel):
    sale_date: date
    items: list[ProformaConvertItem] = Field(min_length=1)


# Statut de livraison (dérivé)
DeliveryStatus = Literal["non_livree", "partiellement_livree", "livree"]

# ---------- Bons de livraison ----------
class DeliveryItemInput(BaseModel):
    sales_order_item_id: uuid.UUID | None = None   # None = ligne libre
    designation: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit: str = Field(default="pièce", max_length=20)
    sale_price: Decimal = Field(ge=0)


class DeliveryNoteCreate(BaseModel):
    sales_order_id: uuid.UUID
    delivery_date: date
    notes: str | None = None
    items: list[DeliveryItemInput] = Field(min_length=1)


class DeliveryItemRead(BaseModel):
    id: uuid.UUID
    sales_order_item_id: uuid.UUID | None
    designation: str
    quantity: int
    unit: str
    sale_price: Decimal
    line_total: Decimal


class DeliveryNoteRead(BaseModel):
    id: uuid.UUID
    delivery_number: str
    sales_order_id: uuid.UUID
    sale_number: str
    client_id: uuid.UUID
    client_name: str
    delivery_date: date
    notes: str | None
    items: list[DeliveryItemRead]
    total: Decimal
    created_at: datetime


# Pour le formulaire : le reste à livrer d'une vente
class DeliverableLine(BaseModel):
    sales_order_item_id: uuid.UUID
    designation: str
    unit: str
    sale_price: Decimal
    quantity_ordered: int
    quantity_delivered: int
    quantity_remaining: int


class DeliverableSale(BaseModel):
    sales_order_id: uuid.UUID
    sale_number: str
    client_id: uuid.UUID
    client_name: str
    lines: list[DeliverableLine]
    

# ================ Prix par client (marge, TVA, paiement) ================
class ClientPriceHint(BaseModel):
    purchase_price: Decimal | None
    sale_price: Decimal
    last_sale_date: date
    source: str
    