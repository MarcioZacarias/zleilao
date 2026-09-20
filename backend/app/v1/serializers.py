"""Montagem dos DTOs de item/pregao com os dados relacionados (fonte,
categoria, campos de card, duplicados). Centralizado para portal e admin
devolverem exatamente a mesma forma."""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.category_fields import effective_fields
from app.engine.geo import haversine_km
from app.models import Auction, Category, CategoryField, Item, ItemDuplicate, ItemOpportunity, PriceReference, Source
from app.schemas import (
    AuctionOut, AuctionSessionOut, CategoryFieldOut, DuplicateRefOut, ItemAdminOut, ItemCardOut,
    ItemDetailOut, ItemPriceHistoryOut, OpportunityOut,
)


class SerializerContext:
    """Cache por requisicao: fontes, categorias, campos de card, duplicados."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.sources: dict[int, Source] = {}
        self.categories: dict[int, Category] = {}
        self.card_keys: dict[int, list[CategoryField]] = {}
        self.field_defs: dict[int, list[tuple[CategoryField, Category]]] = {}
        self.dup_ids: set[int] = set()
        self.opportunities: dict[int, ItemOpportunity] = {}
        #: centro da busca por raio, quando houver — preenchido pela rota.
        self.center: tuple[float, float] | None = None

    async def load(self, items: list[Item]) -> "SerializerContext":
        if not self.sources:
            self.sources = {s.id: s for s in (await self.db.execute(select(Source))).scalars().all()}
        if not self.categories:
            self.categories = {c.id: c for c in (await self.db.execute(select(Category))).scalars().all()}
        ids = [i.id for i in items]
        if ids:
            rows = (await self.db.execute(select(ItemDuplicate.canonical_item_id, ItemDuplicate.duplicate_item_id).where(
                ItemDuplicate.status.in_(("suspected", "confirmed")),
                or_(ItemDuplicate.canonical_item_id.in_(ids), ItemDuplicate.duplicate_item_id.in_(ids)),
            ))).all()
            for a, b in rows:
                self.dup_ids.add(a)
                self.dup_ids.add(b)
        if ids:
            for opp in (await self.db.execute(
                select(ItemOpportunity).where(ItemOpportunity.item_id.in_(ids))
            )).scalars().all():
                self.opportunities[opp.item_id] = opp
        for cid in {i.category_id for i in items if i.category_id}:
            await self.fields_for(cid)
        return self

    async def fields_for(self, category_id: int) -> list[tuple[CategoryField, Category]]:
        if category_id not in self.field_defs:
            cat = self.categories.get(category_id) or await self.db.get(Category, category_id)
            self.field_defs[category_id] = await effective_fields(self.db, cat) if cat else []
            self.card_keys[category_id] = [f for f, _ in self.field_defs[category_id] if f.show_in_card]
        return self.field_defs[category_id]

    def card(self, item: Item) -> ItemCardOut:
        src = self.sources.get(item.source_id)
        cat = self.categories.get(item.category_id) if item.category_id else None
        attrs = item.attributes or {}
        card_fields = {f.key: attrs.get(f.key) for f in self.card_keys.get(item.category_id or -1, []) if attrs.get(f.key) is not None}
        auction_type = item.auction.auction_type if getattr(item, "auction", None) else None
        return ItemCardOut(
            id=item.id, item_type=item.item_type, title=item.title, lot_number=item.lot_number,
            price=item.price, price_kind=item.price_kind, price_second=item.price_second,
            image_url=item.image_url, city=item.city, state=item.state, brand=item.brand, model=item.model,
            year_model=item.year_model, km=item.km, condition=item.condition, status=item.status,
            next_session_at=item.next_session_at, last_seen_at=item.last_seen_at,
            source_id=item.source_id, source_name=src.name if src else None, source_slug=src.slug if src else None,
            category_id=item.category_id, category_slug=cat.slug if cat else None, category_name=cat.name if cat else None,
            auction_id=item.auction_id, auction_type=auction_type, card_fields=card_fields,
            possible_duplicate=item.id in self.dup_ids,
            opportunity_score=opp.score if (opp := self.opportunities.get(item.id)) else None,
            opportunity_discount=opp.discount_pct if opp else None,
            distance_km=self._distance(item),
        )

    def _distance(self, item: Item) -> float | None:
        """Distância até o centro da busca. É a distância entre os municípios,
        não até o pátio: o lote não tem endereço, tem cidade."""
        if not self.center or item.lat is None or item.lng is None:
            return None
        return round(haversine_km(self.center[0], self.center[1], float(item.lat), float(item.lng)), 1)

    def field_defs_out(self, category_id: int | None) -> list[CategoryFieldOut]:
        if not category_id:
            return []
        cat = self.categories.get(category_id)
        out = []
        for f, owner in self.field_defs.get(category_id, []):
            dto = CategoryFieldOut.model_validate(f)
            dto.inherited_from = owner.slug if (cat and owner.id != cat.id) else None
            out.append(dto)
        return out

    async def detail(self, item: Item, disclaimer: str | None) -> ItemDetailOut:
        await self.fields_for(item.category_id) if item.category_id else None
        base = self.card(item).model_dump()
        auction_out = await self.auction(item.auction) if item.auction else None
        dups: list[DuplicateRefOut] = []
        rows = (await self.db.execute(select(ItemDuplicate).where(
            ItemDuplicate.status.in_(("suspected", "confirmed")),
            or_(ItemDuplicate.canonical_item_id == item.id, ItemDuplicate.duplicate_item_id == item.id),
        ))).scalars().all()
        for d in rows:
            other_id = d.duplicate_item_id if d.canonical_item_id == item.id else d.canonical_item_id
            other = await self.db.get(Item, other_id)
            if other:
                osrc = self.sources.get(other.source_id)
                dups.append(DuplicateRefOut(item_id=other.id, title=other.title, source_name=osrc.name if osrc else None,
                                            official_url=other.official_url, similarity=d.similarity, status=d.status))
        public_attrs = {k: v for k, v in (item.attributes or {}).items() if not k.startswith("_")}
        return ItemDetailOut(
            **base,
            description=item.description, images=item.images or [], attributes=public_attrs,
            field_defs=self.field_defs_out(item.category_id), official_url=item.official_url,
            location_text=item.location_text, auction=auction_out,
            price_history=[ItemPriceHistoryOut.model_validate(p) for p in (item.price_history or [])],
            duplicates=dups, first_seen_at=item.first_seen_at, disclaimer=disclaimer,
            extraction_status=item.extraction_status, extraction_version=item.extraction_version,
            opportunity=await self.opportunity(item),
        )

    async def opportunity(self, item: Item) -> OpportunityOut | None:
        """RN-010: score com a referência nomeada. Sem referência confiável,
        devolve None e o portal mostra "sem referência de mercado"."""
        opp = self.opportunities.get(item.id)
        if not opp:
            opp = await self.db.scalar(select(ItemOpportunity).where(ItemOpportunity.item_id == item.id))
        if not opp:
            return None
        dto = OpportunityOut.model_validate(opp)
        ref = await self.db.get(PriceReference, opp.price_reference_id) if opp.price_reference_id else None
        if ref:
            month = (ref.reference_month or "").strip()
            dto.reference_label = " — ".join(x for x in [
                f"FIPE {month}" if month else "FIPE", ref.fipe_model_label or f"{ref.brand} {ref.model}"
            ] if x)
        return dto

    def admin(self, item: Item) -> ItemAdminOut:
        base = self.card(item).model_dump()
        return ItemAdminOut(
            **base, external_id=item.external_id, official_url=item.official_url,
            extraction_status=item.extraction_status, extraction_attempts=item.extraction_attempts,
            extraction_version=item.extraction_version, extraction_error=item.extraction_error,
            extraction_model=item.extraction_model, status_hint=item.status_hint, misses=item.misses,
            first_seen_at=item.first_seen_at, created_at=item.created_at, updated_at=item.updated_at,
            description=item.description, attributes=item.attributes or {}, images=item.images or [],
        )

    async def auction(self, auction: Auction, items_count: int | None = None) -> AuctionOut:
        src = self.sources.get(auction.source_id)
        if items_count is None:
            from sqlalchemy import func
            items_count = await self.db.scalar(select(func.count(Item.id)).where(Item.auction_id == auction.id)) or 0
        return AuctionOut(
            id=auction.id, source_id=auction.source_id, source_name=src.name if src else None,
            external_id=auction.external_id, title=auction.title, auctioneer_name=auction.auctioneer_name,
            auctioneer_registration=auction.auctioneer_registration, committer_name=auction.committer_name,
            modality=auction.modality, auction_type=auction.auction_type, official_url=auction.official_url,
            status=auction.status, starts_at=auction.starts_at, ends_at=auction.ends_at,
            sessions=[AuctionSessionOut.model_validate(s) for s in (auction.sessions or [])], items_count=items_count,
        )
