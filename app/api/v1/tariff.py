from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep
from app.api.auth_deps import require_role
from app.core.pagination import PaginationDep
from app.schemas.common import Page, to_page
from app.schemas.tariff import (
    TariffBrandCreate, TariffBrandRead, TariffModelCreate, TariffModelRead, TariffModelsBulkCreate, TariffSupplierCreate, TariffSupplierRead, TariffSupplierUpdate,
    TariffArticleCreate, TariffArticleRead, TariffArticleUpdate,
    TariffPriceCreate, TariffPriceRead,
    ArticlePricesView, SupplierPricesView,
)
from app.services.tariff import (
    TariffBrandService, TariffModelService, TariffSupplierService, TariffArticleService, TariffPriceService,
)

router = APIRouter(
    prefix="/tariffs",
    tags=["tariffs"],
    dependencies=[Depends(require_role("admin"))],
)


# ---------- Fournisseurs ----------
@router.get("/suppliers", response_model=Page[TariffSupplierRead])
async def list_suppliers(session: SessionDep, pagination: PaginationDep,
                         search: Annotated[str | None, Query(max_length=255)] = None):
    items, total = await TariffSupplierService(session).list_suppliers(
        search=search, page=pagination.page, limit=pagination.limit)
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.post("/suppliers", response_model=TariffSupplierRead, status_code=status.HTTP_201_CREATED)
async def create_supplier(payload: TariffSupplierCreate, session: SessionDep):
    return await TariffSupplierService(session).create(payload)


@router.patch("/suppliers/{supplier_id}", response_model=TariffSupplierRead)
async def update_supplier(supplier_id: UUID, payload: TariffSupplierUpdate, session: SessionDep):
    return await TariffSupplierService(session).update(supplier_id, payload)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(supplier_id: UUID, session: SessionDep):
    await TariffSupplierService(session).delete(supplier_id)


@router.get("/suppliers/{supplier_id}/prices", response_model=SupplierPricesView)
async def supplier_prices(supplier_id: UUID, session: SessionDep):
    return await TariffPriceService(session).supplier_prices_view(supplier_id)


# ---------- Articles ----------
@router.get("/articles", response_model=Page[TariffArticleRead])
async def list_articles(session: SessionDep, pagination: PaginationDep,
                        search: Annotated[str | None, Query(max_length=255)] = None):
    items, total = await TariffArticleService(session).list_articles(
        search=search, page=pagination.page, limit=pagination.limit)
    return to_page(items, total=total, page=pagination.page, limit=pagination.limit)


@router.get("/articles/next-reference")
async def next_article_reference(session: SessionDep):
    ref = await TariffArticleService(session).next_reference()
    return {"reference": ref}


@router.post("/articles", response_model=TariffArticleRead, status_code=status.HTTP_201_CREATED)
async def create_article(payload: TariffArticleCreate, session: SessionDep):
    a = await TariffArticleService(session).create(payload)
    return {
        "id": a.id, "reference": a.reference, "designation": a.designation,
        "model_id": a.model_id, "brand_name": a.model.brand.name, "model_name": a.model.name,
        "notes": a.notes, "supplier_count": 0, "best_price": None, "created_at": a.created_at,
    }


@router.patch("/articles/{article_id}", response_model=TariffArticleRead)
async def update_article(article_id: UUID, payload: TariffArticleUpdate, session: SessionDep):
    svc = TariffArticleService(session)
    a = await svc.update(article_id, payload)
    last = await svc._last_prices_for_article(a.id)
    prices = [p for (p, _d) in last.values()]
    return {
        "id": a.id, "reference": a.reference, "designation": a.designation,
        "model_id": a.model_id, "brand_name": a.model.brand.name, "model_name": a.model.name,
        "notes": a.notes, "supplier_count": len(last),
        "best_price": min(prices) if prices else None, "created_at": a.created_at,
    }

@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(article_id: UUID, session: SessionDep):
    await TariffArticleService(session).delete(article_id)


@router.get("/articles/{article_id}/prices", response_model=ArticlePricesView)
async def article_prices(article_id: UUID, session: SessionDep):
    return await TariffArticleService(session).article_prices_view(article_id)


# ---------- Prix ----------
@router.post("/prices", response_model=TariffPriceRead, status_code=status.HTTP_201_CREATED)
async def create_price(payload: TariffPriceCreate, session: SessionDep):
    p = await TariffPriceService(session).create(payload)
    return {"id": p.id, "article_id": p.article_id, "supplier_id": p.supplier_id,
            "supplier_name": p.supplier.name, "price": p.price,
            "effective_date": p.effective_date, "notes": p.notes, "created_at": p.created_at}


@router.delete("/prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price(price_id: UUID, session: SessionDep):
    await TariffPriceService(session).delete(price_id)


# ---------- Marques ----------
@router.get("/brands", response_model=list[TariffBrandRead])
async def list_brands(session: SessionDep):
    return await TariffBrandService(session).list_brands()

@router.post("/brands", response_model=TariffBrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(payload: TariffBrandCreate, session: SessionDep):
    return await TariffBrandService(session).create(payload)

@router.delete("/brands/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(brand_id: UUID, session: SessionDep):
    await TariffBrandService(session).delete(brand_id)

# ---------- Modèles ----------
@router.get("/models", response_model=list[TariffModelRead])
async def list_models(session: SessionDep, brand_id: Annotated[UUID | None, Query()] = None):
    return await TariffModelService(session).list_models(brand_id=brand_id)

@router.post("/models", response_model=TariffModelRead, status_code=status.HTTP_201_CREATED)
async def create_model(payload: TariffModelCreate, session: SessionDep):
    return await TariffModelService(session).create(payload)

@router.post("/models/bulk", response_model=list[TariffModelRead], status_code=status.HTTP_201_CREATED)
async def create_models_bulk(payload: TariffModelsBulkCreate, session: SessionDep):
    return await TariffModelService(session).create_bulk(payload.brand_id, payload.names)

@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: UUID, session: SessionDep):
    await TariffModelService(session).delete(model_id)