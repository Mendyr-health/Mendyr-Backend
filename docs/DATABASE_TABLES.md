# Database Tables

A table-by-table reference of the Mendyr schema, grounded in the migration DDL
(`migrations/002_initial_schema.sql`, `003_add_super_admin_role.sql`,
`004_frontend_schema_additions.sql`) and cross-checked against `app/models/*.py` for
relationship/business-meaning context the raw DDL doesn't convey.

Conventions used throughout the schema (not repeated per table):

- Every table has a `UUID` primary key named `id` (except `platform_settings`, which uses a
  `SERIAL` singleton `id`), generated application-side (SQLAlchemy `UUIDPKMixin`), not by a
  DB default.
- Most tables have `created_at`/`updated_at` (`TIMESTAMP WITH TIME ZONE`, both
  `DEFAULT now()`, `NOT NULL`) via the `TimestampMixin`. Tables without an `updated_at` are
  effectively append-only/event-log tables (e.g. `booking_status_history`, `reviews`,
  `wallet_transactions`).
- Geospatial columns use PostGIS `geography(POINT,4326)` (lon/lat, WGS84), each backed by a
  GiST index for radius/distance queries.
- Enums are native Postgres `ENUM` types (listed inline per column).

---

## Users & Auth

### `users`

Every account on the platform — patients, professionals, admins, and (as of migration 003)
super admins — one row per person regardless of role.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `phone_number` | VARCHAR(15) | NO | unique (`ix_users_phone_number`), primary login identifier |
| `phone_verified` | BOOLEAN | NO | |
| `email` | VARCHAR(255) | YES | unique (`uq_users_email`) |
| `email_verified` | BOOLEAN | NO | |
| `hashed_password` | VARCHAR(255) | YES | optional — phone OTP is the primary auth method |
| `full_name` | VARCHAR(150) | NO | |
| `gender` | ENUM `gender` (`male`,`female`,`other`,`unspecified`) | NO | |
| `date_of_birth` | TIMESTAMP WITH TIME ZONE | YES | |
| `avatar_url` | VARCHAR(500) | YES | |
| `role` | ENUM `user_role` (`patient`,`professional`,`admin`,`ops`,`super_admin`*) | NO | *`super_admin` added by migration 003 for the Next.js admin console |
| `status` | ENUM `user_status` (`active`,`suspended`,`deleted`) | NO | |
| `referral_code` | VARCHAR(12) | NO | unique (`uq_users_referral_code`) |
| `referred_by_id` | UUID | YES | FK → `users.id` (self-referential) |
| `last_login_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | YES | soft-delete marker (`SoftDeleteMixin`) |

- **PK:** `id`
- **FK:** `referred_by_id` → `users.id`
- **Indexes:** unique on `phone_number`; `ix_users_role_status` on `(role, status)`
- **Relates to:** `patient_profiles`, `professional_profiles`, `addresses`, `device_tokens`
  (all 1:1 or 1:N, cascade-deleted), plus as an actor/FK target from `bookings`,
  `payments`, `reviews`, `support_tickets`, `audit_logs`, `notifications`, `messages`,
  `coupon_redemptions`, `wallet_transactions` (indirectly via `wallets`), and
  `booking_status_history`.

### `otp_verifications`

Phone OTP challenges for login/registration/verification flows; not tied to a `users` row by
FK (looked up by phone number so an OTP can be issued before an account exists).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `phone_number` | VARCHAR(15) | NO | indexed |
| `purpose` | VARCHAR(30) | NO | e.g. login, registration |
| `hashed_code` | VARCHAR(255) | NO | OTP stored hashed, never plaintext |
| `attempts` | INTEGER | NO | |
| `max_attempts` | INTEGER | NO | |
| `verified` | BOOLEAN | NO | |
| `expires_at` | TIMESTAMP WITH TIME ZONE | NO | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Indexes:** `ix_otp_phone_purpose` on `(phone_number, purpose)`; `ix_otp_verifications_phone_number` on `phone_number`
- **Relates to:** `users` indirectly (by phone number, not FK)

### `device_tokens`

Push-notification device registrations for a user (one row per device/app install).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE` |
| `platform` | ENUM `device_platform` (`android`,`ios`,`web`) | NO | |
| `push_token` | VARCHAR(500) | NO | |
| `app_version` | VARCHAR(20) | YES | |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `user_id` → `users.id`
- **Indexes:** unique `uq_device_tokens_user_token` on `(user_id, push_token)`
- **Relates to:** `users` (many devices per user)

