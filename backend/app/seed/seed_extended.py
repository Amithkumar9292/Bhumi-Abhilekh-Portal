"""
Extended seed data: seeds all new tables with rich synthetic demo data.
Extends the base seed to add owners, plots, mutations, registrations,
survey details, GIS coordinates, validation rules, notifications.

Run standalone:
  cd backend && python -m app.seed.seed_extended
Or call seed_extended(db) from the base seed.
"""
from __future__ import annotations

import asyncio
import io
import random
import sys
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import AsyncSessionLocal, init_db
from app.models import (
    LandRecord, RecordStatus, User, RoleEnum,
    Owner, OwnerType, LandRecordOwner,
    Plot, PlotStatus,
    SurveyDetail, SurveyType,
    Mutation, MutationType, MutationStatus,
    Registration, RegistrationType,
    ValidationRule, GISCoordinate,
    Notification, NotificationType,
    VerificationAction, VerificationActionType,
)
from app.services.gis_service import generate_gis_data
from sqlalchemy import select

SOIL_TYPES = ["Alluvial", "Black Cotton", "Red Laterite", "Desert Sandy", "Mountain"]
IRRIGATION_SOURCES = ["Canal", "Tubewell", "Rain-fed", "River", "Drip"]
CROP_TYPES = ["Wheat", "Rice", "Sugarcane", "Cotton", "Maize", "Mustard", "Soybean", "Pulses"]
TEHSILDARS = [
    "Shri R.K. Shukla", "Smt. Priya Verma", "Shri M.L. Tiwari",
    "Smt. Anita Singh", "Shri D.K. Gupta",
]
DEED_TYPES = list(RegistrationType)
MUT_TYPES = list(MutationType)

SURVEY_NOTES = [
    "Boundary confirmed with adjacent plot owners.",
    "Revised as per Settlement Officer order dated 2022.",
    "Survey pegs installed at all four corners.",
    "Topo sheet reference: 54F/7. Boundary marks: cement pillars.",
]

DEFAULT_RULES = [
    ("VR001", "Required Fields Completeness",  "All mandatory fields must be present and non-empty",               "ERROR",   "COMPLETENESS",  True,  None),
    ("VR002", "Area Range Sanity",             "Plot area must be between 0.001 ha and 5000 ha",                   "ERROR",   "CONSISTENCY",   True,  {"min_area": 0.001, "max_area": 5000.0}),
    ("VR003", "Khasra Number Format",          "Khasra number must be alphanumeric [A-Z0-9/-]",                    "WARNING", "FORMAT",        False, {"pattern": "^[A-Z0-9][A-Z0-9\\-/]{1,30}$"}),
    ("VR004", "PIN Code Format",               "PIN code must be exactly 6 digits if provided",                    "WARNING", "FORMAT",        False, None),
    ("VR005", "Land Use vs Area Consistency",  "Industrial/Forest land use area sanity",                           "WARNING", "CONSISTENCY",   False, {"min_industrial_ha": 0.1, "min_forest_ha": 1.0}),
    ("VR006", "Owner Name Quality",            "Owner name must be reasonable length and not contain numbers",      "ERROR",   "COMPLETENESS",  False, {"min_name_len": 3, "max_name_len": 200}),
    ("VR007", "Location Field Distinctness",   "State/District/Tehsil/Village should all be different values",     "WARNING", "CONSISTENCY",   False, None),
    ("VR008", "Duplicate Khasra Detection",    "Khasra number + district combination must be unique",              "ERROR",   "DUPLICATE",     True,  None),
    ("VR009", "Area Cross-Record Consistency", "Area deviation >20% vs existing record with same khasra",          "WARNING", "CROSS_RECORD",  False, {"area_tolerance_pct": 20.0}),
    ("VR010", "Village-Tehsil Cross Check",    "Village must consistently map to same tehsil across all records",  "WARNING", "CROSS_RECORD",  False, None),
]


