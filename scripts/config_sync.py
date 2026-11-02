"""Keep the app config (feature flags, theme, banners, booking rules, pricing…) when the
database changes.

The `configs` table is the only place portal edits live, so moving to a new database would
otherwise lose them. Three commands:

    # Save every config row from the current database to a JSON file (commit it to keep it):
    uv run python -m scripts.config_sync export --file config/app_configs.json

    # Load that file into a (new) database. Existing keys are left alone unless --overwrite:
    uv run python -m scripts.config_sync import --file config/app_configs.json [--overwrite]

    # Give every registered key a row holding its default, where it doesn't have one yet:
    uv run python -m scripts.config_sync defaults

A database with no rows at all still works — the backend falls back to the registry defaults
(app/core/config_registry.py) — but seeded rows show up in the portal straight away.

Every value is validated against its schema before it's written, and every write lands in
the activity log as a system action. Nothing is ever deleted.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.core.config_registry import REGISTRY, default_value, validate_value
from app.db.session import AsyncSessionLocal
from app.models.config import Config
from app.repositories.config_repo import ConfigRepository
from app.services.audit_service import AuditService

FILE_VERSION = 1


async def export() -> dict:
    async with AsyncSessionLocal() as session:
        rows = await ConfigRepository(session).list_all()
    for row in rows:
        print(f"  {'●' if row.is_active else '○'} {row.key}")
    return {
        "version": FILE_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "configs": [
            {
                "key": row.key,
                "value": row.value,
                "description": row.description,
                "is_active": row.is_active,
            }
            for row in rows
        ],
    }


async def _write(
    entries: list[dict], *, overwrite: bool, action: str, dry_run: bool = False
) -> None:
    created = updated = skipped = 0
    problems: list[str] = []
    async with AsyncSessionLocal() as session:
        repo = ConfigRepository(session)
        audit = AuditService(session)
        for entry in entries:
            key = entry["key"]
            try:
                value = validate_value(key, entry["value"])
            except ValidationError as exc:
                problems.append(f"{key}: {exc.errors()[0]['msg']}")
                continue
            existing = await repo.get_by_key(key)
            if existing is not None and not overwrite:
                skipped += 1
                print(f"  = {key} (already set — kept)")
                continue
            if existing is None:
                session.add(
                    Config(
                        key=key,
                        value=value,
                        description=entry.get("description"),
                        is_active=entry.get("is_active", True),
                    )
                )
                created += 1
                print(f"  + {key}")
            else:
                existing.value = value
                existing.is_active = entry.get("is_active", existing.is_active)
                if entry.get("description") is not None:
                    existing.description = entry["description"]
                updated += 1
                print(f"  ~ {key} (overwritten)")
            audit.log(
                actor_id=None,
                action=action,
                entity_type="config",
                entity_id=key,
                metadata={"value": value},
            )
        if problems:
            await session.rollback()
            print("\nNothing was written — these values don't pass validation:")
            for problem in problems:
                print(f"  ✗ {problem}")
            sys.exit(1)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    verb = "Dry run, nothing written — would have" if dry_run else "Done:"
    print(f"\n{verb} {created} created, {updated} overwritten, {skipped} kept as they were.")


async def import_entries(entries: list[dict], *, overwrite: bool, dry_run: bool) -> None:
    await _write(entries, overwrite=overwrite, action="config.import", dry_run=dry_run)


async def seed_defaults(*, dry_run: bool) -> None:
    entries = [
        {"key": key, "value": default_value(key), "description": spec.description}
        for key, spec in REGISTRY.items()
    ]
    print(f"Seeding defaults for {len(entries)} registered key(s):")
    await _write(entries, overwrite=False, action="config.seed_default", dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Database → JSON file.")
    p_export.add_argument("--file", type=Path, default=Path("config/app_configs.json"))

    p_import = sub.add_parser("import", help="JSON file → database.")
    p_import.add_argument("--file", type=Path, default=Path("config/app_configs.json"))
    p_import.add_argument(
        "--overwrite", action="store_true", help="Replace keys the database already has."
    )
    p_import.add_argument("--dry-run", action="store_true")

    p_defaults = sub.add_parser("defaults", help="Seed missing registered keys with defaults.")
    p_defaults.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "export":
        payload = asyncio.run(export())
        args.file.parent.mkdir(parents=True, exist_ok=True)
        args.file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"Exported {len(payload['configs'])} config(s) to {args.file}.")
    elif args.command == "import":
        payload = json.loads(args.file.read_text())
        entries = payload["configs"] if isinstance(payload, dict) else payload
        print(f"Importing {len(entries)} config(s) from {args.file}:")
        asyncio.run(import_entries(entries, overwrite=args.overwrite, dry_run=args.dry_run))
    else:
        asyncio.run(seed_defaults(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