---

## Patients

### `patient_profiles`

The patient-specific profile extending a `users` row (1:1).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE`, unique (1:1) |
| `known_conditions` | VARCHAR(100)[] | YES | |
| `allergies` | VARCHAR(100)[] | YES | |
| `current_medications` | TEXT | YES | |
| `emergency_contact_name` | VARCHAR(150) | YES | |
| `emergency_contact_phone` | VARCHAR(15) | YES | |
| `emergency_contact_relationship` | VARCHAR(100) | YES | added by migration 004 |
| `preferred_language` | VARCHAR(50) | YES | |
| `notes` | TEXT | YES | |
| `date_of_birth` | TIMESTAMP WITHOUT TIME ZONE | YES | separate from `users.date_of_birth`; no timezone |
| `address_line` | TEXT | YES | added by migration 004 (free-text registration address) |
| `city` | VARCHAR(100) | YES | added by migration 004 |
| `state` | VARCHAR(100) | YES | added by migration 004 |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `user_id` → `users.id` (unique — 1:1)
- **Relates to:** `users` (1:1), `care_plans` (as `patient_id` → `users.id`, not this table),
  `bookings` (as `patient_id` → `users.id`), `message_threads` (as `patient_id`)

---

## Professionals / Nurses

### `professional_profiles`

The professional-specific profile extending a `users` row (1:1) — nurses, physiotherapists,
caretakers, lab technicians, doctors, and baby-care specialists all share this one table,
distinguished by `professional_type`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE`, unique (1:1) |
| `professional_type` | ENUM `professional_type` (`nurse`,`physiotherapist`,`caretaker`,`lab_technician`,`doctor`,`baby_care_specialist`) | NO | |
| `years_of_experience` | SMALLINT | NO | |
| `bio` | TEXT | YES | |
| `license_number` | VARCHAR(100) | YES | |
| `council_registration_number` | VARCHAR(100) | YES | |
| `languages_spoken` | VARCHAR(50)[] | YES | |
| `verification_status` | ENUM `verification_status` (`pending`,`in_review`,`approved`,`rejected`) | NO | shared enum, also used by `professional_documents` |
| `verified_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `rejection_reason` | VARCHAR(500) | YES | |
| `availability_status` | ENUM `availability_status` (`offline`,`online`,`on_visit`,`break`) | NO | |
| `current_location` | geography(POINT,4326) | YES | live location for dispatch matching |
| `location_updated_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `base_service_radius_km` | NUMERIC(5,2) | NO | |
| `average_rating` | NUMERIC(3,2) | NO | denormalized from `reviews` |
| `total_ratings` | INTEGER | NO | denormalized |
| `total_visits_completed` | INTEGER | NO | denormalized |
| `bank_account_number` | VARCHAR(50) | YES | payout details |
| `bank_ifsc` | VARCHAR(15) | YES | |
| `bank_account_holder_name` | VARCHAR(150) | YES | |
| `upi_id` | VARCHAR(100) | YES | |
| `is_accepting_bookings` | BOOLEAN | NO | |
| `experience_description` | TEXT | YES | added by migration 004 |
| `qualifications` | TEXT | YES | added by migration 004 |
| `certifications` | TEXT | YES | added by migration 004 |
| `preferred_contact` | ENUM `preferred_contact_method` (`email`,`phone`,`whatsapp`) | NO, default `'email'` | added by migration 004 |
| `address_line` | TEXT | YES | added by migration 004 |
| `city` | VARCHAR(100) | YES | added by migration 004 |
| `state` | VARCHAR(100) | YES | added by migration 004 |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `user_id` → `users.id` (unique — 1:1)
- **Indexes:** `ix_professional_current_location` (GiST, for radius search);
  `ix_professional_type_status` on `(professional_type, verification_status)`
- **Relates to:** `users` (1:1), `professional_documents`, `professional_specializations`,
  `professional_availability_slots`, `professional_services` (all 1:N, cascade-deleted),
  `bookings`/`booking_offers`/`care_plans`/`payouts`/`message_threads` (as the professional
  side of those relationships)

### `professional_documents`