async def seed_extended(db: AsyncSession, records: list[LandRecord], users: list[User]) -> None:
    print("🌱 Seeding extended platform data...")

    officer = next((u for u in users if u.role == RoleEnum.OFFICER), users[0])
    admin   = next((u for u in users if u.role == RoleEnum.ADMIN), users[0])
    verifier = next((u for u in users if u.role == RoleEnum.VERIFIER), users[0])

    # ── Validation Rules ──────────────────────────────────────────────────────
    for code, name, desc, sev, cat, blocking, config in DEFAULT_RULES:
        existing = (await db.execute(
            select(ValidationRule).where(ValidationRule.rule_code == code)
        )).scalar_one_or_none()
        if not existing:
            rule = ValidationRule(
                id=uuid.uuid4(), rule_code=code, rule_name=name, description=desc,
                severity=sev, category=cat, is_active=True, is_blocking=blocking,
                applies_to="LAND_RECORD", config=config, created_by=admin.id,
            )
            db.add(rule)
    await db.flush()
    print(f"  ✅ Seeded {len(DEFAULT_RULES)} validation rules")

    # ── Owners + LandRecordOwners ─────────────────────────────────────────────
    owner_count = 0
    for record in records:
        owner = Owner(
            id=uuid.uuid4(),
            owner_type=random.choice([OwnerType.INDIVIDUAL, OwnerType.JOINT]),
            full_name=record.owner_name,
            father_spouse_name=record.father_name,
            gender=random.choice(["Male", "Female"]),
            aadhaar_last4=record.aadhaar_last4,
            address=record.address,
            district=record.district,
            state=record.state,
        )
        db.add(owner)
        await db.flush()

        lro = LandRecordOwner(
            id=uuid.uuid4(),
            land_record_id=record.id,
            owner_id=owner.id,
            ownership_share_pct=100.0,
            is_primary=True,
        )
        db.add(lro)
        owner_count += 1

        # 20% chance of a joint owner
        if random.random() < 0.2:
            co_owner = Owner(
                id=uuid.uuid4(), owner_type=OwnerType.INDIVIDUAL,
                full_name=f"Co-owner of {record.khasra_number}",
                gender=random.choice(["Male", "Female"]),
                district=record.district, state=record.state,
            )
            db.add(co_owner)
            await db.flush()
            db.add(LandRecordOwner(
                id=uuid.uuid4(), land_record_id=record.id, owner_id=co_owner.id,
                ownership_share_pct=50.0, is_primary=False,
            ))
            owner_count += 1

    await db.flush()
    print(f"  ✅ Created {owner_count} owner records")

    # ── Plots ─────────────────────────────────────────────────────────────────
    plot_count = 0
    for record in records:
        n_plots = random.choice([1, 1, 1, 2, 3])  # mostly single plot
        remaining = float(record.area_hectares)
        for j in range(n_plots):
            area = round(remaining / (n_plots - j) * random.uniform(0.8, 1.2), 4) if j < n_plots - 1 else round(remaining, 4)
            area = max(0.001, area)
            remaining = max(0.001, remaining - area)
            plot = Plot(
                id=uuid.uuid4(), land_record_id=record.id,
                plot_number=f"{record.khasra_number}/{j+1}",
                area_hectares=area,
                area_sq_meters=round(area * 10000, 2),
                soil_type=random.choice(SOIL_TYPES),
                irrigation_source=random.choice(IRRIGATION_SOURCES),
                crop_type=random.choice(CROP_TYPES),
                revenue_circle=record.tehsil,
                status=PlotStatus.ACTIVE,
            )
            db.add(plot)
            plot_count += 1
    await db.flush()
    print(f"  ✅ Created {plot_count} plot records")

    # ── Survey Details ────────────────────────────────────────────────────────
    survey_count = 0
    for record in records[::2]:  # every other record has survey detail
        survey = SurveyDetail(
            id=uuid.uuid4(), land_record_id=record.id,
            survey_type=random.choice(list(SurveyType)),
            surveyor_name=f"Surveyor {random.randint(100, 999)}",
            survey_date=f"20{random.randint(18, 24)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            settlement_year=str(random.randint(1985, 2010)),
            revision_year=str(random.randint(2015, 2024)),
            toposheet_number=f"{random.randint(50,60)}{chr(random.randint(65, 75))}/{random.randint(1, 16)}",
            field_book_number=f"FB-{random.randint(1000, 9999)}",
            remarks=random.choice(SURVEY_NOTES),
        )
        db.add(survey)
        survey_count += 1
    await db.flush()
    print(f"  ✅ Created {survey_count} survey detail records")

    # ── Registrations ─────────────────────────────────────────────────────────
    reg_count = 0
    for record in records[:30]:
        reg = Registration(
            id=uuid.uuid4(), land_record_id=record.id,
            registration_type=random.choice(DEED_TYPES),
            deed_number=f"DEED-{random.randint(100000, 999999)}",
            book_number=str(random.randint(1, 50)),
            volume_number=str(random.randint(1, 5)),
            registration_date=f"20{random.randint(18, 24)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            execution_date=f"20{random.randint(18, 24)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            sub_registrar_office=f"Sub-Registrar Office, {record.district}",
            sub_registrar_name=random.choice(["Shri A.K. Dubey", "Smt. R. Singh", "Shri P.K. Sharma"]),
            district=record.district, state=record.state,
            market_value=round(random.uniform(200000, 5000000), 2),
            consideration_value=round(random.uniform(150000, 4500000), 2),
            stamp_duty=round(random.uniform(10000, 200000), 2),
            registration_fee=round(random.uniform(2000, 20000), 2),
        )
        db.add(reg)
        reg_count += 1
    await db.flush()
    print(f"  ✅ Created {reg_count} registration records")

    # ── Mutations ─────────────────────────────────────────────────────────────
    mut_count = 0
    for record in records[:25]:
        mut = Mutation(
            id=uuid.uuid4(), land_record_id=record.id,
            mutation_number=f"MUT-{datetime.now().year}-{random.randint(1000, 9999)}",
            mutation_type=random.choice(MUT_TYPES),
            status=random.choice(list(MutationStatus)),
            transferor_name=record.owner_name,
            transferee_name=random.choice([
                "Ramesh Chandra Yadav", "Smt. Geeta Devi",
                "Arvind Kumar Patel", "Shri Vijay Singh",
            ]),
            application_date=f"20{random.randint(20,24)}-{random.randint(1,12):02d}-01",
            approval_date=f"20{random.randint(20,24)}-{random.randint(1,12):02d}-15",
            consideration_amount=round(random.uniform(100000, 3000000), 2),
            stamp_duty_paid=round(random.uniform(5000, 100000), 2),
            tehsildar_name=random.choice(TEHSILDARS),
            created_by=officer.id,
        )
        db.add(mut)
        mut_count += 1
    await db.flush()
    print(f"  ✅ Created {mut_count} mutation records")

    # ── GIS Coordinates ───────────────────────────────────────────────────────
    gis_count = 0
    for record in records:
        gis_data = generate_gis_data(
            str(record.id), record.state, record.district,
            record.khasra_number, record.area_hectares,
        )
        coord = GISCoordinate(
            id=uuid.uuid4(),
            **gis_data,
        )
        db.add(coord)
        gis_count += 1
    await db.flush()
    print(f"  ✅ Generated {gis_count} GIS coordinate records")

    # ── Verification Actions ──────────────────────────────────────────────────
    action_count = 0
    for record in records:
        if record.status == RecordStatus.UNDER_REVIEW:
            db.add(VerificationAction(
                id=uuid.uuid4(), land_record_id=record.id,
                action_type=VerificationActionType.SUBMITTED_FOR_REVIEW,
                actor_id=officer.id, actor_role="OFFICER",
                notes="Submitted for verification as all documents are in order.",
                previous_status="PENDING", new_status="UNDER_REVIEW",
            ))
            action_count += 1
        elif record.status == RecordStatus.VERIFIED:
            db.add(VerificationAction(
                id=uuid.uuid4(), land_record_id=record.id,
                action_type=VerificationActionType.SUBMITTED_FOR_REVIEW,
                actor_id=officer.id, actor_role="OFFICER",
                previous_status="PENDING", new_status="UNDER_REVIEW",
            ))
            db.add(VerificationAction(
                id=uuid.uuid4(), land_record_id=record.id,
                action_type=VerificationActionType.APPROVED,
                actor_id=verifier.id, actor_role="VERIFIER",
                notes="All fields validated. Documents verified. Record approved.",
                previous_status="UNDER_REVIEW", new_status="VERIFIED",
            ))
            action_count += 2
        elif record.status == RecordStatus.REJECTED:
            db.add(VerificationAction(
                id=uuid.uuid4(), land_record_id=record.id,
                action_type=VerificationActionType.REJECTED,
                actor_id=verifier.id, actor_role="VERIFIER",
                notes="Boundary discrepancy found. Survey documents do not match.",
                previous_status="UNDER_REVIEW", new_status="REJECTED",
            ))
            action_count += 1
    await db.flush()
    print(f"  ✅ Created {action_count} verification action records")

    # ── Notifications ─────────────────────────────────────────────────────────
    notif_count = 0
    for user in users:
        db.add(Notification(
            id=uuid.uuid4(), recipient_id=user.id,
            notification_type=NotificationType.SYSTEM_NOTICE,
            title="Welcome to Bhumi Abhilekh Portal",
            body="Your account has been activated. This system contains synthetic demo data only.",
            is_read=False,
        ))
        notif_count += 1

    for record in records[:10]:
        db.add(Notification(
            id=uuid.uuid4(), recipient_id=officer.id,
            notification_type=NotificationType.RECORD_VERIFIED,
            title=f"Record {record.khasra_number} Verified",
            body=f"Land record {record.khasra_number} in {record.district} has been verified.",
            resource_type="LandRecord", resource_id=str(record.id),
        ))
        notif_count += 1

    await db.flush()
    print(f"  ✅ Created {notif_count} notification records")

    await db.commit()
    print("✅ Extended seed complete!")


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        # Get existing seeded records and users
        records_result = await db.execute(select(LandRecord).limit(100))
        records = list(records_result.scalars().all())
        users_result = await db.execute(select(User))
        users = list(users_result.scalars().all())
        if not records:
            print("❌ No base records found. Run seed_data.py first.")
            return
        await seed_extended(db, records, users)


if __name__ == "__main__":
    # Windows consoles default to cp1252, which cannot encode the emoji below.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
