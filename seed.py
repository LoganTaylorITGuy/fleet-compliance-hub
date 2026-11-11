"""Load the demo data set.

    python seed.py            # seed an empty database
    python seed.py --reset    # wipe all data first (refused in production)

Run ``flask db upgrade`` first. See README for the demo logins.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    args = parser.parse_args(argv)

    load_dotenv()
    from app import create_app
    from app.seed import has_data, reset_all, seed_demo

    app = create_app()
    if app.config["APP_ENV"] == "production":
        print("Refusing to seed demo data in production.", file=sys.stderr)
        return 2

    with app.app_context():
        if has_data():
            if not args.reset:
                print("The database already has data. Re-run with --reset to replace it.")
                return 1
            reset_all()
            print("Existing data deleted.")
        summary = seed_demo(app.config["PROVIDER_NAME"])

    print(f"Seeded {app.config['PROVIDER_NAME']}:")
    for row in summary.values():
        print(f"  {row['name']}: {row['drivers']} drivers, {row['vehicles']} units")
    print(
        "Demo logins are listed in README.md (password: SEED_PASSWORD or the documented default)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