KYC / verification documents uploaded by a professional.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `professional_id` | UUID | NO | FK → `professional_profiles.id`, `ON DELETE CASCADE` |
| `document_type` | ENUM `document_type` (`government_id`,`nursing_council_certificate`,`degree_certificate`,`police_verification`,`profile_photo`,`address_proof`) | NO | |
| `file_url` | VARCHAR(500) | NO | |
| `verification_status` | ENUM `verification_status` | NO | |
| `reviewed_by_id` | UUID | YES | FK → `users.id` (the reviewing admin) |
| `reviewed_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `rejection_reason` | VARCHAR(500) | YES | |
| `expires_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `professional_id` → `professional_profiles.id`; `reviewed_by_id` → `users.id`
- **Relates to:** `professional_profiles` (N:1), `users` (reviewer)

### `specializations`

Reference list of clinical specializations (e.g. wound care, geriatric care).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `name` | VARCHAR(150) | NO | unique (`uq_specializations_name`) |
| `description` | VARCHAR(500) | YES | |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Relates to:** `professional_specializations` (N:M join to `professional_profiles`)

### `professional_specializations`

Join table: which specializations a professional holds, with years of experience in each.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `professional_id` | UUID | NO | FK → `professional_profiles.id`, `ON DELETE CASCADE` |
| `specialization_id` | UUID | NO | FK → `specializations.id`, `ON DELETE CASCADE` |
| `years_of_experience` | SMALLINT | NO | |

- **PK:** `id`
- **Indexes:** unique `uq_professional_specialization` on `(professional_id, specialization_id)`
- **Relates to:** `professional_profiles`, `specializations` (N:M join)

### `professional_availability_slots`

Weekly recurring availability windows a professional sets for themselves.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `professional_id` | UUID | NO | FK → `professional_profiles.id`, `ON DELETE CASCADE` |
| `day_of_week` | SMALLINT | NO | |
| `start_time` | TIME WITHOUT TIME ZONE | NO | |
| `end_time` | TIME WITHOUT TIME ZONE | NO | |
| `is_active` | BOOLEAN | NO | |

- **PK:** `id`
- **Indexes:** `ix_availability_professional_day` on `(professional_id, day_of_week)`
- **Relates to:** `professional_profiles` (N:1)

---

## Services & Categories

### `service_categories`

Top-level grouping for services (e.g. "Nursing Care", "Physiotherapy").

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `name` | VARCHAR(150) | NO | unique |
| `slug` | VARCHAR(150) | NO | unique |
| `description` | VARCHAR(500) | YES | |
| `icon_url` | VARCHAR(500) | YES | |
| `display_order` | SMALLINT | NO | |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Relates to:** `services` (1:N, cascade-deleted)

### `services`

A bookable service offering (e.g. "Post-surgical wound dressing").

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `category_id` | UUID | NO | FK → `service_categories.id`, `ON DELETE CASCADE` |
| `name` | VARCHAR(200) | NO | |
| `slug` | VARCHAR(200) | NO | unique |
| `description` | TEXT | YES | |
| `required_professional_type` | ENUM `professional_type` | NO | which professional type can fulfil this service |
| `duration_minutes` | INTEGER | NO | |
| `base_price` | NUMERIC(10,2) | NO | |
| `is_recurring_eligible` | BOOLEAN | NO | can be used in a `care_plans` recurring booking |
| `requires_prescription` | BOOLEAN | NO | |
| `is_active` | BOOLEAN | NO | |
| `display_order` | SMALLINT | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `category_id` → `service_categories.id`
- **Relates to:** `service_categories` (N:1), `professional_services` (1:N),
  `bookings`/`care_plans` (as `service_id`)

### `professional_services`

Join table: which services a professional offers, with an optional per-professional price
override.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `professional_id` | UUID | NO | FK → `professional_profiles.id`, `ON DELETE CASCADE` |
| `service_id` | UUID | NO | FK → `services.id`, `ON DELETE CASCADE` |
| `price_override` | NUMERIC(10,2) | YES | overrides `services.base_price` when set |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Indexes:** unique `uq_professional_service` on `(professional_id, service_id)`
- **Relates to:** `professional_profiles`, `services` (N:M join)

---

## Bookings & Visits

### `addresses`

