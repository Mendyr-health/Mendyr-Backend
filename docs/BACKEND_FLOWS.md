# Mendyr Backend — Step-by-Step Flows

Grounded directly in `app/services/*.py` and the endpoints that call them. See
`docs/ARCHITECTURE_DIAGRAM.md` for the request-lifecycle/router-level view; this document
walks through the business logic inside specific flows.

---

## 1. Patient journey: register → login → book → offer/accept → check-in/out → pay → review

1. **Register** — `POST /api/auth/register` (`app/api/web/auth.py`) → `AuthService.register`
   (`app/services/auth_service.py:68`). Rejects a duplicate email (`ConflictError`). Creates a
   `User` (`email`, `phone_number`, `full_name`, `hashed_password` via `hash_password`,
   `role=PATIENT`, `gender`, `date_of_birth`, `referral_code`). Calls
   `WalletService.get_or_create_wallet(user.id)`, then creates a `PatientProfile`
   (`address_line`, `city`, `state`). Response: cookies set via `_issue_session_cookies` +
   `ApiResponse.ok(AuthResultOut)`.
2. **Login** — `POST /api/auth/login` → `AuthService.login_with_password` (line 59): looks up
   by email, verifies password hash, sets `user.last_login_at`, and the endpoint issues fresh
   session cookies. No tokens are returned in the body for this path — they only ever live in
   the httpOnly cookies.
3. **Quote** — `POST /api/v1/bookings/quote` (`require_patient`) →
   `BookingService.quote` (`app/services/booking_service.py:97`) → delegates to
   `PricingService.quote(base_price, coupon_code)` — no rows written, pure price preview.
4. **Create booking** — `POST /api/v1/bookings` → `BookingService.create_booking` (line 102):
   validates the address belongs to the patient and the scheduled time is in the future
   (and, for `CARE_PLAN` bookings, that `total_visits` is set); re-quotes via `pricing`; writes
   a `Booking` row with status `CREATED` and a full price snapshot (`base_price`,
   `discount_amount`, `platform_fee`, `tax_amount`, `total_amount`,
   `professional_payout_amount`, `commission_pct`) plus `booking_code` (`MNDYR-XXXXXX`) and
   `service_location` (PostGIS point from the address). No professional is assigned yet.
5. **Pay** — `POST /api/v1/payments/orders` (`require_patient`) →
   `PaymentService.create_order` (`app/services/payment_service.py:33`): confirms
   `booking.status == CREATED`, creates a Razorpay order, writes a `Payment` row
   (`status=PENDING`). The client then completes checkout with Razorpay directly.
6. **Verify & dispatch** — `POST /api/v1/payments/verify` →
   `PaymentService.verify_and_capture` (line 60): verifies the Razorpay signature (else
   `PaymentError`), marks the `Payment` `CAPTURED`, transitions the `Booking` to `SEARCHING`
   via `BookingService.transition_status`, then calls
   `MatchingService.start_dispatch(booking.id)`. A booking never enters the dispatch queue
   before money has moved — enforced here, not just documented.
   The Razorpay webhook (`POST /api/v1/webhooks/razorpay` → `PaymentService.handle_webhook`,
   line 91) is an idempotent fallback for the same transition: it only re-captures if
   `payment.status != CAPTURED`, and only re-triggers dispatch if
   `booking.status == CREATED` — both guards make it safe if the client-driven `verify`
   call already ran.
7. **Dispatch** — `MatchingService.start_dispatch` runs `_run_round(booking, round_number=1)`:
   `ProfessionalRepository.find_nearby_candidates` selects up to `OFFERS_PER_ROUND` (3) nearby,
   approved, online, qualified professionals (excluding anyone already offered), each getting a
   `BookingOffer` row (`PENDING`, `expires_at`) and a push notification. If a round starts with
   zero candidates, it recurses immediately into the next (wider-radius) round rather than
   waiting for expiry.
8. **Offer response** — `POST /api/v1/offers/{booking_id}/respond` (`require_professional`) →
   `MatchingService.respond_to_offer` (line 105): on accept, marks that `BookingOffer`
   `ACCEPTED`, cancels every sibling offer in the round, sets `booking.professional_id`, and
   transitions the booking to `ASSIGNED`. If the offer already expired by the time the
   professional responds, it's marked `EXPIRED` and a `ValidationAppError` is raised instead
   (a race-guard independent of the Celery sweep below).
