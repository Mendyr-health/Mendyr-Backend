"""Permanently hard-delete specified users and cascade through every referencing table.

Accepts a comma-separated list of emails or user UUIDs (or via file / arguments),
safely nullifies referencing foreign keys in unrelated records, and deletes all user-owned
records across every table (bookings, care plans, addresses, wallets, reviews, support tickets,
payouts, professional profiles, device tokens, refresh tokens, audit logs, etc.).

Usage:
    # Dry-run inspection (validates constraints and prints affected row counts without deleting):
    uv run python -m scripts.delete_users --users "user1@example.com, user2@example.com" --dry-run

    # Execute interactive deletion with confirmation prompt:
    uv run python -m scripts.delete_users --users "user1@example.com, 123e4567-e89b-12d3-a456-426614174000"

    # Bypass confirmation prompt:
    uv run python -m scripts.delete_users --users "user1@example.com,user2@example.com" --force

    # Pass as positional arguments:
    uv run python -m scripts.delete_users user1@example.com user2@example.com

    # Read from file:
    uv run python -m scripts.delete_users --file users_to_delete.txt

    # Dispatch as an asynchronous Celery background job:
    uv run python -m scripts.delete_users --users "user1@example.com" --queue
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.services.user_cleanup_service import UserCleanupService, parse_user_identifiers


async def run_cleanup(
    identifiers: list[str],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    parsed = parse_user_identifiers(identifiers)
    if not parsed:
        print("No user identifiers provided.")
        return 1

    async with AsyncSessionLocal() as session:
        service = UserCleanupService(session)

        # 1. First run a dry-run check to find records and display impact preview
        preview = await service.delete_users(parsed, dry_run=True)

        if not preview.found_users:
            print("No matching users found in the database.")
            if preview.not_found_identifiers:
                print(f"Unmatched identifiers: {', '.join(preview.not_found_identifiers)}")
            return 0

        print(f"\nFound {len(preview.found_users)} user(s) to delete:")
        for u in preview.found_users:
            email_display = u.email or "<no email>"
            phone_display = u.phone_number or "<no phone>"
            print(f"  • {email_display} ({u.role}) — {u.full_name} [ID: {u.id}, Phone: {phone_display}]")

        if preview.not_found_identifiers:
            print(f"\nWarning: {len(preview.not_found_identifiers)} identifier(s) were NOT found:")
            for item in preview.not_found_identifiers:
                print(f"  • {item}")

        print("\nImpact summary (records to be deleted / updated):")
        for table, count in sorted(preview.counts.items()):
            action = "nullified/unassigned" if "cleared" in table or "unassigned" in table else "deleted"
            print(f"  - {table}: {count} row(s) {action}")

        if dry_run:
            print("\n[DRY RUN COMPLETE] Rolled back all changes. No database rows were modified.")
            return 0

        # Confirmation prompt if not forced
        if not force:
            confirm = input(
                f"\nAre you sure you want to PERMANENTLY delete these {len(preview.found_users)} "
                "user(s) and all their associated data across all tables? [y/N]: "
            )
            if confirm.strip().lower() not in ("y", "yes"):
                print("Aborted by user. No data was deleted.")
                return 0

    # 2. Execute actual deletion in a fresh transaction
    async with AsyncSessionLocal() as session:
        service = UserCleanupService(session)
        actual_summary = await service.delete_users(parsed, dry_run=False)

    print("\n[SUCCESS] Deletion completed successfully.")
    print("Deleted/updated record counts:")
    for table, count in sorted(actual_summary.counts.items()):
        print(f"  - {table}: {count}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "positional_users",
        nargs="*",
        help="Space or comma-separated user emails or UUIDs.",
    )
    parser.add_argument(
        "--users",
        "-u",
        dest="users_flag",
        help="Comma-separated list of user emails or UUIDs (e.g. 'u1@example.com, u2@example.com').",
    )
    parser.add_argument(
        "--file",
        "-f",
        dest="file_path",
        help="Path to a text file containing user emails or UUIDs (one per line or comma-separated).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the deletion in a rolled-back transaction to verify constraints and row counts.",
    )
    parser.add_argument(
        "--force",
        "-y",
        action="store_true",
        help="Bypass interactive confirmation prompt.",
    )
    parser.add_argument(
        "--queue",
        action="store_true",
        help="Queue deletion as an asynchronous Celery background task instead of executing synchronously.",
    )

    args = parser.parse_args()

    identifiers: list[str] = []
    if args.users_flag:
        identifiers.extend(args.users_flag.split(","))
    if args.positional_users:
        identifiers.extend(args.positional_users)
    if args.file_path:
        p = Path(args.file_path)
        if not p.is_file():
            print(f"Error: File not found: {args.file_path}", file=sys.stderr)
            sys.exit(1)
        content = p.read_text(encoding="utf-8")
        identifiers.extend(content.replace("\n", ",").split(","))

    cleaned = parse_user_identifiers(identifiers)
    if not cleaned:
        parser.print_help()
        sys.exit(1)

    if args.queue:
        from app.workers.tasks.users import delete_users_job

        print(f"Dispatching Celery background task for {len(cleaned)} user identifier(s)...")
        task = delete_users_job.delay(cleaned, dry_run=args.dry_run)
        print(f"Task dispatched with ID: {task.id}")
        sys.exit(0)

    exit_code = asyncio.run(
        run_cleanup(cleaned, dry_run=args.dry_run, force=args.force)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