Saved addresses for a user (patient), including a geocoded point used for booking dispatch.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE` |
| `label` | VARCHAR(30) | NO | e.g. "Home", "Work" |
| `line1` | VARCHAR(255) | NO | |
| `line2` | VARCHAR(255) | YES | |
| `landmark` | VARCHAR(255) | YES | |
| `city` | VARCHAR(100) | NO | |
| `state` | VARCHAR(100) | NO | |
| `pincode` | VARCHAR(10) | NO | |
| `country` | VARCHAR(2) | NO | ISO code |
| `location` | geography(POINT,4326) | NO | |
| `is_default` | BOOLEAN | NO | |
| `contact_name` | VARCHAR(150) | YES | |
| `contact_phone` | VARCHAR(15) | YES | |
| `instructions_for_professional` | VARCHAR(500) | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `user_id` → `users.id`
- **Indexes:** `ix_addresses_location` (GiST); `ix_addresses_user_id`
- **Relates to:** `users` (N:1), `care_plans`/`bookings` (as `address_id`)

### `care_plans`

A recurring booking arrangement (e.g. "daily physio visits for 2 weeks") that generates
multiple `bookings`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `patient_id` | UUID | NO | FK → `users.id` |
| `service_id` | UUID | NO | FK → `services.id` |
| `address_id` | UUID | NO | FK → `addresses.id` |
| `total_visits` | SMALLINT | NO | |
| `visits_per_day` | SMALLINT | NO | |
| `start_date` / `end_date` | TIMESTAMP WITH TIME ZONE | NO | |
| `preferred_professional_id` | UUID | YES | FK → `professional_profiles.id` |
| `notes` | TEXT | YES | |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `patient_id` → `users.id`; `service_id` → `services.id`; `address_id` →
  `addresses.id`; `preferred_professional_id` → `professional_profiles.id`
- **Relates to:** `bookings` (1:N — each generated visit is a `booking` row with
  `care_plan_id` set)

### `bookings`

The central transactional entity: one scheduled/completed/cancelled service appointment.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_code` | VARCHAR(20) | NO | unique, human-facing reference |
| `patient_id` | UUID | NO | FK → `users.id` |
| `professional_id` | UUID | YES | FK → `professional_profiles.id`; null until assigned |
| `service_id` | UUID | NO | FK → `services.id` |
| `address_id` | UUID | NO | FK → `addresses.id` |
| `care_plan_id` | UUID | YES | FK → `care_plans.id`, set for recurring-plan visits |
| `booking_type` | ENUM `booking_type` (`one_time`,`care_plan`) | NO | |
| `status` | ENUM `booking_status` (`created`,`searching`,`assigned`,`confirmed`,`en_route`,`in_progress`,`completed`,`cancelled`,`no_show`,`failed`) | NO | |
| `required_professional_type` | ENUM `professional_type` | NO | |
| `scheduled_start_at` / `scheduled_end_at` | TIMESTAMP WITH TIME ZONE | NO | |
| `service_name_snapshot` | VARCHAR(200) | NO | denormalized at booking time |
| `address_snapshot` | TEXT | NO | denormalized at booking time |
| `service_location` | geography(POINT,4326) | NO | |
| `base_price` / `discount_amount` / `platform_fee` / `tax_amount` / `total_amount` / `professional_payout_amount` | NUMERIC(10,2) | NO | pricing breakdown, all snapshotted |
| `commission_pct` | NUMERIC(5,2) | NO | |
| `coupon_id` | UUID | YES | FK → `coupons.id` |
| `patient_notes` | TEXT | YES | |
| `cancellation_reason` | VARCHAR(500) | YES | |
| `cancelled_by_id` | UUID | YES | FK → `users.id` |
| `cancelled_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `cancellation_fee_amount` | NUMERIC(10,2) | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `patient_id`, `cancelled_by_id` → `users.id`; `professional_id` →
  `professional_profiles.id`; `service_id` → `services.id`; `address_id` → `addresses.id`;
  `care_plan_id` → `care_plans.id`; `coupon_id` → `coupons.id`
- **Indexes:** `ix_bookings_patient_status` on `(patient_id, status)`;
  `ix_bookings_professional_status` on `(professional_id, status)`;
  `ix_bookings_scheduled_start` on `scheduled_start_at`
- **Relates to:** `booking_offers`, `booking_status_history`, `booking_visits` (1:1),
  `visit_tracking_pings`, `payments`, `reviews`, `coupon_redemptions`, `support_tickets`,
  `wallet_transactions` (via `reference_booking_id`), `message_threads`

### `booking_offers`

Dispatch offers sent to nearby professionals for a `searching` booking — the matching/offer
round mechanism (each round widens the search radius).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE` |
| `professional_id` | UUID | NO | FK → `professional_profiles.id` |
| `round_number` | SMALLINT | NO | |
| `distance_meters` | INTEGER | NO | |
| `status` | ENUM `offer_status` (`pending`,`accepted`,`rejected`,`expired`,`cancelled`) | NO | |
| `expires_at` | TIMESTAMP WITH TIME ZONE | NO | |
| `responded_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id`; `professional_id` → `professional_profiles.id`
- **Indexes:** `ix_offers_booking_round` on `(booking_id, round_number)`;
  `ix_offers_professional_status` on `(professional_id, status)`