9. **No response in time** — the Celery beat task calls
   `MatchingService.expire_and_escalate` (line 138) only once *every* pending offer in the
   current round has expired; it marks them `EXPIRED` and starts the next round at a wider
   radius (`_radius_for_round` linearly interpolates between `DEFAULT_SEARCH_RADIUS_KM` and
   `MAX_SEARCH_RADIUS_KM` over `BOOKING_MAX_OFFER_ROUNDS`). If the last round still finds zero
   candidates, the booking moves to `FAILED` and `NoProfessionalAvailableError` is raised.
10. **En route / check-in / check-out** — `require_professional`-gated, all in
    `VisitService` (`app/services/visit_service.py`):
    - `POST /api/v1/bookings/{id}/en-route` → `mark_en_route` (line 50): sets
      `BookingVisit.en_route_at`, transitions to `EN_ROUTE`.
    - `POST /api/v1/bookings/{id}/check-in` → `check_in` (line 57): computes
      `ST_Distance(booking.service_location, current_point)`; rejects with the actual/required
      distance in the message if outside `settings.VISIT_CHECKIN_GEOFENCE_METERS`; on success
      records `checked_in_at`, `checked_in_location`, `checked_in_distance_meters`, and
      transitions to `IN_PROGRESS`.
    - `POST /api/v1/bookings/{id}/check-out` → `check_out` (line 81): requires a prior
      check-in (else `ValidationAppError`); records `checked_out_at`, `checked_out_location`;
      if a care note was submitted, sets `visit_summary_notes` and, if vitals were included,
      `vitals_recorded = json.dumps(payload.care_note.vitals.model_dump(exclude_none=True))` —
      stored as a **JSON string column**, not structured columns (see Known Gaps, item 1);
      also records `proof_of_visit_photo_url`; transitions the booking to `COMPLETED`.
11. **Review** — `POST /api/v1/reviews` (`require_patient`) → `ReviewService.create_review`
    (`app/services/review_service.py:22`): requires the booking is the reviewer's own,
    `COMPLETED`, and has an assigned professional; a DB unique-constraint violation on a
    second review for the same booking is converted to `ConflictError`. On success, updates the
    professional's rolling average with the incremental-mean formula
    `new_avg = (old_avg * old_count + new_rating) / (old_count + 1)`, and increments
    `total_ratings`.
12. **Response shape** — every step above returns `ApiResponse[T]` (`{success, data, meta,
    error}`), except `offers.py`'s `respond_to_offer` and a few older routes
    (`bookings`, `visits`) which still return the bare Pydantic model directly rather than
    wrapping it in `ApiResponse` — worth noting as an inconsistency (see Known Gaps, item 6).
13. Cancellation, at any point before `COMPLETED`, goes through `BookingService.cancel`
    (line 152): blocks if already `COMPLETED`/`CANCELLED`/`NO_SHOW`; applies
    `CANCELLATION_FEE_PCT` if inside `FREE_CANCELLATION_WINDOW_MINUTES` of the scheduled start
    **and** the booking is `ASSIGNED` or `CONFIRMED`; then transitions to `CANCELLED`.
    `PaymentService.refund` is the caller's responsibility to invoke afterward for the
    remainder (it accumulates `amount_refunded` and moves status to `REFUNDED`/
    `PARTIALLY_REFUNDED`, supporting multiple partial refunds safely).

---

## 2. Nurse journey: register → KYC → admin verification → online → offers

