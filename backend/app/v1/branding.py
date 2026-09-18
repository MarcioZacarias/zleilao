"""Logo/favicon armazenados no banco (padrao Promo)."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.timeutil import now_brt
from app.models import BrandingAsset

ALLOWED_KEYS = {"logo_dark", "logo_light", "favicon"}
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_MIMETYPES = {"image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp", "image/x-icon", "image/vnd.microsoft.icon"}

public_router = APIRouter()
admin_router = APIRouter()


@public_router.get("/branding/{key}")
async def get_asset(key: str, db: AsyncSession = Depends(get_db)):
    if key not in ALLOWED_KEYS:
        raise HTTPException(404, "Chave inválida")
    asset = await db.scalar(select(BrandingAsset).where(BrandingAsset.key == key))
    if not asset:
        raise HTTPException(404, "Sem imagem para esta chave")
    return Response(content=asset.data, media_type=asset.mimetype,
                    headers={"Cache-Control": "public, max-age=300", "ETag": f'"{asset.updated_at.timestamp()}"'})


@admin_router.post("/branding/upload")
async def upload(key: str = Form(...), file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Chave inválida. Permitidas: {sorted(ALLOWED_KEYS)}")
    mimetype = (file.content_type or "").lower()
    if mimetype not in ALLOWED_MIMETYPES:
        raise HTTPException(400, f"Tipo '{mimetype}' não permitido (PNG, JPEG, SVG, WEBP, ICO)")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Arquivo vazio")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Arquivo maior que 2 MB")
    asset = await db.scalar(select(BrandingAsset).where(BrandingAsset.key == key))
    if asset:
        asset.mimetype, asset.data, asset.updated_at = mimetype, data, now_brt()
    else:
        asset = BrandingAsset(key=key, mimetype=mimetype, data=data)
        db.add(asset)
    await db.commit()
    return {"key": key, "mimetype": mimetype, "size": len(data), "url": f"/api/branding/{key}?v={int(asset.updated_at.timestamp())}"}


@admin_router.delete("/branding/{key}")
async def delete_asset(key: str, db: AsyncSession = Depends(get_db)):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, "Chave inválida")
    asset = await db.scalar(select(BrandingAsset).where(BrandingAsset.key == key))
    if not asset:
        return {"key": key, "deleted": False}
    await db.delete(asset)
    await db.commit()
    return {"key": key, "deleted": True}