- **Relates to:** `bookings` (N:1), `professional_profiles` (N:1)

### `booking_status_history`

Append-only audit trail of every status transition a booking goes through.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE` |
| `from_status` | ENUM `booking_status` | YES | null for the initial transition |
| `to_status` | ENUM `booking_status` | NO | |
| `changed_by_id` | UUID | YES | FK → `users.id` |
| `reason` | VARCHAR(500) | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id`; `changed_by_id` → `users.id`
- **Relates to:** `bookings` (N:1)

### `booking_visits`

The clinical visit record for a booking — check-in/check-out, location proof, and visit
notes (1:1 with `bookings`).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE`, unique (1:1) |
| `en_route_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `checked_in_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `checked_in_location` | geography(POINT,4326) | YES | |
| `checked_in_distance_meters` | INTEGER | YES | distance from the address at check-in, for geofence validation |
| `checked_out_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `checked_out_location` | geography(POINT,4326) | YES | |
| `visit_summary_notes` | TEXT | YES | |
| `vitals_recorded` | TEXT | YES | |
| `proof_of_visit_photo_url` | VARCHAR(500) | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id` (unique — 1:1)
- **Relates to:** `bookings` (1:1)

### `visit_tracking_pings`

Raw GPS pings emitted during a visit's lifecycle (en route / check-in / check-out) — the
detail feed behind `booking_visits`' summary fields.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE` |
| `event` | ENUM `visit_event` (`en_route`,`checked_in`,`checked_out`) | NO | |
| `location` | geography(POINT,4326) | NO | |
| `recorded_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id`
- **Indexes:** `ix_tracking_booking_time` on `(booking_id, recorded_at)`
- **Relates to:** `bookings` (N:1)

---

## Payments & Wallet

### `payments`

A payment attempt/transaction against a booking, via a payment gateway (Razorpay).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE` |
| `patient_id` | UUID | NO | FK → `users.id` |
| `provider` | VARCHAR(30) | NO | e.g. "razorpay" |
| `provider_order_id` | VARCHAR(100) | YES | indexed |
| `provider_payment_id` | VARCHAR(100) | YES | indexed |
| `provider_signature` | VARCHAR(255) | YES | webhook signature, for verification |
| `method` | ENUM `payment_method` (`upi`,`card`,`netbanking`,`wallet`,`cash`) | YES | |
| `status` | ENUM `payment_status` (`pending`,`authorized`,`captured`,`failed`,`refunded`,`partially_refunded`) | NO | |
| `amount` | NUMERIC(10,2) | NO | |
| `amount_refunded` | NUMERIC(10,2) | NO | |
| `currency` | VARCHAR(3) | NO | |
| `failure_reason` | VARCHAR(500) | YES | |
| `captured_at` / `refunded_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `raw_webhook_payload` | TEXT | YES | full webhook body for audit/debugging |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id`; `patient_id` → `users.id`
- **Indexes:** `ix_payments_booking_id`; `ix_payments_provider_order_id`;
  `ix_payments_provider_payment_id`
- **Relates to:** `bookings` (N:1), `users` (N:1)

### `payouts`

A periodic (e.g. weekly) payout batch to a professional, aggregating completed visits.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `professional_id` | UUID | NO | FK → `professional_profiles.id` |
| `period_start` / `period_end` | TIMESTAMP WITH TIME ZONE | NO | |
| `total_visits` | INTEGER | NO | |
| `gross_amount` / `commission_deducted` / `adjustments` / `net_amount` | NUMERIC(10,2) | NO | |
| `status` | ENUM `payout_status` (`pending`,`processing`,`paid`,`failed`) | NO | |
| `provider_reference_id` | VARCHAR(100) | YES | |
| `failure_reason` | VARCHAR(500) | YES | |
| `paid_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `professional_id` → `professional_profiles.id`
- **Indexes:** `ix_payouts_professional_id`
- **Relates to:** `professional_profiles` (N:1)

