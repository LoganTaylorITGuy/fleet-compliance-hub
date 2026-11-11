"""Demo data: one provider, three fictional carriers and an academy fleet.

Everything is fake: company names, people, DOT/MC/CDL numbers and VINs. Dates
are relative to the day you seed, so statuses stay realistic: re-seed the day
before a demo.

The random generator is seeded, so every run produces the same people and
trucks. A few records are planted on purpose for the demo script:

* Red Draw Hauling (the carrier the demo Carrier Admin/Viewer log in to) has a
  driver whose medical card expires in 12 days, and a driver with an hours of
  service violation 2 days ago.
* One of its trailers has an open DVIR defect linked to an open repair in the
  provider's in-house trailer shop.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from faker import Faker
from sqlalchemy import delete, select

from .audit import audit_suppressed, record
from .auth.services import hash_password
from .extensions import db
from .models import (
    DVIR,
    AuditLog,
    Driver,
    DriverFileItem,
    DriverStatus,
    DrugAlcoholTest,
    DrugTestResult,
    DrugTestType,
    FileItemType,
    HOSLog,
    ImportRun,
    ImportTemplate,
    IntegrationConnection,
    MaintenanceRecord,
    Provider,
    RepairStatus,
    Role,
    ShopType,
    Tenant,
    TenantKind,
    TrainingCategory,
    TrainingRecord,
    User,
    Vehicle,
    VehicleType,
)
from .tenancy import all_tenants

SEED = 2026
DEFAULT_PASSWORD = "fleet-demo-2026"  # noqa: S105 - documented demo password, override with SEED_PASSWORD
HOS_DAYS = 30
TRAILER_SHOP = "In-house trailer shop"

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # VINs never use I, O or Q


@dataclass(frozen=True)
class TenantPlan:
    key: str
    name: str
    kind: str
    city: str
    drivers: int
    tractors: int
    trailers: int
    students: int = 0


def tenant_plans() -> list[TenantPlan]:
    academy = os.environ.get("DEMO_ACADEMY_NAME", "").strip() or "High Plains Driving Academy"
    return [
        TenantPlan("small", "Cedar Mesa Freight LLC", TenantKind.CARRIER, "Canyon", 3, 3, 3),
        TenantPlan("medium", "Red Draw Hauling Co.", TenantKind.CARRIER, "Hereford", 8, 6, 8),
        TenantPlan("large", "Blue Stem Transport Inc.", TenantKind.CARRIER, "Amarillo", 15, 12, 16),
        TenantPlan("academy", academy, TenantKind.ACADEMY, "Hereford", 2, 3, 2, students=6),
    ]


ACADEMY_COURSES = [
    "CDL Class A: Theory (ELDT)",
    "CDL Class A: Range Skills (ELDT)",
    "CDL Class A: Road Skills (ELDT)",
    "Pre-trip Inspection",
]
SAFETY_COURSES = [
    ("Defensive Driving", TrainingCategory.SAFETY, 730),
    ("Hazmat Endorsement Training", TrainingCategory.HAZMAT, 1095),
    ("Winter Driving Safety", TrainingCategory.SAFETY, 365),
    ("Cargo Securement", TrainingCategory.SAFETY, 730),
]


class Seeder:
    def __init__(self, today: date, password: str):
        self.today = today
        self.password_hash = hash_password(password)
        self.rng = random.Random(SEED)
        self.fake = Faker("en_US")
        self.fake.seed_instance(SEED)
        self.used_cdls: set[str] = set()

    # -- helpers -----------------------------------------------------------

    def days(self, n: int) -> date:
        return self.today + timedelta(days=n)

    def current(self, low: int = 45, high: int = 700) -> date:
        """A date comfortably in the future. apply_status_mix() adds the problems."""
        return self.days(self.rng.randint(low, high))

    def cdl_number(self) -> str:
        while True:
            number = "99" + "".join(self.rng.choices("0123456789", k=6))
            if number not in self.used_cdls:
                self.used_cdls.add(number)
                return number

    def vin(self) -> str:
        return "".join(self.rng.choices(VIN_CHARS, k=17))

    # -- build -------------------------------------------------------------

    def run(self, provider_name: str) -> dict[str, Tenant]:
        provider = Provider(name=provider_name)
        db.session.add(provider)
        db.session.flush()

        tenants: dict[str, Tenant] = {}
        for plan in tenant_plans():
            tenant = Tenant(
                provider_id=provider.id,
                name=plan.name,
                kind=plan.kind,
                dot_number="99" + "".join(self.rng.choices("0123456789", k=5)),
                mc_number="MC-99" + "".join(self.rng.choices("0123456789", k=4)),
                address_line=self.fake.street_address(),
                city=plan.city,
                state="TX",
                postal_code=self.fake.numerify("790##"),
            )
            db.session.add(tenant)
            db.session.flush()
            tenants[plan.key] = tenant
            drivers = self.build_drivers(tenant, plan)
            vehicles = self.build_fleet(tenant, plan)
            self.apply_status_mix(drivers, vehicles)
            self.build_hos(tenant, [d for d in drivers if not d.is_student])
            self.build_dvirs(tenant, vehicles, [d for d in drivers if not d.is_student])
            db.session.add(IntegrationConnection(tenant_id=tenant.id, service="motive"))

        self.plant_demo_moments(tenants)
        self.build_users(provider, tenants)
        return tenants

    def build_drivers(self, tenant: Tenant, plan: TenantPlan) -> list[Driver]:
        drivers = []
        for index in range(plan.drivers + plan.students):
            is_student = index >= plan.drivers
            hire = self.days(
                -self.rng.randint(20, 120) if is_student else -self.rng.randint(200, 3000)
            )
            driver = Driver(
                tenant_id=tenant.id,
                first_name=self.fake.first_name(),
                last_name=self.fake.last_name(),
                cdl_number=self.cdl_number(),
                cdl_state="TX",
                cdl_class="A" if self.rng.random() < 0.85 or is_student else "B",
                cdl_expiration=self.current(60, 1800),
                medical_card_expiration=self.current(),
                hire_date=hire,
                status=DriverStatus.ACTIVE,
                is_student=is_student,
                phone=self.fake.numerify("806-555-####"),
            )
            db.session.add(driver)
            db.session.flush()
            drivers.append(driver)
            self.build_driver_file(tenant, driver)
            self.build_tests(tenant, driver)
            self.build_training(tenant, driver, academy=plan.kind == TenantKind.ACADEMY)
        return drivers

    def build_driver_file(self, tenant: Tenant, driver: Driver) -> None:
        hire = driver.hire_date
        items = [
            (FileItemType.APPLICATION, hire - timedelta(days=10), None),
            (
                FileItemType.PREVIOUS_EMPLOYER_CHECK,
                hire + timedelta(days=self.rng.randint(5, 25)),
                None,
            ),
            (FileItemType.ROAD_TEST, hire - timedelta(days=3), None),
        ]
        if not driver.is_student:
            # Annual items: completed within the last year, so the next one is due later.
            mvr_done = self.days(-self.rng.randint(20, 300))
            review_done = self.days(-self.rng.randint(20, 300))
            items += [
                (FileItemType.MVR, mvr_done, mvr_done + timedelta(days=365)),
                (FileItemType.ANNUAL_REVIEW, review_done, review_done + timedelta(days=365)),
            ]
        for item_type, completed, due in items:
            db.session.add(
                DriverFileItem(
                    tenant_id=tenant.id,
                    driver_id=driver.id,
                    item_type=item_type,
                    completed_on=completed,
                    due_on=due,
                )
            )

    def build_tests(self, tenant: Tenant, driver: Driver) -> None:
        db.session.add(
            DrugAlcoholTest(
                tenant_id=tenant.id,
                driver_id=driver.id,
                test_type=DrugTestType.PRE_EMPLOYMENT,
                tested_on=driver.hire_date - timedelta(days=5),
                result=DrugTestResult.NEGATIVE,
            )
        )
        if not driver.is_student and self.rng.random() < 0.6:
            db.session.add(
                DrugAlcoholTest(
                    tenant_id=tenant.id,
                    driver_id=driver.id,
                    test_type=DrugTestType.RANDOM,
                    tested_on=self.days(-self.rng.randint(10, 300)),
                    result=DrugTestResult.NEGATIVE,
                )
            )

    def build_training(self, tenant: Tenant, driver: Driver, *, academy: bool) -> None:
        if driver.is_student:
            done = self.rng.randint(1, len(ACADEMY_COURSES))
            for index, course in enumerate(ACADEMY_COURSES):
                completed = (
                    driver.hire_date + timedelta(days=7 * (index + 1)) if index < done else None
                )
                if completed and completed > self.today:
                    completed = None
                db.session.add(
                    TrainingRecord(
                        tenant_id=tenant.id,
                        driver_id=driver.id,
                        course_name=course,
                        category=TrainingCategory.ACADEMY,
                        completed_on=completed,
                    )
                )
            return
        for course, category, valid_days in self.rng.sample(SAFETY_COURSES, k=2):
            expires = self.current(60, valid_days - 30)
            db.session.add(
                TrainingRecord(
                    tenant_id=tenant.id,
                    driver_id=driver.id,
                    course_name=course,
                    category=category,
                    completed_on=expires - timedelta(days=valid_days),
                    expires_on=expires,
                )
            )

    def build_fleet(self, tenant: Tenant, plan: TenantPlan) -> list[Vehicle]:
        vehicles = []
        makes = {
            "tractor": ["Peterbilt", "Kenworth", "Freightliner", "International"],
            "trailer": [
                "Hereford-built flatbed",
                "Wilson livestock",
                "Timpte hopper",
                "Great Dane reefer",
            ],
        }
        for vtype, count, start in (
            (VehicleType.TRACTOR, plan.tractors, 101),
            (VehicleType.TRAILER, plan.trailers, 501),
        ):
            for n in range(count):
                last_inspection = self.days(-self.rng.randint(20, 300))
                vehicle = Vehicle(
                    tenant_id=tenant.id,
                    unit_number=f"{'T' if vtype == VehicleType.TRACTOR else 'TR'}{start + n}",
                    vehicle_type=vtype,
                    make=self.rng.choice(makes[vtype]),
                    year=self.rng.randint(2014, 2025),
                    vin=self.vin(),
                    plate=self.fake.bothify("??#-####").upper(),
                    plate_state="TX",
                    registration_expiration=self.current(40, 360),
                    annual_inspection_on=last_inspection,
                    odometer=self.rng.randint(40_000, 900_000)
                    if vtype == VehicleType.TRACTOR
                    else None,
                )
                db.session.add(vehicle)
                db.session.flush()
                vehicles.append(vehicle)
                self.build_maintenance(tenant, vehicle)
        return vehicles

    def build_maintenance(self, tenant: Tenant, vehicle: Vehicle) -> None:
        is_trailer = vehicle.vehicle_type == VehicleType.TRAILER
        for _ in range(self.rng.randint(1, 3)):
            performed = self.days(-self.rng.randint(15, 200))
            db.session.add(
                MaintenanceRecord(
                    tenant_id=tenant.id,
                    vehicle_id=vehicle.id,
                    performed_on=performed,
                    work_done=self.rng.choice(
                        [
                            "Brake adjustment and lube",
                            "Tire replacement",
                            "Light and wiring repair",
                            "Annual service",
                        ]
                        if is_trailer
                        else [
                            "PM-A service, oil and filters",
                            "Brake chamber replacement",
                            "Tire rotation",
                            "DPF cleaning",
                        ]
                    ),
                    shop_type=ShopType.IN_HOUSE
                    if is_trailer
                    else self.rng.choice([ShopType.IN_HOUSE, ShopType.OUTSIDE]),
                    shop_name=TRAILER_SHOP
                    if is_trailer
                    else self.rng.choice([TRAILER_SHOP, "Panhandle Diesel Service"]),
                    status=RepairStatus.COMPLETED,
                )
            )
        # The next preventive maintenance is due 30 to 120 days after the last one.
        db.session.add(
            MaintenanceRecord(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                performed_on=self.days(-self.rng.randint(5, 90)),
                work_done="Preventive maintenance inspection",
                shop_type=ShopType.IN_HOUSE,
                shop_name=TRAILER_SHOP if is_trailer else "Panhandle Diesel Service",
                status=RepairStatus.COMPLETED,
                next_due_on=self.current(35, 120),
            )
        )

    def apply_status_mix(self, drivers: list[Driver], vehicles: list[Vehicle]) -> None:
        """Give each tenant a realistic mix: a few reds, several yellows, mostly green.

        Each working driver and unit in the tenant goes into one pool. About 10%
        (at least one) get a lapsed item, about 18% (at least one) get an item due
        soon, and the rest stay fully current. Fixed quotas instead of independent
        random dates, which compound into a mostly red fleet. Students stay green.
        """
        db.session.flush()
        pool: list[Driver | Vehicle] = [d for d in drivers if not d.is_student] + vehicles
        self.rng.shuffle(pool)
        reds = max(1, round(len(pool) * 0.10))
        yellows = max(1, round(len(pool) * 0.18))
        for index, item in enumerate(pool[: reds + yellows]):
            target = (
                self.days(-self.rng.randint(3, 40))
                if index < reds
                else self.days(self.rng.randint(4, 29))
            )
            if isinstance(item, Driver):
                self._set_driver_date(item, target)
            else:
                self._set_vehicle_date(item, target)

    def _set_driver_date(self, driver: Driver, target: date) -> None:
        match self.rng.choice(["medical", "medical", "cdl", "training", "mvr"]):
            case "medical":
                driver.medical_card_expiration = target
            case "cdl":
                driver.cdl_expiration = target
            case "training":
                driver.trainings[0].expires_on = target
            case "mvr":
                mvr = next(i for i in driver.file_items if i.item_type == FileItemType.MVR)
                mvr.due_on = target

    def _set_vehicle_date(self, vehicle: Vehicle, target: date) -> None:
        match self.rng.choice(["registration", "inspection", "maintenance"]):
            case "registration":
                vehicle.registration_expiration = target
            case "inspection":
                vehicle.annual_inspection_on = target - timedelta(days=365)
            case "maintenance":
                pm = next(r for r in vehicle.maintenance if r.next_due_on)
                pm.next_due_on = target

    def build_hos(self, tenant: Tenant, drivers: list[Driver]) -> None:
        """30 days of daily logs per driver, as the Motive sync would deliver them."""
        logs: dict[tuple[int, date], HOSLog] = {}
        for driver in drivers:
            for offset in range(HOS_DAYS, 0, -1):
                day = self.days(-offset)
                if day.weekday() == 6 or self.rng.random() < 0.12:  # Sundays and days off
                    driving, on_duty = 0.0, 0.0
                else:
                    driving = round(self.rng.uniform(5.5, 10.75) * 4) / 4
                    on_duty = round(driving + self.rng.uniform(1.0, 2.75), 2)
                log = self._hos(tenant, driver, day, driving, on_duty)
                logs[(driver.id, day)] = log
                db.session.add(log)
        if drivers:
            # One older violation per carrier, outside the 7-day window: history, not red.
            old = logs[(drivers[-1].id, self.days(-18))]
            old.driving_hours, old.on_duty_hours, old.off_duty_hours = 11.5, 13.5, 10.5
            old.violation, old.violation_note = True, "11-hour driving limit exceeded"

    def _hos(
        self, tenant: Tenant, driver: Driver, day: date, driving: float, on_duty: float
    ) -> HOSLog:
        return HOSLog(
            tenant_id=tenant.id,
            driver_id=driver.id,
            log_date=day,
            driving_hours=driving,
            on_duty_hours=on_duty,
            off_duty_hours=round(24 - on_duty, 2),
            source="Motive (mock)",
            external_id=f"mock-hos-{driver.id}-{day.isoformat()}",
        )

    def build_dvirs(self, tenant: Tenant, vehicles: list[Vehicle], drivers: list[Driver]) -> None:
        if not drivers:
            return
        for vehicle in vehicles:
            for _ in range(self.rng.randint(1, 2)):
                db.session.add(
                    DVIR(
                        tenant_id=tenant.id,
                        vehicle_id=vehicle.id,
                        driver_id=self.rng.choice(drivers).id,
                        inspected_on=self.days(-self.rng.randint(1, 20)),
                        defect_found=False,
                        external_id=f"mock-dvir-{vehicle.id}-{self.rng.randint(1000, 9999)}",
                    )
                )
        # One resolved defect per carrier, to show history.
        vehicle = self.rng.choice(vehicles)
        found = self.days(-self.rng.randint(8, 20))
        dvir = DVIR(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            driver_id=self.rng.choice(drivers).id,
            inspected_on=found,
            defects="Clearance light out, driver side",
            defect_found=True,
            defect_resolved=True,
            resolved_on=found + timedelta(days=1),
        )
        db.session.add(dvir)
        db.session.flush()
        db.session.add(
            MaintenanceRecord(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                dvir_id=dvir.id,
                performed_on=found + timedelta(days=1),
                work_done="Replaced clearance light (from DVIR)",
                shop_type=ShopType.IN_HOUSE,
                shop_name=TRAILER_SHOP,
                status=RepairStatus.COMPLETED,
            )
        )

    def plant_demo_moments(self, tenants: dict[str, Tenant]) -> None:
        """Make sure every step of the demo script has something to show."""
        db.session.flush()
        medium = tenants["medium"]
        drivers = db.session.scalars(
            select(Driver).where(Driver.tenant_id == medium.id).order_by(Driver.id)
        ).all()

        # 1. Medical card expiring in 12 days, otherwise a clean file.
        featured = drivers[1]
        featured.medical_card_expiration = self.days(12)
        featured.cdl_expiration = self.days(900)
        for training in featured.trainings:
            training.expires_on = self.days(400)
        for item in featured.file_items:
            if item.due_on:
                item.completed_on, item.due_on = self.days(-60), self.days(305)

        # 2. HOS violation two days ago (red: within the last 7 days).
        log = db.session.scalars(
            select(HOSLog).where(
                HOSLog.driver_id == drivers[2].id, HOSLog.log_date == self.days(-2)
            )
        ).one()
        log.driving_hours, log.on_duty_hours, log.off_duty_hours = 11.75, 14.5, 9.5
        log.violation, log.violation_note = True, "11-hour driving limit exceeded"

        # 3. Trailer with an open DVIR defect, in the in-house trailer shop now.
        trailer = db.session.scalars(
            select(Vehicle)
            .where(Vehicle.tenant_id == medium.id, Vehicle.vehicle_type == VehicleType.TRAILER)
            .order_by(Vehicle.id)
        ).first()
        dvir = DVIR(
            tenant_id=medium.id,
            vehicle_id=trailer.id,
            driver_id=drivers[0].id,
            inspected_on=self.days(-1),
            defects="Air leak at gladhand, brake chamber on axle 2 not holding pressure",
            defect_found=True,
            defect_resolved=False,
            external_id="mock-dvir-demo-open",
        )
        db.session.add(dvir)
        db.session.flush()
        db.session.add(
            MaintenanceRecord(
                tenant_id=medium.id,
                vehicle_id=trailer.id,
                dvir_id=dvir.id,
                performed_on=self.today,
                work_done="Replace gladhand seal and axle 2 brake chamber (from DVIR)",
                shop_type=ShopType.IN_HOUSE,
                shop_name=TRAILER_SHOP,
                status=RepairStatus.OPEN,
            )
        )

        # 4. One failed random test in the large carrier (red).
        large_driver = db.session.scalars(
            select(Driver).where(Driver.tenant_id == tenants["large"].id).order_by(Driver.id)
        ).all()[5]
        db.session.add(
            DrugAlcoholTest(
                tenant_id=tenants["large"].id,
                driver_id=large_driver.id,
                test_type=DrugTestType.RANDOM,
                tested_on=self.days(-4),
                result=DrugTestResult.POSITIVE,
            )
        )
        large_driver.status = DriverStatus.ON_LEAVE

    def build_users(self, provider: Provider, tenants: dict[str, Tenant]) -> None:
        def user(email, name, role, *, tenant=None, permissions=""):
            db.session.add(
                User(
                    email=email,
                    name=name,
                    role=role,
                    provider_id=provider.id if tenant is None else None,
                    tenant_id=tenant.id if tenant else None,
                    permissions=permissions,
                    password_hash=self.password_hash,
                )
            )

        user("admin@demo.example", "Dana Whitfield", Role.PROVIDER_ADMIN)
        user("shop@demo.example", "Rusty Kemp", Role.PROVIDER_LIMITED, permissions="maintenance")
        user("academy@demo.example", "Lena Ortiz", Role.PROVIDER_LIMITED, permissions="training")
        user("owner@demo.example", "Cal Brennan", Role.CARRIER_ADMIN, tenant=tenants["medium"])
        user("viewer@demo.example", "Jo Marsh", Role.CARRIER_VIEWER, tenant=tenants["medium"])
        user("small-owner@demo.example", "Mae Collins", Role.CARRIER_ADMIN, tenant=tenants["small"])
        user("large-owner@demo.example", "Wes Harlan", Role.CARRIER_ADMIN, tenant=tenants["large"])


# Delete order: children before parents.
_TABLES_IN_DELETE_ORDER = (
    AuditLog,
    ImportRun,
    ImportTemplate,
    IntegrationConnection,
    MaintenanceRecord,
    DVIR,
    HOSLog,
    TrainingRecord,
    DrugAlcoholTest,
    DriverFileItem,
    Vehicle,
    Driver,
    User,
    Tenant,
    Provider,
)


def has_data() -> bool:
    return db.session.scalars(select(Provider.id)).first() is not None


def reset_all() -> None:
    """Delete every row in every table. Local and demo databases only."""
    with all_tenants():
        for model in _TABLES_IN_DELETE_ORDER:
            db.session.execute(delete(model))
        db.session.commit()


def seed_demo(
    provider_name: str, *, today: date | None = None, password: str | None = None
) -> dict:
    """Load the demo data set. Returns a small summary for the CLI to print."""
    today = today or date.today()
    password = password or os.environ.get("SEED_PASSWORD", "").strip() or DEFAULT_PASSWORD
    with all_tenants(), audit_suppressed():
        tenants = Seeder(today, password).run(provider_name)
        db.session.flush()
        for tenant in tenants.values():
            record("seed", f"Loaded demo data for {tenant.name}", tenant_id=tenant.id)
        record("seed", "Loaded demo data set")
        stamp = datetime.combine(today, time(6, 0), tzinfo=UTC)
        for connection in db.session.scalars(select(IntegrationConnection)):
            connection.last_synced_at = stamp
        db.session.commit()
        counts = {
            plan_key: {
                "name": t.name,
                "drivers": db.session.query(Driver).filter_by(tenant_id=t.id).count(),
                "vehicles": db.session.query(Vehicle).filter_by(tenant_id=t.id).count(),
            }
            for plan_key, t in tenants.items()
        }
    return counts
