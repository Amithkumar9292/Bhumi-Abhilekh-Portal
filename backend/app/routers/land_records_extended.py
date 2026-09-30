"""
Extended Land Records Router — Adds mutations, registrations, owners,
plots, survey details, verification actions to land record CRUD.

New endpoints:
  GET  /land-records/{id}/full              — full detail with all related data
  GET  /land-records/{id}/mutations         — mutation history
  POST /land-records/{id}/mutations         — add mutation
  GET  /land-records/{id}/registrations     — registration records
  POST /land-records/{id}/registrations     — add registration
  GET  /land-records/{id}/owners            — owner list
  POST /land-records/{id}/owners            — add owner
  GET  /land-records/{id}/plots             — plot list
  POST /land-records/{id}/plots             — add plot
  GET  /land-records/{id}/survey            — survey detail
  PUT  /land-records/{id}/survey            — set survey detail
  GET  /land-records/{id}/verification-history — full action history
  POST /land-records/{id}/submit-review     — officer submits for review
  GET  /land-records/search                 — full-text search
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func

from app.dependencies import CurrentUser, DBSession, OfficerUser
from app.models.extended import (
    Mutation, MutationType, MutationStatus,
    Registration, RegistrationType,
    Owner, LandRecordOwner, OwnerType,
    Plot, PlotStatus,
    SurveyDetail, SurveyType,
    VerificationAction, VerificationActionType,
)
from app.models.land_record import LandRecord, RecordStatus
from app.services.audit_service import log_event

router = APIRouter(prefix="/land-records", tags=["Land Records — Extended"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class MutationCreate(BaseModel):
    mutation_number: str = Field(..., min_length=2)
    mutation_type: str
    transferor_name: Optional[str] = None
    transferee_name: Optional[str] = None
    application_date: Optional[str] = None
    approval_date: Optional[str] = None
    effective_date: Optional[str] = None
    consideration_amount: Optional[float] = Field(None, ge=0)
    stamp_duty_paid: Optional[float] = Field(None, ge=0)
    tehsildar_name: Optional[str] = None
    remarks: Optional[str] = None


class RegistrationCreate(BaseModel):
    registration_type: str
    deed_number: Optional[str] = None
    book_number: Optional[str] = None
    registration_date: Optional[str] = None
    execution_date: Optional[str] = None
    sub_registrar_office: Optional[str] = None
    sub_registrar_name: Optional[str] = None
    market_value: Optional[float] = Field(None, ge=0)
    consideration_value: Optional[float] = Field(None, ge=0)
    stamp_duty: Optional[float] = Field(None, ge=0)
    registration_fee: Optional[float] = Field(None, ge=0)
    remarks: Optional[str] = None


class OwnerCreate(BaseModel):
    owner_type: str = "INDIVIDUAL"
    full_name: str = Field(..., min_length=2)
    father_spouse_name: Optional[str] = None
    gender: Optional[str] = None
    aadhaar_last4: Optional[str] = Field(None, min_length=4, max_length=4)
    address: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    ownership_share_pct: Optional[float] = Field(None, ge=0, le=100)
    is_primary: bool = True


class PlotCreate(BaseModel):
    plot_number: str = Field(..., min_length=1)
    area_hectares: float = Field(..., gt=0)
    soil_type: Optional[str] = None
    irrigation_source: Optional[str] = None
    crop_type: Optional[str] = None
    revenue_circle: Optional[str] = None
    remarks: Optional[str] = None


class SurveyDetailCreate(BaseModel):
    survey_type: str = "CADASTRAL"
    surveyor_name: Optional[str] = None
    survey_date: Optional[str] = None
    settlement_year: Optional[str] = None
    revision_year: Optional[str] = None
    toposheet_number: Optional[str] = None
    field_book_number: Optional[str] = None
    boundary_marks: Optional[str] = None
    remarks: Optional[str] = None


# ── Full-text search (must be before /{record_id} routes) ─────────────────────

@router.get("/search")
async def full_text_search(
    q: str = Query(..., min_length=2),
    page: int = 1,
    page_size: int = 20,
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Full-text search across khasra, owner_name, village, district."""
    search_q = select(LandRecord).where(
        or_(
            LandRecord.khasra_number.ilike(f"%{q}%"),
            LandRecord.owner_name.ilike(f"%{q}%"),
            LandRecord.village.ilike(f"%{q}%"),
            LandRecord.district.ilike(f"%{q}%"),
            LandRecord.state.ilike(f"%{q}%"),
            LandRecord.survey_number.ilike(f"%{q}%"),
            LandRecord.khatauni_number.ilike(f"%{q}%"),
        )
    )
    total = (await db.execute(select(func.count()).select_from(search_q.subquery()))).scalar() or 0
    result = await db.execute(search_q.offset((page - 1) * page_size).limit(page_size))
    records = result.scalars().all()
    return {
        "query": q,
        "total": total,
        "page": page,
        "items": [
            {"id": str(r.id), "khasra_number": r.khasra_number, "owner_name": r.owner_name,
             "district": r.district, "village": r.village, "area_hectares": r.area_hectares,
             "land_use_type": r.land_use_type.value, "status": r.status.value}
            for r in records
        ],
    }