### `wallets`

A user's platform wallet (referral credits, refunds, etc.) — 1:1 with `users`.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE`, unique (1:1) |
| `balance` | NUMERIC(10,2) | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `user_id` → `users.id` (unique — 1:1)
- **Relates to:** `wallet_transactions` (1:N, cascade-deleted)

### `wallet_transactions`

Append-only ledger of every credit/debit against a wallet.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `wallet_id` | UUID | NO | FK → `wallets.id`, `ON DELETE CASCADE` |
| `txn_type` | ENUM `wallet_txn_type` (`credit`,`debit`) | NO | |
| `reason` | ENUM `wallet_txn_reason` (`referral_bonus`,`cancellation_refund`,`booking_payment`,`payout`,`adjustment`,`promotion`) | NO | |
| `amount` | NUMERIC(10,2) | NO | |
| `balance_after` | NUMERIC(10,2) | NO | running balance snapshot |
| `reference_booking_id` | UUID | YES | FK → `bookings.id` |
| `description` | VARCHAR(255) | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only ledger |

- **PK:** `id`
- **FK:** `wallet_id` → `wallets.id`; `reference_booking_id` → `bookings.id`
- **Relates to:** `wallets` (N:1), `bookings` (N:1, optional)

### `coupons`

Discount codes applicable to bookings.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `code` | VARCHAR(30) | NO | unique |
| `description` | VARCHAR(255) | YES | |
| `discount_type` | ENUM `coupon_discount_type` (`flat`,`percentage`) | NO | |
| `discount_value` | NUMERIC(10,2) | NO | |
| `max_discount_amount` | NUMERIC(10,2) | YES | caps a percentage discount |
| `min_order_amount` | NUMERIC(10,2) | NO | |
| `max_redemptions_total` | INTEGER | YES | |
| `max_redemptions_per_user` | SMALLINT | NO | |
| `valid_from` / `valid_until` | TIMESTAMP WITH TIME ZONE | NO | |
| `is_active` | BOOLEAN | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Indexes:** unique on `code`
- **Relates to:** `bookings` (as `coupon_id`), `coupon_redemptions` (1:N, cascade-deleted)

### `coupon_redemptions`

Records each time a coupon is used on a booking, enforcing per-coupon-per-booking
uniqueness.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `coupon_id` | UUID | NO | FK → `coupons.id`, `ON DELETE CASCADE` |
| `user_id` | UUID | NO | FK → `users.id` |
| `booking_id` | UUID | NO | FK → `bookings.id` |
| `discount_applied` | NUMERIC(10,2) | NO | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only |

- **PK:** `id`
- **FK:** `coupon_id` → `coupons.id`; `user_id` → `users.id`; `booking_id` → `bookings.id`
- **Indexes:** unique `uq_coupon_booking` on `(coupon_id, booking_id)`
- **Relates to:** `coupons`, `users`, `bookings`

---

## Reviews & Support

### `reviews`

A rating/review left by one party about the other after a booking (patient↔professional,
either direction).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `booking_id` | UUID | NO | FK → `bookings.id`, `ON DELETE CASCADE` |
| `reviewer_id` | UUID | NO | FK → `users.id` |
| `reviewee_id` | UUID | NO | FK → `users.id` |
| `rating` | SMALLINT | NO | `CHECK (rating BETWEEN 1 AND 5)` |
| `comment` | VARCHAR(1000) | YES | |
| `tags` | VARCHAR(50)[] | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — reviews are immutable once created |

- **PK:** `id`
- **FK:** `booking_id` → `bookings.id`; `reviewer_id`, `reviewee_id` → `users.id`
- **Indexes:** unique `uq_review_booking_reviewer` on `(booking_id, reviewer_id)` — one
  review per reviewer per booking
- **Relates to:** `bookings` (N:1), `users` (reviewer and reviewee)
- Feeds the denormalized `average_rating`/`total_ratings` on `professional_profiles`.

### `support_tickets`

