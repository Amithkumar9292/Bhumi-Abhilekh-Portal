"""
Demo data seeder: generates synthetic land records, users, documents.
Clearly marked as non-legally-binding demo data.
"""

import asyncio
import io
import random
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.postgres import AsyncSessionLocal, init_db
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType, RecordStatus
from app.models.user import RoleEnum, User

# ── Demo users ────────────────────────────────────────────────────────────────
DEMO_USERS = [
    {
        "username": "admin",
        "email": "admin@landrecords.demo",
        "full_name": "System Administrator",
        "password": "Admin@1234",
        "role": RoleEnum.ADMIN,
        "district_code": None,
    },
    {
        "username": "officer_rajesh",
        "email": "rajesh.kumar@landrecords.demo",
        "full_name": "Rajesh Kumar",
        "password": "Officer@1234",
        "role": RoleEnum.OFFICER,
        "district_code": "UP-LKW",
    },
    {
        "username": "verifier_priya",
        "email": "priya.sharma@landrecords.demo",
        "full_name": "Priya Sharma",
        "password": "Verifier@1234",
        "role": RoleEnum.VERIFIER,
        "district_code": "UP-LKW",
    },
    {
        "username": "viewer_anand",
        "email": "anand.mishra@landrecords.demo",
        "full_name": "Anand Mishra",
        "password": "Viewer@1234",
        "role": RoleEnum.VIEWER,
        "district_code": "UP-VNS",
    },
]

# ── Synthetic Indian place data ───────────────────────────────────────────────
DISTRICTS = [
    ("Uttar Pradesh", "Lucknow", ["Sarojini Nagar", "Chinhat", "Bakshi Ka Talab"]),
    ("Uttar Pradesh", "Varanasi", ["Kashi", "Sarnath", "Rohania"]),
    ("Madhya Pradesh", "Bhopal", ["Berasia", "Huzur", "Phanda"]),
    ("Rajasthan", "Jaipur", ["Amer", "Sanganer", "Jhotwara"]),
    ("Maharashtra", "Pune", ["Haveli", "Mulshi", "Maval"]),
    ("Bihar", "Patna", ["Phulwari", "Danapur", "Sampatchak"]),
]

OWNER_NAMES = [
    "Ram Prasad Verma", "Sita Devi Yadav", "Mohan Lal Gupta", "Sunita Kumari Singh",
    "Hari Om Tiwari", "Geeta Devi Patel", "Bhola Nath Mishra", "Pushpa Lata Chauhan",
    "Dinesh Kumar Sharma", "Radha Rani Dubey", "Suresh Chandra Pandey", "Kamla Devi Maurya",
    "Vijay Kumar Srivastava", "Lalita Devi Rai", "Manoj Kumar Tripathi",
]

LAND_USE_TYPES = list(LandUseType)
STATUSES = [
    RecordStatus.PENDING,
    RecordStatus.PENDING,
    RecordStatus.UNDER_REVIEW,
    RecordStatus.VERIFIED,
    RecordStatus.VERIFIED,
    RecordStatus.VERIFIED,
    RecordStatus.REJECTED,
]


def random_khasra() -> str:
    return f"{random.randint(100, 9999)}/{random.randint(1, 99)}"


def random_khatauni() -> str:
    return f"KH-{random.randint(10000, 99999)}"


def random_aadhaar_last4() -> str:
    return str(random.randint(1000, 9999))


def make_geometry(lat: float, lon: float, size: float = 0.002) -> dict:
    """Generate a simple square GeoJSON polygon."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat],
            [lon + size, lat],
            [lon + size, lat + size],
            [lon, lat + size],
            [lon, lat],
        ]],
    }


BASE_COORDS = {
    "Lucknow": (26.85, 80.95),
    "Varanasi": (25.30, 82.97),
    "Bhopal": (23.25, 77.40),
    "Jaipur": (26.91, 75.78),
    "Pune": (18.52, 73.85),
    "Patna": (25.59, 85.13),
}


async def seed(db: AsyncSession) -> None:
    print("🌱 Seeding demo data...")

    # ── Users ──────────────────────────────────────────────────
    user_objects: list[User] = []
    for u in DEMO_USERS:
        user = User(
            username=u["username"],
            email=u["email"],
            full_name=u["full_name"],
            hashed_password=hash_password(str(u["password"])),
            role=u["role"],
            district_code=u.get("district_code"),
        )
        db.add(user)
        user_objects.append(user)
    await db.flush()
    print(f"  ✅ Created {len(user_objects)} demo users")

    # ── Land Records ───────────────────────────────────────────
    records: list[LandRecord] = []
    officer_user = next(u for u in user_objects if u.role == RoleEnum.OFFICER)
    verifier_user = next(u for u in user_objects if u.role == RoleEnum.VERIFIER)

    for _ in range(60):
        state, district, tehsils = random.choice(DISTRICTS)
        tehsil = random.choice(tehsils)
        base_lat, base_lon = BASE_COORDS.get(district, (20.0, 78.0))
        status = random.choice(STATUSES)
        record = LandRecord(
            khasra_number=random_khasra(),
            khatauni_number=random_khatauni(),
            survey_number=f"SRV-{random.randint(1000, 9999)}",
            state=state,
            district=district,
            tehsil=tehsil,
            village=f"{tehsil} Village {random.randint(1, 10)}",
            pin_code=str(random.randint(200000, 999999)),
            area_hectares=round(random.uniform(0.1, 15.0), 4),
            land_use_type=random.choice(LAND_USE_TYPES),
            owner_name=random.choice(OWNER_NAMES),
            father_name=random.choice(OWNER_NAMES),
            address=f"Near Gram Panchayat, {tehsil}, {district}",
            aadhaar_last4=random_aadhaar_last4(),
            status=status,
            created_by=officer_user.id,
            verified_by=verifier_user.id if status == RecordStatus.VERIFIED else None,
            verified_at=datetime.now(timezone.utc) if status == RecordStatus.VERIFIED else None,
            rejection_reason="Boundary discrepancy found in survey documents" if status == RecordStatus.REJECTED else None,
            geometry=make_geometry(
                base_lat + random.uniform(-0.1, 0.1),
                base_lon + random.uniform(-0.1, 0.1),
            ),
        )
        db.add(record)
        records.append(record)
    await db.flush()
    print(f"  ✅ Created {len(records)} synthetic land records")

    # ── Documents ──────────────────────────────────────────────
    doc_count = 0
    for record in records[:20]:
        doc = Document(
            land_record_id=record.id,
            document_type=random.choice(list(DocumentType)),
            original_filename=f"document_{uuid.uuid4().hex[:8]}.pdf",
            stored_path=f"uploads/{record.id}/doc.pdf",
            file_size_bytes=random.randint(50000, 2000000),
            mime_type="application/pdf",
            status=DocumentStatus.VALIDATED,
            uploaded_by=officer_user.id,
        )
        db.add(doc)
        doc_count += 1
    await db.flush()
    print(f"  ✅ Created {doc_count} synthetic documents")

    await db.commit()
    print("✅ Seed complete!")
    print("\n📌 Demo Credentials:")
    print("   admin / Admin@1234              (ADMIN)")
    print("   officer_rajesh / Officer@1234   (OFFICER)")
    print("   verifier_priya / Verifier@1234  (VERIFIER)")
    print("   viewer_anand / Viewer@1234       (VIEWER)")
    print("\n⚠️  ALL DATA IS SYNTHETIC — NON-LEGALLY-BINDING DEMO ONLY")


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    # Windows consoles default to cp1252, which cannot encode the emoji below.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
