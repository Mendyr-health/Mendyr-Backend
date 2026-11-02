# Staff roles: super admin, admin and ops

Mendyr has three staff roles that can sign in to the **config portal**. Patients and
professionals can't — the portal shows "Admins only" and every admin API returns `403`.

| Role | In one line |
|---|---|
| **super_admin** | Everything an admin can do, plus managing other admins. |
| **admin** | Runs the platform: verifies professionals, changes app settings, edits the catalogue, suspends users. |
| **ops** | Day-to-day operations: sees everything, handles bookings, but can't change policy or approve anyone. |

The backend enforces all of this on every request (`app/core/permissions.py`), so hiding a
button in the portal is only a convenience — an ops user calling an admin API directly still
gets `403`.

---

## What each role can do

✅ = allowed · ❌ = not allowed (hidden in the portal, `403` from the API)

### Overview & reporting
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| See the overview dashboard (KPIs, GMV, fill rate, charts) | ✅ | ✅ | ✅ |
| See the activity log (who did what) | ✅ | ✅ | ✅ |
| Create, edit, delete and **run** saved SQL queries (Queries page) | ✅ | ✅ | ❌ |

### Professional verification
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| See the verification queue, stats and every professional's profile | ✅ | ✅ | ✅ |
| View their uploaded documents (ID, certificates…) | ✅ | ✅ | ✅ |
| **Approve / reject / mark in review** a professional | ✅ | ✅ | ❌ |
| Approve or reject **individual documents** | ✅ | ✅ | ❌ |
| Delete a professional's document | ✅ | ✅ | ❌ |

### Bookings
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| Search and view bookings (timeline, people, price, notes, vitals, attached prescriptions) | ✅ | ✅ | ✅ |
| **Cancel** a booking for the patient (no cancellation fee; both sides notified) | ✅ | ✅ | ✅ |
| **Reopen** a booking (take it off the assigned professional, back on the board) | ✅ | ✅ | ✅ |

### Users
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| Search and view users (patients, professionals, staff) | ✅ | ✅ | ✅ |
| **Suspend / reactivate** a patient or professional | ✅ | ✅ | ❌ |
| **Suspend / reactivate** an admin or super admin | ✅ | ❌ | ❌ |
| Change your own account status | ❌ | ❌ | ❌ |

Suspending signs the person out everywhere immediately and, for a professional, stops new
requests reaching them.

### Catalogue
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| See categories and services | ✅ | ✅ | ✅ |
| Create / edit categories and services (price, duration, images, what's included, FAQs) | ✅ | ✅ | ❌ |

### App Config (what the apps show and how the business runs)
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| See App Config | ✅ | ✅ | ❌ |
| Change feature flags, theme, home layout, banners, onboarding, app text (English/Hindi), support & SOS numbers | ✅ | ✅ | ❌ |
| Change booking rules (slots, lead time, travel buffer, cancellation window & fee) and cancel reasons | ✅ | ✅ | ❌ |
| Change pricing (commission %, GST %) | ✅ | ✅ | ❌ |
| Change verification policy (auto-approve on/off) and privacy rules | ✅ | ✅ | ❌ |
| Maintenance mode, minimum app version / force update | ✅ | ✅ | ❌ |
| Reset a setting to its default | ✅ | ✅ | ❌ |

### Support tickets
| Action | Super admin | Admin | Ops |
|---|:-:|:-:|:-:|
| Reply to any patient's or professional's support ticket | ✅ | ✅ | ✅ |

---

## Things every staff role shares
- Every change (approvals, rejections, suspensions, config saves, cancellations, document
  reviews) is written to the **activity log** with who did it and when.
- Staff can't sign up in the app. Accounts are created by a super admin/admin — see below.
- Staff accounts opening the patient/professional app see "Use the admin portal".

## Super admin vs admin today
They have the same access except one thing: **only a super admin can suspend or reactivate
another admin or super admin.** Use `super_admin` for the founders/owners and `admin` for
everyone else who runs the platform. If more owner-only powers are needed later (e.g. pricing
or creating staff accounts from the portal), they go behind `super_admin`.

---

## Giving someone a staff role

**GitHub Actions → "Manage admin/user accounts" → Run workflow**

| Field | What to enter |
|---|---|
| mode | `promote` (they already have an app account) or `create` (new account) |
| role | `super_admin`, `admin` or `ops` |
| email | their email |
| full_name, phone_number | only for `create` |

- `create` prints a one-time password in the job log — copy it straight away and share it
  privately.
- To remove staff access: suspend them from the portal's Users page (super admin for admins),
  or run the workflow in `delete` mode.

Locally (with `POSTGRES_*` pointing at the right database):
```bash
uv run python -m scripts.create_admin promote --email person@example.com --role ops
```

## Resetting a password

**GitHub Actions → "Reset user password" → Run workflow** — enter one or more emails
(comma-separated). Each account gets a new random password printed once in the run log, all
its sessions are signed out, and the reset is logged. Works for patients, professionals,
admins and ops; **super admin accounts are always skipped**. Tick "dry run" to check the
emails first. Locally: `uv run python -m scripts.reset_password --users "a@x.com, b@y.com"`.

## Where this lives in code
- Role guards: `app/core/permissions.py` (`require_admin` = admin + super_admin;
  `require_ops_or_admin` = ops + admin + super_admin)
- Admin APIs: `app/api/v1/endpoints/admin.py`, `configs.py`, `query_info.py`
- "Only super admin can suspend admins": `app/services/admin_service.py` → `set_user_status`
- Roles list: `app/core/constants.py` → `UserRole`