A customer-support ticket, optionally tied to a specific booking.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `raised_by_id` | UUID | NO | FK → `users.id` |
| `booking_id` | UUID | YES | FK → `bookings.id` |
| `assigned_to_id` | UUID | YES | FK → `users.id` (support agent/admin) |
| `subject` | VARCHAR(255) | NO | |
| `category` | VARCHAR(50) | NO | |
| `priority` | ENUM `support_ticket_priority` (`low`,`medium`,`high`,`urgent`) | NO | |
| `status` | ENUM `support_ticket_status` (`open`,`in_progress`,`resolved`,`closed`) | NO | |
| `resolved_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `raised_by_id`, `assigned_to_id` → `users.id`; `booking_id` → `bookings.id`
- **Relates to:** `users` (raiser and assignee), `bookings` (optional), `support_ticket_messages` (1:N, cascade-deleted)

### `support_ticket_messages`

The message thread within a support ticket.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `ticket_id` | UUID | NO | FK → `support_tickets.id`, `ON DELETE CASCADE` |
| `sender_id` | UUID | NO | FK → `users.id` |
| `message` | TEXT | NO | |
| `attachment_url` | VARCHAR(500) | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only |

- **PK:** `id`
- **FK:** `ticket_id` → `support_tickets.id`; `sender_id` → `users.id`
- **Relates to:** `support_tickets` (N:1), `users` (N:1)

---

## Messaging

### `message_threads`

A conversation thread between a patient and a professional, optionally scoped to a specific
booking (added by migration 004 for the frontend's patient↔nurse messaging screens).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `patient_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE` |
| `professional_id` | UUID | NO | FK → `professional_profiles.id`, `ON DELETE CASCADE` |
| `booking_id` | UUID | YES | FK → `bookings.id` |
| `last_message_at` | TIMESTAMP WITH TIME ZONE | YES | denormalized, for inbox sorting |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **FK:** `patient_id` → `users.id`; `professional_id` → `professional_profiles.id`;
  `booking_id` → `bookings.id`
- **Indexes:** `ix_message_threads_patient`; `ix_message_threads_professional`
- **Relates to:** `users`, `professional_profiles`, `bookings` (optional), `messages` (1:N, cascade-deleted)

### `messages`

An individual message within a `message_threads` conversation.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `thread_id` | UUID | NO | FK → `message_threads.id`, `ON DELETE CASCADE` |
| `sender_id` | UUID | NO | FK → `users.id` |
| `body` | TEXT | NO | |
| `read_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `is_read` | BOOLEAN | NO | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — messages are immutable |

- **PK:** `id`
- **FK:** `thread_id` → `message_threads.id`; `sender_id` → `users.id`
- **Indexes:** `ix_messages_thread_created` on `(thread_id, created_at)`
- **Relates to:** `message_threads` (N:1), `users` (sender)

---

## Admin / Platform

### `audit_logs`

Append-only record of actions taken across the platform, for admin/compliance review.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `actor_id` | UUID | YES | FK → `users.id`; null for system-initiated actions |
| `action` | VARCHAR(100) | NO | |
| `entity_type` | VARCHAR(100) | NO | |
| `entity_id` | VARCHAR(100) | NO | stored as text, not FK'd (polymorphic target) |
| `metadata_json` | TEXT | YES | |
| `ip_address` | VARCHAR(45) | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` — append-only |

- **PK:** `id`
- **FK:** `actor_id` → `users.id`
- **Relates to:** `users` (actor); `entity_type`/`entity_id` reference other tables
  polymorphically, not via FK

### `platform_settings`

Singleton row of global platform configuration for the Super Admin console (migration 004).
Seeded with exactly one row (`id = 1`, `platform_name = 'Mendyr'`).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | SERIAL | NO | PK — only row `1` is expected to exist |
| `platform_name` | VARCHAR(100) | NO | |
| `support_email` | VARCHAR(255) | YES | |
| `support_phone` | VARCHAR(15) | YES | |
| `maintenance_mode` | BOOLEAN | NO | |
| `new_registrations_enabled` | BOOLEAN | NO | |
| `platform_commission_pct` | NUMERIC(5,2) | NO | default commission applied to bookings |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id` (SERIAL, not UUID — the one exception in the schema)
- **Relates to:** none by FK; read/written by the Super Admin settings screens

### `notifications`

