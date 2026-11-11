"""Motive (ELD and fleet platform) client: a stub showing where Motive plugs in.

In demo mode every method returns generated data shaped like a typical REST
JSON response (a ``data`` list plus ``pagination``). Nothing here calls Motive.

TODO (before real use): every endpoint path, query parameter, field name,
pagination scheme, rate limit and auth header below must be checked against
Motive's developer documentation. None of them have been verified, and none
should be assumed to match the real API.

The API key comes from the environment (``MOTIVE_API_KEY``) and is never
hard-coded or stored in the database. A later version would hold one key per
tenant in a secret store, referenced by ``IntegrationConnection.api_key_ref``.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


class MotiveNotConfigured(RuntimeError):
    """Raised when a live call is attempted without demo mode or an API key."""


@dataclass(frozen=True)
class RosterDriver:
    """A local driver the mock knows about, as Motive would have them on file."""

    local_id: int
    first_name: str
    last_name: str
    license_number: str


@dataclass(frozen=True)
class RosterVehicle:
    local_id: int
    number: str
    vehicle_type: str
    odometer: int | None


@dataclass
class MockRoster:
    """In demo mode the mock 'account' mirrors the carrier's own drivers and units."""

    drivers: list[RosterDriver] = field(default_factory=list)
    vehicles: list[RosterVehicle] = field(default_factory=list)


def _rng(*parts) -> random.Random:
    """A generator seeded from the inputs, so the same day always returns the same data."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


class MotiveClient:
    # TODO: base URL, API version and auth header come from Motive's developer docs.

    def __init__(
        self,
        api_key: str | None,
        *,
        demo_mode: bool,
        roster: MockRoster | None = None,
        now: datetime | None = None,
    ):
        self.api_key = api_key or None
        self.demo_mode = demo_mode
        self.roster = roster or MockRoster()
        self.now = now or datetime.now()
        if not demo_mode and not self.api_key:
            raise MotiveNotConfigured("Set MOTIVE_API_KEY or enable DEMO_MODE.")

    @property
    def mode_label(self) -> str:
        return "Connected (demo mode)" if self.demo_mode else "Connected"

    # -- public API ---------------------------------------------------------

    def get_drivers(self) -> dict:
        # TODO: real endpoint path and fields must come from Motive's docs.
        if not self.demo_mode:
            return self._live_get("drivers")
        return self._page(
            [
                {
                    "id": f"mock-drv-{d.local_id}",
                    "first_name": d.first_name,
                    "last_name": d.last_name,
                    "license_number": d.license_number,
                    "status": "active",
                }
                for d in self.roster.drivers
            ]
        )

    def get_vehicles(self) -> dict:
        # TODO: real endpoint path and fields must come from Motive's docs.
        if not self.demo_mode:
            return self._live_get("vehicles")
        today = self.now.date()
        records = []
        for v in self.roster.vehicles:
            odometer = None
            if v.odometer is not None:
                odometer = v.odometer + _rng("odo", v.local_id, today).randint(150, 650)
            records.append(
                {
                    "id": f"mock-veh-{v.local_id}",
                    "number": v.number,
                    "type": v.vehicle_type,
                    "current_odometer_miles": odometer,
                }
            )
        return self._page(records)

    def get_hos_logs(self, start: date, end: date) -> dict:
        """Daily duty totals per driver for ``start``..``end`` inclusive.

        Today's log (if in range) is still in progress and grows with the hour.
        """
        # TODO: real endpoint path, date params and duty-status fields from Motive's docs.
        if not self.demo_mode:
            return self._live_get("hos_logs", start=start, end=end)
        today = self.now.date()
        records = []
        day = start
        while day <= min(end, today):
            for d in self.roster.drivers:
                records.append(self._mock_log(d, day, in_progress=day == today))
            day += timedelta(days=1)
        return self._page(records)

    def get_dvirs(self, start: date, end: date) -> dict:
        # TODO: real endpoint path and inspection fields from Motive's docs.
        if not self.demo_mode:
            return self._live_get("dvirs", start=start, end=end)
        today = self.now.date()
        records = []
        day = start
        drivers = self.roster.drivers
        while day <= min(end, today) and drivers:
            for v in self.roster.vehicles:
                rng = _rng("dvir", v.local_id, day)
                if rng.random() < 0.5:  # about half the units run each day
                    continue
                driver = drivers[rng.randrange(len(drivers))]
                records.append(
                    {
                        "id": f"mock-dvir-{v.local_id}-{day.isoformat()}",
                        "vehicle_id": f"mock-veh-{v.local_id}",
                        "vehicle_number": v.number,
                        "driver_id": f"mock-drv-{driver.local_id}",
                        "date": day.isoformat(),
                        "inspection_type": "pre_trip",
                        "defects": [],
                    }
                )
            day += timedelta(days=1)
        return self._page(records)

    # -- internals ----------------------------------------------------------

    def _mock_log(self, driver: RosterDriver, day: date, *, in_progress: bool) -> dict:
        rng = _rng("hos", driver.local_id, day)
        off_day = day.weekday() == 6 or rng.random() < 0.12
        driving = 0.0 if off_day else round(rng.uniform(5.5, 10.5) * 4) / 4
        on_duty = 0.0 if off_day else round(driving + rng.uniform(1.0, 2.5), 2)
        if in_progress:
            # Scale today's hours by how much of the working day has passed (06:00 to 18:00).
            fraction = min(max((self.now.hour + self.now.minute / 60 - 6) / 12, 0), 1)
            driving, on_duty = round(driving * fraction, 2), round(on_duty * fraction, 2)
        return {
            "id": f"mock-hos-{driver.local_id}-{day.isoformat()}",
            "driver_id": f"mock-drv-{driver.local_id}",
            "date": day.isoformat(),
            "driving_hours": driving,
            "on_duty_hours": on_duty,
            "off_duty_hours": round(24 - on_duty, 2) if not in_progress else None,
            "in_progress": in_progress,
            "violations": [],
        }

    @staticmethod
    def _page(records: list[dict]) -> dict:
        return {
            "data": records,
            "pagination": {"page": 1, "per_page": len(records), "total": len(records)},
        }

    def _live_get(self, resource: str, **params) -> dict:
        # TODO: implement with an HTTP client (timeouts, retries with backoff,
        # pagination, rate-limit handling) once endpoints are confirmed against
        # Motive's developer docs. The key would go in an auth header, never a URL.
        raise NotImplementedError(
            f"Live Motive calls are not implemented yet ({resource}). Use DEMO_MODE=true."
        )