1. **Register** — same `POST /api/auth/register` path as patients, but
   `AuthService.register` branches on `role == PROFESSIONAL`: creates a `ProfessionalProfile`
   with `professional_type` hard-coded to `NURSE`, plus `address_line`/`city`/`state`,
   `experience_description`, `qualifications`, `certifications`, and `preferred_contact`
   (defensively parsed, defaulting to `EMAIL`).
   (There is a second, separate onboarding path for OTP-authenticated professionals:
   `POST /api/v1/professionals/onboard` → `ProfessionalService.onboard`
   (`app/services/professional_service.py:40`) — rejects if a profile already exists, creates
   the `ProfessionalProfile` with `verification_status=PENDING`, and inserts
   `ProfessionalSpecialization`/`ProfessionalService` (opt-in) rows from the payload's id lists.)
2. **KYC document upload** — `POST /api/v1/professionals/me/documents/upload-url` (presigned
   S3 URL) then `POST /api/v1/professionals/me/documents` → `ProfessionalService.upload_document`
   (line 77): creates a `ProfessionalDocument` row (`document_type`, `file_url`,
   `verification_status=PENDING`).
3. **Admin verification queue** — the current admin UI lists pending nurses via the generic
   `GET /api/v1/search?entity=nurses&status=pending`, which `AdminConsoleService.search`
   (`app/services/admin_console_service.py:168`) dispatches to
   `ProfessionalRepository.search(q, verification_status, limit, offset)`, mapped through
   `nurse_admin_out` (includes nested `documents` via `_nurse_document_out`). (An older,
   still-mounted pair — `GET /api/v1/admin/professionals/pending` /
   `POST /api/v1/admin/professionals/{id}/review`, gated by `require_ops_or_admin` — duplicates
   this same underlying capability and appears superseded by the search-based flow for the
   current frontend.)
4. **Approve/reject** — `POST /api/v1/admin/nurses/{id}/approve` or `/reject`
   (`require_admin`) → `AdminConsoleService.review_nurse` (line 207) →
   `ProfessionalService.review_kyc` (line 90) — one method handles both branches via
   `decision.approve`: approve sets `verification_status=APPROVED`, `verified_at=now`, clears
   `rejection_reason`; reject requires a `rejection_reason` (else `ValidationAppError`) and
   sets `verification_status=REJECTED`. `review_nurse` then writes an `AuditLog` row
   (`action="nurse.approve"`/`"nurse.reject"`, `entity_type="professional_profile"`,
   `metadata_json={"new_value": {"verificationStatus": ...}}`).
5. **Go online** — `PATCH /api/v1/professionals/me/availability/status`
   (`require_professional`) → `ProfessionalService.update_availability_status` (line 140):
   sets `availability_status`, and if a location is given, updates `current_location` (PostGIS
   point) + `location_updated_at`. (The weekly recurring schedule is a separate endpoint,
   `PUT /api/v1/professionals/me/availability/slots`, which fully replaces the professional's
   `ProfessionalAvailabilitySlot` rows — delete-then-insert, chosen to keep the endpoint
   idempotent per the code's own comment.)
6. **Receive offers** — once `APPROVED`, `ONLINE`, and qualified for a requested service, the
   professional becomes a dispatch candidate (see flow 1, steps 7-9) and reaches
   `POST /api/v1/offers/{booking_id}/respond` to accept/reject.

---

## 3. Admin managing the platform

- **Nurse verification queue** — see flow 2, step 3.
- **Generic `/api/v1/search` pattern** — `app/api/v1/endpoints/search.py`'s own docstring
  states the intent directly: "Generic cross-entity search used by every admin-console list
  screen — one endpoint, dispatched by `entity`, instead of five near-identical list
  endpoints." It is `require_admin`-gated and deliberately not nested under `/admin` because
  the frontend calls it as a bare `/api/v1/search`. `AdminConsoleService.search` (line 168)
  dispatches on the `SearchEntity` literal:
  - `"nurses"` → `ProfessionalRepository.search` → `nurse_admin_out`
  - `"patients"` → `PatientRepository.search` → `patient_admin_out`
  - `"services"` → `CatalogService.search_services` → `service_admin_out`
  - `"waitlist"` → `WaitlistRepository.search` → `waitlist_admin_out`
  - `"contacts"` → `ContactRepository.search` → `contact_admin_out`
  Every branch returns `(items, total)` and the endpoint wraps it with
  `pagination_meta(page, limit, total)`. Five frontend hooks — `useNurses.ts`,
  `usePatients.ts`, `useServices.ts`, `useWaitlist.ts`, `useContacts.ts` — all hit this one
  path with a different `entity` query param instead of the backend exposing five separate
  list endpoints.
- **Service catalog management** — read via `GET /api/v1/services` /
  `/api/v1/services/categories` (public, no auth), and via the admin `services` search entity
  above for the admin list screen; `ServiceCreateIn`/`ServiceUpdateIn` schemas exist in
  `app/schemas/admin_console.py` for catalog editing.
- **Waitlist / contact inquiries** — `POST /api/v1/admin/waitlist/{id}/notify` →
  `AdminConsoleService.mark_waitlist_notified` (line 240) sets `entry.notified = True`.
  `PATCH /api/v1/admin/contacts/{id}/status` → `update_contact_status` (line 250) sets
  `inquiry.status`. Both are simple single-field mutations with no side effects beyond the
  flush.
- **Dashboard stats** — `GET /api/v1/admin/dashboard` (`require_admin`; the same path is used
  by both the Admin and Super Admin dashboards, per `app/schemas/super_admin.py`'s own
  comment) → `AdminConsoleService.get_dashboard_stats` (line 262): counts `PatientProfile`
  rows, `professionals.count_all()`, `professionals.count_pending()`, `waitlist.count_all()`,
  `contacts.count_by_status(NEW)`, and the 10 most recent `AuditLog` rows (outer-joined to
  `User` for actor name/email) mapped through `_audit_log_out`.

---

## 4. Super Admin

Backed by `app/services/super_admin_service.py` (`SuperAdminService`), a separate file from
`AdminConsoleService`, behind `app/api/v1/endpoints/super_admin.py` (all routes
`require_super_admin`):

1. **Admin account management** — `GET/POST /api/v1/admin/admins`,
   `POST /api/v1/admin/admins/{id}/suspend`. Creating an admin
   (`AdminCreateIn`: `full_name`, `email`, `password`, `role` of `ADMIN`/`SUPER_ADMIN`) hits a
   real constraint: `User.phone_number` is `NOT NULL` + unique, but the admin-creation form
   collects no phone number. `SuperAdminService._generate_placeholder_phone` synthesizes a
   unique `"9" + 9 random digits"` value to satisfy the column — flagged directly in the code
   as a gap (see Known Gaps, item 4). Suspension sets `UserStatus.SUSPENDED`.
2. **Roles/permissions** — `GET /api/v1/admin/roles` returns a static, computed
   permission-per-role projection (mirroring the frontend's hardcoded `rolesData.ts` /
   `DEFAULT_ROLE_PERMISSIONS`) — per `app/schemas/super_admin.py`'s own comment, this is "not a
   dynamic RBAC table," so there's no create/update/delete for roles.
3. **Audit log review** — `GET /api/v1/admin/audit-logs` → `SuperAdminService.list_audit_logs`.
   Unlike `AdminConsoleService._audit_log_out` (which tries to split `metadata_json` into
   `old_value`/`new_value` when it was written in that shape), this implementation always sets
   `old_value=None` — the code comment says plainly: "AuditLog has no before-state column — see
   report gap" (see Known Gaps, item 5).
4. **Platform settings** — `GET/PUT /api/v1/admin/settings` read/write a singleton
   `PlatformSettings` row: `site_name` (aliased from `platform_name`), `support_email`,
   `support_phone`, `maintenance_mode`, `registration_enabled` (aliased from
   `new_registrations_enabled`), `platform_commission_pct`. Per
   `app/schemas/super_admin.py:78-83` and `PlatformSettingsUpdateIn`
   (lines 97-109), the frontend's settings form also submits `launchDate`,
   `nurseRegistrationEnabled`, `maxLoginAttempts`, `sessionTimeout` — these are accepted on the
   input schema purely so the PUT body the frontend actually sends validates, but they have
   **no backing column on `PlatformSettings`** and are silently ignored rather than persisted
   (see Known Gaps, item 3).

---

## 5. Patient ↔ Nurse messaging

Backed by `app/services/messaging_service.py::MessagingService`. Threads are
one-per-`(patient, professional)` pair, created lazily rather than up front.

1. **Thread creation tied to a booking** —
   `POST /api/v1/messaging/threads/for-booking/{booking_id}` →
   `get_or_create_thread_for_booking` (line 107): loads the booking; requires
   `booking.professional_id` is already set (`NotFoundError("No professional assigned to this
   booking yet.")` otherwise — a thread cannot exist before dispatch has assigned someone).
   Authorization: the caller must be either `booking.patient_id` or the professional currently
   assigned to it (resolved by matching `ProfessionalProfile.id` to
   `booking.professional_id`) — anyone else gets `ForbiddenError`. The thread is then fetched
   or created via `MessageThreadRepository.get_or_create(patient_id, professional_id,
   booking_id)`.
2. **Participant authorization on every subsequent call** — `_assert_participant` (line 61):
   for a `professional`-role caller, checks their `ProfessionalProfile.id` matches
   `thread.professional_id`; for anyone else, checks `thread.patient_id == user.id`. This same
   check gates both `list_messages` and `send_message`, so a thread's two participants are the
   only two users who can ever read or post into it.
3. **List messages** — `GET /api/v1/messaging/threads/{id}/messages` →
   `list_messages` (line 75): asserts participant, paginates via
   `MessageRepository.list_for_thread`, and — as a side effect — calls
   `messages.mark_thread_read(thread_id, for_user_id=user.id)`, i.e. simply viewing a thread
   marks its messages read for that viewer.
4. **Send message** — `POST /api/v1/messaging/threads/{id}/messages` → `send_message`
   (line 95): asserts participant, inserts a `Message` (`thread_id`, `sender_id`, `body`,
   `created_at`), and bumps `thread.last_message_at`.
5. **List my threads** — `GET /api/v1/messaging/threads` → `list_threads_for_user` (line 30):
   branches on the caller's role to fetch either their professional-side or patient-side
   threads, and enriches each with an unread count and both participants' display info.

---

## 6. Nurse earnings — `ProfessionalService.get_earnings_summary`

`app/services/professional_service.py:159`, behind `GET /api/v1/professionals/me/earnings`
(`require_professional`). Boundaries:

```python
now = datetime.now(UTC)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
week_start = today_start - timedelta(days=today_start.weekday())   # Monday of the current week
month_start = today_start.replace(day=1)                            # the 1st of the current month
```

One repository call fetches every `COMPLETED` booking for the professional in the current
month (`bookings.list_completed_for_professional_between(professional_id, start=month_start,
end=now + timedelta(days=1))`); `today`/`week`/`month` are then all **filtered from that same
in-memory list** rather than three separate queries:

- `today_earnings` = sum of `professional_payout_amount` for bookings with
  `scheduled_start_at >= today_start`
- `week_earnings` = same, filtered to `>= week_start`
- `month_earnings` = sum across the whole fetched list (no further filter)
- `total_earnings` is a **separate, all-time** SQL aggregate — 
  `sum(Booking.professional_payout_amount)` where `status == COMPLETED`, unbounded by month.

**`pending_payout` derivation**:
```python
already_paid_out = sum(Payout.net_amount) for that professional  # a direct SQL aggregate
pending_payout = max(total_earnings - already_paid_out, 0)
```
It is not read off a "pending" status on any row — it's the residual of all-time completed
booking payout amounts minus everything ever recorded in `Payout.net_amount` for that
professional, floored at zero.

Two things to note as read: `completed_visits_count` is `len(month_bookings)` — i.e. scoped to
the current month only, not all-time, despite sitting alongside the all-time `total_earnings`
in the same response. The per-transaction `status` field in the `transactions` list
(`"paid"` vs `"processing"`) is a single global flag —
`"paid" if already_paid_out >= total_earnings else "processing"` — applied identically to
every listed transaction rather than computed per booking/payout.

---

## 7. Known Gaps

Every item below is called out directly in the code (a `GAP:` or `Cross-domain note:` comment,
or an equivalent gap-style comment identified while reading the surrounding service), with the
exact file:line.

1. **Vitals are stored as a JSON string, and the "shape unconfirmed" caveat is now stale.**
   `app/services/patient_service.py:150-157` (comment, `Cross-domain note:`):
   > `BookingVisit.vitals_recorded` is a free-form JSON *string* column (see
   > `app/models/booking.py`), written by the nurse-side visit-checkout flow
   > (`app/services/visit_service.py` / `app/schemas/appointment.py`'s `VitalsIn` — at the time
   > this was written that flow was mid-change and not yet persisting vitals at all, so the
   > exact JSON shape it will end up writing is unconfirmed). This parses defensively: known
   > vitals field names (in either snake_case or the frontend's camelCase) get a friendly label
   > + unit, and anything else falls back to a raw label/value pair so nothing is silently
   > dropped once that flow lands.

   As-read today, `visit_service.py::check_out` (line 93-98) *does* now write
   `vitals_recorded = json.dumps(payload.care_note.vitals.model_dump(exclude_none=True))` — so
   the "not yet persisting vitals at all" half of the comment is outdated relative to the
   current code, though the defensive/dual-casing parsing in `_get_health_summary`
   (lines 149-188) remains the right approach since `vitals_recorded` is still an unstructured
   JSON string rather than typed columns.

2. **`AuditLog` has no discrete old/new-value columns.**
   `app/services/admin_console_service.py:293-295` (`GAP:`):
   > AuditLog stores a single `metadata_json` blob rather than discrete old/new value columns.
   > When it was written as `{"old_value": ..., "new_value": ...}` we split it back out;
   > otherwise the whole blob is surfaced as newValue.

   A second, inconsistent implementation of the same read exists in
   `app/services/super_admin_service.py:221`, which always returns `old_value=None` with the
   comment "AuditLog has no before-state column — see report gap" rather than attempting the
   same old/new split `admin_console_service.py` does. The admin dashboard's recent-activity
   feed and the super-admin audit-log screen can therefore show different `oldValue`/`newValue`
   behavior for the same underlying `AuditLog` rows depending on which endpoint served them.

3. **Platform settings: several frontend fields have no backing column.**
   `app/schemas/super_admin.py:78-83` and `PlatformSettingsUpdateIn` (lines 97-109):
   > The frontend form also collects `launchDate`, `nurseRegistrationEnabled`,
   > `maxLoginAttempts` and `sessionTimeout`, none of which have a backing column on
   > `PlatformSettings` ... those are accepted on the input schema (so the PUT body the
   > frontend actually sends validates) but silently ignored rather than persisted.

4. **Admin account creation synthesizes a placeholder phone number.**
   `app/services/super_admin_service.py:112-117`:
   > Admin accounts are created by email/password (see `AdminCreateIn`) and don't collect a
   > phone number, but `User.phone_number` is NOT NULL + unique ... and this task may not
   > add/alter columns. A synthetic, clearly-marked unique value fills the column without
   > colliding with real phone numbers. Flagged as a gap in the final report.

   (`_generate_placeholder_phone` returns `"9" + 9 random digits`.)

5. **`PatientProfile` has no registration/status column.**
   `app/schemas/admin_console.py:87-89` (`GAP:`):
   > PatientProfile has no registration/status column — derived from the linked User's status
   > (active/suspended/deleted) as the closest available proxy.

6. **`ServiceAdminOut` exposes marketing-page fields the `Service` model doesn't have.**
   `app/schemas/admin_console.py:101-103` (`GAP:`):
   > shortDesc/heroImage/icon/features/seoTitle/seoDescription don't exist as columns on
   > Service — derived (shortDesc) or left null/empty (the rest).

7. **Contact-inquiry status vocabularies never converged between frontend and backend.**
   `app/schemas/admin_console.py:169-172` (`GAP:`):
   > the frontend UI (WebAdminContacts) offers NEW/READ/REPLIED/ARCHIVED, but the backend
   > ContactInquiryStatus enum (`app/core/constants.py`) is NEW/IN_PROGRESS/RESOLVED — the two
   > never migrated to the same vocabulary. Exposing the real backend enum here.

8. **Public waitlist/contact submission endpoints don't exist, though the frontend calls
   them.** Found while cross-referencing the frontend, not from an in-code comment: the public
   marketing site calls `POST /api/v1/waitlist` (`src/app/(public)/page.tsx`) and
   `POST /api/v1/contacts` (`src/app/(public)/contact/page.tsx`), but no router registered in
   `app/api/v1/api.py` exposes a public `POST /waitlist` or `POST /contacts` path — the
   `WaitlistEntry`/`ContactInquiry` tables exist (migration
   `004_frontend_schema_additions.sql`) and the admin-facing read/manage side
   (`GET /api/v1/search?entity=waitlist|contacts`, the notify/status-update endpoints) works
   against them, but nothing currently lets a public visitor create a row in either table.

9. **Response-envelope inconsistency.** Most `/api/v1/*` routes wrap their payload in
   `ApiResponse[T]` (`{success, data, meta, error}`), but several older routes
   (`app/api/v1/endpoints/bookings.py`, `visits.py`, `offers.py`, `reviews.py`, `payments.py`,
   `addresses.py`, `services.py`, `users.py`, `wallet.py`, `support.py`) return the bare
   Pydantic response model directly instead. Not flagged in the code with a `GAP:` comment, but
   worth surfacing: a frontend client written against the `ApiResponse` envelope (as
   `app/schemas/common.py`'s docstring says the frontend's `ApiResponse<T>` type expects) will
   receive a differently-shaped body from these endpoints than from the newer
   `admin`/`super_admin`/`patient`/`search`/`messaging` routes.

10. **Two duplicate nurse-KYC-queue endpoints.** Not a code comment either, but observed
    directly: `GET /api/v1/admin/professionals/pending` /
    `POST /api/v1/admin/professionals/{id}/review` (`app/api/v1/endpoints/admin.py`,
    `require_ops_or_admin`) and `GET /api/v1/search?entity=nurses` +
    `POST /api/v1/admin/nurses/{id}/approve|reject` (`require_admin`) both expose the same
    underlying `ProfessionalService.review_kyc` capability; only the latter pair has a
    confirmed frontend caller (`useNurses.ts`), suggesting the former is a superseded
    first-pass implementation still mounted in the router.