A notification sent (or queued) to a user across a channel (push/SMS/email/in-app).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `user_id` | UUID | NO | FK → `users.id`, `ON DELETE CASCADE` |
| `channel` | ENUM `notification_channel` (`push`,`sms`,`email`,`in_app`) | NO | |
| `template_key` | VARCHAR(100) | NO | |
| `title` | VARCHAR(200) | YES | |
| `body` | TEXT | NO | |
| `data` | TEXT | YES | arbitrary JSON payload, stored as text |
| `status` | ENUM `notification_status` (`queued`,`sent`,`failed`) | NO | |
| `failure_reason` | VARCHAR(500) | YES | |
| `sent_at` / `read_at` | TIMESTAMP WITH TIME ZONE | YES | |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | no `updated_at` |

- **PK:** `id`
- **FK:** `user_id` → `users.id`
- **Indexes:** `ix_notifications_user_id`
- **Relates to:** `users` (N:1)

---

## Waitlist & Contact

### `waitlist_entries`

Pre-launch/marketing waitlist signups from the public site (migration 004).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `email` | VARCHAR(255) | NO | unique |
| `name` | VARCHAR(150) | YES | |
| `phone` | VARCHAR(15) | YES | |
| `source` | VARCHAR(50) | YES | e.g. which page/campaign |
| `notified` | BOOLEAN | NO | whether a launch notification has been sent |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Indexes:** unique + `ix_waitlist_entries_email` on `email`
- **Relates to:** none by FK — standalone marketing table

### `contact_inquiries`

Submissions from the public "Contact Us" form (migration 004).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID | NO | PK |
| `name` | VARCHAR(100) | NO | |
| `email` | VARCHAR(255) | NO | indexed |
| `phone` | VARCHAR(15) | YES | |
| `subject` | VARCHAR(200) | NO | |
| `message` | TEXT | NO | |
| `status` | ENUM `contact_inquiry_status` (`new`,`in_progress`,`resolved`) | NO | |
| `created_at` / `updated_at` | TIMESTAMP WITH TIME ZONE | NO | |

- **PK:** `id`
- **Indexes:** `ix_contact_inquiries_email`
- **Relates to:** none by FK — standalone table, triaged by admins

---

## Enum reference

For quick lookup, every native Postgres enum type defined across the three migrations:

| Enum | Values | Used by |
|---|---|---|
| `coupon_discount_type` | flat, percentage | `coupons` |
| `gender` | male, female, other, unspecified | `users` |
| `user_role` | patient, professional, admin, ops, **super_admin** (migration 003) | `users` |
| `user_status` | active, suspended, deleted | `users` |
| `device_platform` | android, ios, web | `device_tokens` |
| `notification_channel` | push, sms, email, in_app | `notifications` |
| `notification_status` | queued, sent, failed | `notifications` |
| `professional_type` | nurse, physiotherapist, caretaker, lab_technician, doctor, baby_care_specialist | `professional_profiles`, `services`, `bookings` |
| `verification_status` | pending, in_review, approved, rejected | `professional_profiles`, `professional_documents` |
| `availability_status` | offline, online, on_visit, break | `professional_profiles` |
| `payout_status` | pending, processing, paid, failed | `payouts` |
| `document_type` | government_id, nursing_council_certificate, degree_certificate, police_verification, profile_photo, address_proof | `professional_documents` |
| `booking_type` | one_time, care_plan | `bookings` |
| `booking_status` | created, searching, assigned, confirmed, en_route, in_progress, completed, cancelled, no_show, failed | `bookings`, `booking_status_history` |
| `offer_status` | pending, accepted, rejected, expired, cancelled | `booking_offers` |
| `payment_method` | upi, card, netbanking, wallet, cash | `payments` |
| `payment_status` | pending, authorized, captured, failed, refunded, partially_refunded | `payments` |
| `support_ticket_priority` | low, medium, high, urgent | `support_tickets` |
| `support_ticket_status` | open, in_progress, resolved, closed | `support_tickets` |
| `visit_event` | en_route, checked_in, checked_out | `visit_tracking_pings` |
| `wallet_txn_type` | credit, debit | `wallet_transactions` |
| `wallet_txn_reason` | referral_bonus, cancellation_refund, booking_payment, payout, adjustment, promotion | `wallet_transactions` |
| `preferred_contact_method` (migration 004) | email, phone, whatsapp | `professional_profiles` |
| `contact_inquiry_status` (migration 004) | new, in_progress, resolved | `contact_inquiries` |
