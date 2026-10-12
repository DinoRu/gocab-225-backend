from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import constraint_name
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.pagination import paginate
from app.models.tariff import TariffSupplier, TariffArticle, TariffPrice, TariffBrand, TariffModel


# ======================= FOURNISSEURS =======================
class TariffSupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_suppliers(self, *, search, page, limit):
        stmt = select(TariffSupplier)
        if search:
            stmt = stmt.where(TariffSupplier.name.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(TariffSupplier.name.asc())
        return await paginate(self.session, stmt, page=page, limit=limit)

    async def get_or_404(self, supplier_id: UUID) -> TariffSupplier:
        s = await self.session.get(TariffSupplier, supplier_id)
        if s is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
        return s

    async def create(self, data):
        s = TariffSupplier(**data.model_dump())
        self.session.add(s)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_tariff_suppliers_name":
                raise ConflictError("Un fournisseur porte déjà ce nom.") from exc
            raise
        await self.session.refresh(s)
        return s

    async def update(self, supplier_id: UUID, data):
        s = await self.get_or_404(supplier_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(s, k, v)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_tariff_suppliers_name":
                raise ConflictError("Un fournisseur porte déjà ce nom.") from exc
            raise
        await self.session.refresh(s)
        return s

    async def delete(self, supplier_id: UUID) -> None:
        s = await self.get_or_404(supplier_id)
        await self.session.delete(s)   # cascade → ses prix disparaissent
        await self.session.commit()


# ======================= ARTICLES =======================
class TariffArticleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        
    async def next_reference(self) -> str:
        """Prochaine référence séquentielle libre : ART-0001, ART-0002…"""
        prefix = "ART-"
        # numéro après 'ART-' → entier, on prend le max parmi les réf au format ART-nnnn
        seq = cast(func.substring(TariffArticle.reference, len(prefix) + 1), Integer)
        last = await self.session.scalar(
            select(func.coalesce(func.max(seq), 0)).where(
                TariffArticle.reference.op("~")(r'^ART-\d+$')
            )
        )
        return f"{prefix}{(last or 0) + 1:04d}"

    async def get_or_404(self, article_id: UUID) -> TariffArticle:
        a = await self.session.get(TariffArticle, article_id)
        if a is None:
            raise NotFoundError(f"Article {article_id} introuvable.")
        return a

    async def _last_prices_for_article(self, article_id: UUID) -> dict[UUID, tuple[Decimal, date]]:
        """Dernier prix par fournisseur pour un article. {supplier_id: (prix, date)}."""
        rows = (await self.session.execute(
            select(TariffPrice)
            .where(TariffPrice.article_id == article_id)
            .order_by(TariffPrice.effective_date.desc(), TariffPrice.created_at.desc())
        )).scalars().all()
        last: dict[UUID, tuple[Decimal, date]] = {}
        for p in rows:
            # la 1re rencontrée pour un fournisseur (tri desc) est la plus récente
            if p.supplier_id not in last:
                last[p.supplier_id] = (p.price, p.effective_date)
        return last

    async def list_articles(self, *, search, page, limit):
        stmt = select(TariffArticle).options(
            selectinload(TariffArticle.model).selectinload(TariffModel.brand)
        )
        if search:
            s = f"%{search.strip()}%"
            stmt = stmt.where(
                TariffArticle.designation.ilike(s) | TariffArticle.reference.ilike(s)
            )
        stmt = stmt.order_by(TariffArticle.designation.asc())
        items, total = await paginate(self.session, stmt, page=page, limit=limit)

        # enrichir chaque article : nb fournisseurs + meilleur prix
        out = []
        for a in items:
            last = await self._last_prices_for_article(a.id)
            prices = [p for (p, _d) in last.values()]
            out.append({
                "id": a.id,
                "reference": a.reference,
                "designation": a.designation,
                "model_id": a.model_id,
                "brand_name": a.model.brand.name,
                "model_name": a.model.name,
                "notes": a.notes,
                "supplier_count": len(last),
                "best_price": min(prices) if prices else None,
                "created_at": a.created_at,
            })
        return out, total
        return out, total

    async def create(self, data):
        payload = data.model_dump()
        for _ in range(5):
            if not payload.get("reference"):
                payload["reference"] = await self.next_reference()
            a = TariffArticle(**payload)
            self.session.add(a)
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if constraint_name(exc) == "uq_tariff_articles_reference":
                    payload["reference"] = None   # regénère au tour suivant
                    continue
                raise
            await self.session.refresh(a)
            return a
        raise ConflictError("Impossible de générer une référence unique.")

    async def update(self, article_id: UUID, data):
        a = await self.get_or_404(article_id)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(a, k, v)
        await self.session.commit()
        await self.session.refresh(a)
        return a

    async def delete(self, article_id: UUID) -> None:
        a = await self.get_or_404(article_id)
        await self.session.delete(a)   # cascade → ses prix disparaissent
        await self.session.commit()

    async def article_prices_view(self, article_id: UUID) -> dict:
        """Vue par article : chaque fournisseur avec son dernier prix + historique, triés."""
        a = await self.get_or_404(article_id)
        # tous les prix de cet article, groupés par fournisseur
        rows = (await self.session.execute(
            select(TariffPrice)
            .where(TariffPrice.article_id == article_id)
            .order_by(TariffPrice.effective_date.desc(), TariffPrice.created_at.desc())
        )).scalars().all()

        by_supplier: dict[UUID, list[TariffPrice]] = {}
        for p in rows:
            by_supplier.setdefault(p.supplier_id, []).append(p)

        suppliers = []
        for sid, plist in by_supplier.items():
            plist_sorted = plist  # déjà trié desc
            last = plist_sorted[0]
            suppliers.append({
                "supplier_id": sid,
                "supplier_name": last.supplier.name,
                "last_price": last.price,
                "last_date": last.effective_date,
                "history": [
                    {
                        "id": p.id, "article_id": p.article_id, "supplier_id": p.supplier_id,
                        "supplier_name": p.supplier.name, "price": p.price,
                        "effective_date": p.effective_date, "notes": p.notes, "created_at": p.created_at,
                    }
                    for p in plist_sorted
                ],
            })
        # tri du moins cher au plus cher (par dernier prix)
        suppliers.sort(key=lambda s: s["last_price"])
        return {
            "article_id": a.id,
            "designation": a.designation,
            "reference": a.reference,
            "suppliers": suppliers,
        }


# ======================= PRIX =======================
class TariffPriceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data):
        # vérifs d'existence
        if await self.session.get(TariffArticle, data.article_id) is None:
            raise NotFoundError("Article introuvable.")
        if await self.session.get(TariffSupplier, data.supplier_id) is None:
            raise NotFoundError("Fournisseur introuvable.")
        p = TariffPrice(
            article_id=data.article_id,
            supplier_id=data.supplier_id,
            price=data.price,
            effective_date=data.effective_date,
            notes=data.notes,
        )
        self.session.add(p)   # nouvelle ligne d'historique, jamais d'écrasement
        await self.session.commit()
        await self.session.refresh(p)
        return p

    async def delete(self, price_id: UUID) -> None:
        p = await self.session.get(TariffPrice, price_id)
        if p is None:
            raise NotFoundError(f"Prix {price_id} introuvable.")
        await self.session.delete(p)   # suppression d'une ligne erronée
        await self.session.commit()

    async def supplier_prices_view(self, supplier_id: UUID) -> dict:
        """Vue par fournisseur : ses articles avec leur dernier prix."""
        s = await self.session.get(TariffSupplier, supplier_id)
        if s is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
        rows = (await self.session.execute(
            select(TariffPrice)
            .where(TariffPrice.supplier_id == supplier_id)
            .order_by(TariffPrice.effective_date.desc(), TariffPrice.created_at.desc())
        )).scalars().all()

        seen: set[UUID] = set()
        articles = []
        for p in rows:
            if p.article_id in seen:
                continue           # on ne garde que le dernier prix par article
            seen.add(p.article_id)
            articles.append({
                "article_id": p.article_id,
                "designation": p.article.designation,
                "reference": p.article.reference,
                "last_price": p.price,
                "last_date": p.effective_date,
            })
        articles.sort(key=lambda x: x["designation"])
        return {
            "supplier_id": s.id,
            "supplier_name": s.name,
            "articles": articles,
        }


class TariffBrandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_brands(self):
        rows = (await self.session.scalars(select(TariffBrand).order_by(TariffBrand.name))).all()
        return rows

    async def create(self, data):
        b = TariffBrand(name=data.name.strip())
        self.session.add(b)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_tariff_brands_name":
                raise ConflictError("Cette marque existe déjà.") from exc
            raise
        await self.session.refresh(b)
        return b

    async def delete(self, brand_id: UUID) -> None:
        b = await self.session.get(TariffBrand, brand_id)
        if b is None:
            raise NotFoundError("Marque introuvable.")
        await self.session.delete(b)   # cascade → ses modèles (RESTRICT bloquera si articles liés)
        await self.session.commit()


class TariffModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_models(self, *, brand_id=None):
        stmt = select(TariffModel).order_by(TariffModel.name)
        if brand_id:
            stmt = stmt.where(TariffModel.brand_id == brand_id)
        rows = (await self.session.scalars(stmt)).all()
        return [
            {"id": m.id, "brand_id": m.brand_id, "brand_name": m.brand.name, "name": m.name}
            for m in rows
        ]

    async def create(self, data):
        if await self.session.get(TariffBrand, data.brand_id) is None:
            raise NotFoundError("Marque introuvable.")
        m = TariffModel(brand_id=data.brand_id, name=data.name.strip())
        self.session.add(m)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if constraint_name(exc) == "uq_tariff_models_brand_name":
                raise ConflictError("Ce modèle existe déjà pour cette marque.") from exc
            raise
        await self.session.refresh(m)
        return {"id": m.id, "brand_id": m.brand_id, "brand_name": m.brand.name, "name": m.name}

    async def create_bulk(self, brand_id: UUID, names: list[str]) -> list[dict]:
        brand = await self.session.get(TariffBrand, brand_id)
        if brand is None:
            raise NotFoundError("Marque introuvable.")

        # modèles déjà existants pour cette marque (pour ignorer les doublons)
        existing = {
            n.lower() for n in (await self.session.scalars(
                select(TariffModel.name).where(TariffModel.brand_id == brand_id)
            )).all()
        }

        created = []
        seen_in_batch: set[str] = set()
        for raw in names:
            name = raw.strip()
            key = name.lower()
            if not name or key in existing or key in seen_in_batch:
                continue   # vide, déjà en base, ou en double dans le lot → ignoré
            seen_in_batch.add(key)
            m = TariffModel(brand_id=brand_id, name=name)
            self.session.add(m)
            created.append(m)

        if created:
            await self.session.commit()
            for m in created:
                await self.session.refresh(m)

        return [
            {"id": m.id, "brand_id": m.brand_id, "brand_name": brand.name, "name": m.name}
            for m in created
        ]

    async def delete(self, model_id: UUID) -> None:
        m = await self.session.get(TariffModel, model_id)
        if m is None:
            raise NotFoundError("Modèle introuvable.")
        try:
            await self.session.delete(m)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise BusinessRuleError("Ce modèle est utilisé par des articles et ne peut pas être supprimé.") from exc