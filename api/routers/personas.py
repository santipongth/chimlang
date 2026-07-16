"""Persona endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import get_principal, require
from core.config import get_settings
from governance.rbac import Permission, Principal
from simulation.persona import PersonaFactory

router = APIRouter(prefix="/personas", tags=["personas"])


class PackBody(BaseModel):
    label: str
    segments: list[dict]
    prompt: str = ""


class PackGenerateBody(BaseModel):
    label: str
    prompt: str


class TryAskBody(BaseModel):
    segment: dict
    question: str


@router.get("/pool.json")
def personas_pool_json(
    pack_id: int | None = Query(None),
    principal: Principal = Depends(get_principal),
) -> dict:
    settings = get_settings()
    if pack_id is not None:
        from simulation.persona_packs import PackStore

        try:
            pack = PackStore(settings.postgres_url).get(pack_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
        segments, source = pack.segments, f"pack:{pack.label}"
    else:
        segments, source = PersonaFactory().segments, "census"
    from simulation.persona_packs import MAX_SEGMENTS, MIN_SEGMENTS

    return {
        "source": source,
        "limits": {"min_segments": MIN_SEGMENTS, "max_segments": MAX_SEGMENTS},
        "segments": [
            {
                "id": segment.get("id", ""),
                "name": segment.get("name", ""),
                "share": segment.get("share", 0),
                "voice_activity": segment.get("voice_activity", 0.5),
                "cultural_priors": segment.get("cultural_priors", {}),
                "channel_mix": segment.get("channel_mix", {}),
                "traits": segment.get("traits", []),
            }
            for segment in segments
        ],
    }


@router.get("/packs.json")
def personas_packs_json(principal: Principal = Depends(get_principal)) -> dict:
    from simulation.persona_packs import PackStore

    try:
        packs = PackStore(get_settings().postgres_url).list_packs()
        return {"packs": [pack.__dict__ for pack in packs]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc


@router.post("/packs")
def personas_pack_create(body: PackBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_packs import PackStore, PackValidationError

    try:
        pack_id = PackStore(get_settings().postgres_url).create(
            label=body.label.strip(),
            segments=body.segments,
            prompt=body.prompt,
            created_by=principal.user_id,
        )
    except PackValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"id": pack_id}


@router.put("/packs/{pack_id}")
def personas_pack_update(
    pack_id: int, body: PackBody, principal: Principal = Depends(get_principal)
) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_packs import PackStore, PackValidationError

    try:
        PackStore(get_settings().postgres_url).update(
            pack_id=pack_id,
            label=body.label.strip(),
            segments=body.segments,
            prompt=body.prompt,
        )
    except PackValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"id": pack_id}


@router.post("/packs/generate")
def personas_pack_generate(
    body: PackGenerateBody, principal: Principal = Depends(get_principal)
) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_ai import generate_pack_from_prompt
    from simulation.persona_packs import PackValidationError

    try:
        segments = generate_pack_from_prompt(body.prompt.strip(), label=body.label.strip())
    except PackValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"LLM ไม่พร้อมหรือ generate ไม่สำเร็จ: {exc}"
        ) from exc
    return {"label": body.label, "prompt": body.prompt, "segments": segments}


@router.post("/try-ask")
def personas_try_ask(body: TryAskBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_ai import try_ask

    if len(body.question.strip()) < 4:
        raise HTTPException(status_code=422, detail="คำถามสั้นเกินไป")
    try:
        answer = try_ask(body.segment, body.question.strip())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM ไม่พร้อม: {exc}") from exc
    return {"answer": answer, "segment": body.segment.get("name", "")}


@router.delete("/packs/{pack_id}")
def personas_pack_delete(pack_id: int, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_packs import PackStore

    try:
        PackStore(get_settings().postgres_url).delete(pack_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"ok": True}