# ── Full detail endpoint ──────────────────────────────────────────────────────

@router.get("/{record_id}/full")
async def get_land_record_full(
    record_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Return a land record with all related data (mutations, owners, plots, survey, etc.)."""
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")

    # Parallel queries for related data
    mutations_q   = select(Mutation).where(Mutation.land_record_id == record_id).order_by(Mutation.created_at.desc())
    registrations_q = select(Registration).where(Registration.land_record_id == record_id)
    owners_q      = select(LandRecordOwner, Owner).join(Owner, Owner.id == LandRecordOwner.owner_id).where(LandRecordOwner.land_record_id == record_id)
    plots_q       = select(Plot).where(Plot.land_record_id == record_id)
    survey_q      = select(SurveyDetail).where(SurveyDetail.land_record_id == record_id)
    actions_q     = select(VerificationAction).where(VerificationAction.land_record_id == record_id).order_by(VerificationAction.created_at.desc()).limit(10)

    mutations    = (await db.execute(mutations_q)).scalars().all()
    registrations = (await db.execute(registrations_q)).scalars().all()
    owner_rows   = (await db.execute(owners_q)).all()
    plots        = (await db.execute(plots_q)).scalars().all()
    survey       = (await db.execute(survey_q)).scalar_one_or_none()
    actions      = (await db.execute(actions_q)).scalars().all()

    def _mutation(m: Mutation) -> dict:
        return {
            "id": str(m.id), "mutation_number": m.mutation_number,
            "mutation_type": m.mutation_type.value, "status": m.status.value,
            "transferor_name": m.transferor_name, "transferee_name": m.transferee_name,
            "application_date": m.application_date, "approval_date": m.approval_date,
            "consideration_amount": float(m.consideration_amount) if m.consideration_amount else None,
            "stamp_duty_paid": float(m.stamp_duty_paid) if m.stamp_duty_paid else None,
            "tehsildar_name": m.tehsildar_name, "remarks": m.remarks,
            "created_at": m.created_at.isoformat(),
        }

    def _registration(r: Registration) -> dict:
        return {
            "id": str(r.id), "registration_type": r.registration_type.value,
            "deed_number": r.deed_number, "registration_date": r.registration_date,
            "sub_registrar_office": r.sub_registrar_office,
            "market_value": float(r.market_value) if r.market_value else None,
            "consideration_value": float(r.consideration_value) if r.consideration_value else None,
            "stamp_duty": float(r.stamp_duty) if r.stamp_duty else None,
            "created_at": r.created_at.isoformat(),
        }

    def _owner(lro: LandRecordOwner, o: Owner) -> dict:
        return {
            "id": str(o.id), "full_name": o.full_name,
            "owner_type": o.owner_type.value,
            "father_spouse_name": o.father_spouse_name,
            "address": o.address, "district": o.district, "state": o.state,
            "ownership_share_pct": lro.ownership_share_pct,
            "is_primary": lro.is_primary,
        }

    def _plot(p: Plot) -> dict:
        return {
            "id": str(p.id), "plot_number": p.plot_number,
            "area_hectares": float(p.area_hectares),
            "soil_type": p.soil_type, "irrigation_source": p.irrigation_source,
            "crop_type": p.crop_type, "revenue_circle": p.revenue_circle,
            "status": p.status.value, "remarks": p.remarks,
        }

    return {
        "id": str(record.id),
        "khasra_number": record.khasra_number,
        "khatauni_number": record.khatauni_number,
        "survey_number": record.survey_number,
        "state": record.state, "district": record.district,
        "tehsil": record.tehsil, "village": record.village, "pin_code": record.pin_code,
        "area_hectares": record.area_hectares,
        "land_use_type": record.land_use_type.value,
        "owner_name": record.owner_name,
        "status": record.status.value,
        "rejection_reason": record.rejection_reason,
        "geometry": record.geometry,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        # Extended data
        "owners": [_owner(lro, o) for lro, o in owner_rows],
        "plots": [_plot(p) for p in plots],
        "mutations": [_mutation(m) for m in mutations],
        "registrations": [_registration(r) for r in registrations],
        "survey_detail": {
            "survey_type": survey.survey_type.value,
            "surveyor_name": survey.surveyor_name,
            "survey_date": survey.survey_date,
            "settlement_year": survey.settlement_year,
            "toposheet_number": survey.toposheet_number,
        } if survey else None,
        "verification_history": [
            {
                "id": str(a.id), "action_type": a.action_type.value,
                "actor_role": a.actor_role, "notes": a.notes,
                "previous_status": a.previous_status, "new_status": a.new_status,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
    }


# ── Mutations ─────────────────────────────────────────────────────────────────

@router.get("/{record_id}/mutations")
async def list_mutations(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(Mutation).where(Mutation.land_record_id == record_id).order_by(Mutation.created_at.desc())
    )
    mutations = result.scalars().all()
    return {"items": [
        {"id": str(m.id), "mutation_number": m.mutation_number, "mutation_type": m.mutation_type.value,
         "status": m.status.value, "transferee_name": m.transferee_name,
         "consideration_amount": float(m.consideration_amount) if m.consideration_amount else None,
         "effective_date": m.effective_date, "created_at": m.created_at.isoformat()}
        for m in mutations
    ], "total": len(mutations)}


@router.post("/{record_id}/mutations", status_code=201)
async def add_mutation(
    record_id: uuid.UUID, body: MutationCreate,
    db: DBSession, current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    try:
        m_type = MutationType(body.mutation_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid mutation_type: {body.mutation_type}") from e

    mut = Mutation(
        land_record_id=record_id, mutation_type=m_type,
        status=MutationStatus.PENDING, created_by=current_user.id,
        **{k: v for k, v in body.model_dump().items() if k != "mutation_type"},
    )
    db.add(mut)
    await db.flush()
    await log_event("ADD_MUTATION", current_user.id, "Mutation", mut.id,
                    {"land_record_id": str(record_id), "mutation_number": body.mutation_number})
    return {"id": str(mut.id), "mutation_number": mut.mutation_number}


# ── Registrations ─────────────────────────────────────────────────────────────

@router.get("/{record_id}/registrations")
async def list_registrations(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(select(Registration).where(Registration.land_record_id == record_id))
    regs = result.scalars().all()
    return {"items": [
        {"id": str(r.id), "registration_type": r.registration_type.value,
         "deed_number": r.deed_number, "registration_date": r.registration_date,
         "sub_registrar_office": r.sub_registrar_office,
         "market_value": float(r.market_value) if r.market_value else None}
        for r in regs
    ], "total": len(regs)}


@router.post("/{record_id}/registrations", status_code=201)
async def add_registration(
    record_id: uuid.UUID, body: RegistrationCreate,
    db: DBSession, current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    try:
        r_type = RegistrationType(body.registration_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid registration_type: {body.registration_type}") from e
    reg = Registration(land_record_id=record_id, registration_type=r_type,
                       **{k: v for k, v in body.model_dump().items() if k != "registration_type"})
    db.add(reg)
    await db.flush()
    await log_event("ADD_REGISTRATION", current_user.id, "Registration", reg.id,
                    {"land_record_id": str(record_id)})
    return {"id": str(reg.id), "deed_number": reg.deed_number}


# ── Owners ────────────────────────────────────────────────────────────────────

@router.get("/{record_id}/owners")
async def list_owners(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(LandRecordOwner, Owner).join(Owner, Owner.id == LandRecordOwner.owner_id)
        .where(LandRecordOwner.land_record_id == record_id)
    )
    return {"items": [
        {"id": str(o.id), "full_name": o.full_name, "owner_type": o.owner_type.value,
         "ownership_share_pct": lro.ownership_share_pct, "is_primary": lro.is_primary,
         "address": o.address}
        for lro, o in result.all()
    ]}


@router.post("/{record_id}/owners", status_code=201)
async def add_owner(
    record_id: uuid.UUID, body: OwnerCreate,
    db: DBSession, current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    try:
        o_type = OwnerType(body.owner_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid owner_type: {body.owner_type}") from e

    owner = Owner(id=uuid.uuid4(), owner_type=o_type,
                  full_name=body.full_name, father_spouse_name=body.father_spouse_name,
                  gender=body.gender, aadhaar_last4=body.aadhaar_last4,
                  address=body.address, district=body.district,
                  state=body.state, pin_code=body.pin_code)
    db.add(owner)
    await db.flush()

    lro = LandRecordOwner(id=uuid.uuid4(), land_record_id=record_id, owner_id=owner.id,
                          ownership_share_pct=body.ownership_share_pct, is_primary=body.is_primary)
    db.add(lro)
    await db.flush()
    return {"owner_id": str(owner.id), "land_record_owner_id": str(lro.id)}


# ── Plots ─────────────────────────────────────────────────────────────────────

@router.get("/{record_id}/plots")
async def list_plots(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(select(Plot).where(Plot.land_record_id == record_id))
    plots = result.scalars().all()
    return {"items": [
        {"id": str(p.id), "plot_number": p.plot_number, "area_hectares": float(p.area_hectares),
         "soil_type": p.soil_type, "crop_type": p.crop_type, "status": p.status.value}
        for p in plots
    ], "total": len(plots)}


@router.post("/{record_id}/plots", status_code=201)
async def add_plot(
    record_id: uuid.UUID, body: PlotCreate,
    db: DBSession, current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    plot = Plot(id=uuid.uuid4(), land_record_id=record_id, status=PlotStatus.ACTIVE, **body.model_dump())
    db.add(plot)
    await db.flush()
    return {"id": str(plot.id), "plot_number": plot.plot_number}


# ── Survey Detail ─────────────────────────────────────────────────────────────

@router.get("/{record_id}/survey")
async def get_survey(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    survey = (await db.execute(
        select(SurveyDetail).where(SurveyDetail.land_record_id == record_id)
    )).scalar_one_or_none()
    if not survey:
        raise HTTPException(status_code=404, detail="No survey detail found")
    return {
        "id": str(survey.id), "survey_type": survey.survey_type.value,
        "surveyor_name": survey.surveyor_name, "survey_date": survey.survey_date,
        "settlement_year": survey.settlement_year, "revision_year": survey.revision_year,
        "toposheet_number": survey.toposheet_number, "field_book_number": survey.field_book_number,
        "boundary_marks": survey.boundary_marks, "remarks": survey.remarks,
    }


@router.put("/{record_id}/survey", status_code=200)
async def upsert_survey(
    record_id: uuid.UUID, body: SurveyDetailCreate,
    db: DBSession, current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    existing = (await db.execute(
        select(SurveyDetail).where(SurveyDetail.land_record_id == record_id)
    )).scalar_one_or_none()

    s_type = SurveyType(body.survey_type) if body.survey_type in SurveyType._value2member_map_ else SurveyType.CADASTRAL
    if existing:
        for k, v in body.model_dump(exclude_none=True).items():
            if k != "survey_type":
                setattr(existing, k, v)
        existing.survey_type = s_type
        sid = str(existing.id)
    else:
        survey = SurveyDetail(id=uuid.uuid4(), land_record_id=record_id, survey_type=s_type,
                              **{k: v for k, v in body.model_dump().items() if k != "survey_type"})
        db.add(survey)
        await db.flush()
        sid = str(survey.id)
    return {"id": sid, "survey_type": s_type.value}


# ── Verification history ───────────────────────────────────────────────────────

@router.get("/{record_id}/verification-history")
async def get_verification_history(record_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(VerificationAction).where(VerificationAction.land_record_id == record_id)
        .order_by(VerificationAction.created_at.desc())
    )
    actions = result.scalars().all()
    return {"items": [
        {"id": str(a.id), "action_type": a.action_type.value, "actor_role": a.actor_role,
         "notes": a.notes, "previous_status": a.previous_status, "new_status": a.new_status,
         "created_at": a.created_at.isoformat()}
        for a in actions
    ], "total": len(actions)}


# ── Submit for review ─────────────────────────────────────────────────────────

@router.post("/{record_id}/submit-review", status_code=200)
async def submit_for_review(
    record_id: uuid.UUID,
    notes: Optional[str] = None,
    *,
    db: DBSession,
    current_user: OfficerUser,
) -> dict:
    """OFFICER submits a land record for verification."""
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")
    if record.status != RecordStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Record status is '{record.status}' — only PENDING records can be submitted")

    prev_status = record.status.value
    record.status = RecordStatus.UNDER_REVIEW
    await db.flush()

    action = VerificationAction(
        id=uuid.uuid4(),
        land_record_id=record_id,
        action_type=VerificationActionType.SUBMITTED_FOR_REVIEW,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        notes=notes,
        previous_status=prev_status,
        new_status=RecordStatus.UNDER_REVIEW.value,
    )
    db.add(action)
    await db.flush()
    await log_event("SUBMIT_REVIEW", current_user.id, "LandRecord", record_id, {})
    return {"record_id": str(record_id), "new_status": "UNDER_REVIEW"}



