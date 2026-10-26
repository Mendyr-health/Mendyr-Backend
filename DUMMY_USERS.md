# Dummy Users for Testing

Thirty ready-to-use test accounts: **18 professionals** (three of every profession) and
**12 patients**, all around **Bengaluru**. Use them to test booking, request alerts,
accepting/releasing visits and cancellations without signing anyone up by hand.

Every patient has a home address with at least one professional of each profession within
range. A booking from any patient therefore shows up in some professional's **Requests** list.

- **Password for every account:** `Demo@12345`
- **Email:** `<login>.dummy@mendyr.app` — e.g. `nurse01.dummy@mendyr.app`, `patient07.dummy@mendyr.app`

These are test accounts with a shared, public password. Never use them for real patients or
real professionals.

---

## Creating the accounts

The script is non-interactive and safe to re-run: accounts are matched by email, so running it
again adds anything missing and never creates duplicates.

**Locally** (needs the service catalogue, so seed that first):

```bash
make seed         # service catalogue — skip if already done
make seed-dummy   # uv run python -m scripts.seed_dummy_users
```

**On the shared database:** GitHub → **Actions** → **Seed dummy users** → **Run workflow**. It
has no inputs: it seeds the catalogue, then the accounts, and prints every login in the run log.
It uses the same database secrets as the other workflows.

Source: [`scripts/seed_dummy_users.py`](scripts/seed_dummy_users.py) and
[`.github/workflows/seed-dummy-users.yml`](.github/workflows/seed-dummy-users.yml).

---

## Professionals (18)

All are **approved**, **online**, available **any time** (no weekly timings), and accept
bookings within **15 km** of their location.

| Login | Name | Gender | Phone | Profession | Area | Services offered |
|---|---|---|---|---|---|---|
| `nurse01` | Ananya Iyer | F | +919700001001 | Nurse | Hebbal | General Nursing, ICU-Trained Nursing |
| `nurse02` | Meera Nair | F | +919700001002 | Nurse | Indiranagar | General Nursing, ICU-Trained Nursing |
| `nurse03` | Sunita Gowda | F | +919700001003 | Nurse | Jayanagar | General Nursing, ICU-Trained Nursing |
| `physio01` | Arjun Rao | M | +919700001004 | Physiotherapist | Malleshwaram | Physiotherapy Session |
| `physio02` | Neha Kulkarni | F | +919700001005 | Physiotherapist | Koramangala | Physiotherapy Session |
| `physio03` | Vikram Shetty | M | +919700001006 | Physiotherapist | JP Nagar | Physiotherapy Session |
| `caretaker01` | Ramesh Kumar | M | +919700001007 | Caretaker | RT Nagar | Elder Care Attendant |
| `caretaker02` | Lakshmi Devi | F | +919700001008 | Caretaker | Domlur | Elder Care Attendant |
| `caretaker03` | Suresh Babu | M | +919700001009 | Caretaker | BTM Layout | Elder Care Attendant |
| `babycare01` | Fatima Sheikh | F | +919700001010 | Baby care specialist | Kalyan Nagar | New-Mother & Baby Care |
| `babycare02` | Pooja Hegde | F | +919700001011 | Baby care specialist | Ulsoor | New-Mother & Baby Care |
| `babycare03` | Divya Menon | F | +919700001012 | Baby care specialist | Bommanahalli | New-Mother & Baby Care |
| `labtech01` | Imran Khan | M | +919700001013 | Lab technician | Sadashivanagar | At-Home Lab Sample Collection |
| `labtech02` | Kiran Patil | M | +919700001014 | Lab technician | HSR Layout | At-Home Lab Sample Collection |
| `labtech03` | Shreya Joshi | F | +919700001015 | Lab technician | Basavanagudi | At-Home Lab Sample Collection |
| `doctor01` | Dr. Rahul Verma | M | +919700001016 | Doctor | Frazer Town | — |
| `doctor02` | Dr. Kavya Reddy | F | +919700001017 | Doctor | Old Airport Road | — |
| `doctor03` | Dr. Sameer Desai | M | +919700001018 | Doctor | Rajajinagar | — |

**Doctors don't receive requests yet:** the service catalogue has no doctor service. They can
log in and use their profile, but no booking will reach them until one is added.

## Patients (12)

Each has one default home address in Bengaluru, Karnataka.

| Login | Name | Gender | Phone | Home address | Pincode |
|---|---|---|---|---|---|
| `patient01` | Gopal Krishnan | M | +919700002001 | 14, ITPL Main Road, Whitefield | 560066 |
| `patient02` | Saroja Rao | F | +919700002002 | 7, Outer Ring Road, Marathahalli | 560037 |
| `patient03` | Nikhil Agarwal | M | +919700002003 | 102, Neeladri Road, Electronic City | 560100 |
| `patient04` | Kamala Murthy | F | +919700002004 | 33, Bazaar Street, Yelahanka | 560064 |
| `patient05` | Ritu Sharma | F | +919700002005 | B-1204, Green Glen Layout, Bellandur | 560103 |
| `patient06` | Venkatesh Prasad | M | +919700002006 | 88, 9th Main Road, Vijayanagar | 560040 |
| `patient07` | Ayesha Siddiqui | F | +919700002007 | 21, Kammanahalli Main Road, Banaswadi | 560043 |
| `patient08` | Harish Chandra | M | +919700002008 | 5, Tumkur Road, Yeshwanthpur | 560022 |
| `patient09` | Mary Thomas | F | +919700002009 | 17, Infantry Road, Shivajinagar | 560001 |
| `patient10` | Sanjay Mishra | M | +919700002010 | C-305, Kaikondrahalli, Sarjapur Road | 560035 |
| `patient11` | Deepa Ramesh | F | +919700002011 | 61, BEML Layout, RR Nagar | 560098 |
| `patient12` | Joseph D'Souza | M | +919700002012 | 9, Wheeler Road, Cooke Town | 560005 |

Patients 01, 02, 04, 06, 08, 09 and 12 are elderly (born 1942–1960), which suits elder care and
nursing. Patients 03, 05, 07, 10 and 11 are younger, which suits baby care and physiotherapy.

---

## Who sees whose bookings

A booking reaches every professional of the right profession whose 15 km radius covers the
patient's address. Central patients reach all three; patients on the edge of the city reach
fewer:

| Patient (area) | Nurses | Physios | Caretakers | Baby care | Lab techs |
|---|---|---|---|---|---|
| `patient01` (Whitefield) | 1 | 1 | 1 | 2 | 1 |
| `patient02` (Marathahalli) | 3 | 2 | 3 | 3 | 3 |
| `patient03` (Electronic City) | 2 | 2 | 2 | 1 | 2 |
| `patient04` (Yelahanka) | 1 | 1 | 1 | 2 | 1 |
| `patient05` (Bellandur) | 3 | 3 | 3 | 3 | 3 |
| `patient06` (Vijayanagar) | 3 | 3 | 3 | 3 | 3 |
| `patient07` (Banaswadi) | 3 | 3 | 3 | 3 | 3 |
| `patient08` (Yeshwanthpur) | 3 | 3 | 3 | 2 | 2 |
| `patient09` (Shivajinagar) | 3 | 3 | 3 | 3 | 3 |
| `patient10` (Sarjapur Road) | 2 | 2 | 2 | 3 | 2 |
| `patient11` (RR Nagar) | 3 | 3 | 3 | 2 | 3 |
| `patient12` (Cooke Town) | 3 | 3 | 3 | 3 | 3 |

- **Testing one professional alone:** use `patient01` or `patient04`. Only one professional of
  most professions gets the request, so you know exactly who to log in as.
- **Testing "first to accept wins":** use a central patient (`patient09`, `patient12`). All
  three professionals of each profession get the request.

---

## Example test flows

Use two browser sessions that **don't share cookies**: one normal window and one incognito
window, or two different browsers. Two normal windows of the same browser share a session, so
logging in as the patient there replaces the professional's login.

**New booking → request alert → confirmation**
1. Window A: log in as `physio02` and stay on the dashboard.
2. Window B: log in as `patient05`, book a **Physiotherapy Session**.
3. Within ~15 s, `physio02` sees a **New request** pop-up and a red count on **Requests**.
4. `physio02` accepts. Within ~15 s, `patient05` sees a green **Booking confirmed** pop-up.

**Professional drops out**
1. Continue from above: `physio02` opens the booking under **Bookings** and clicks
   **Can't make it**.
2. `patient05` sees a red **Your professional cancelled** pop-up. The booking reopens for the
   other physios in range (`physio01`, `physio03`).

**Patient cancels**
1. `patient05` opens an upcoming booking and cancels it.
2. The professional who had accepted it sees a red **Booking cancelled** pop-up.

---

## Removing the accounts

There is no delete mode for these accounts yet. Once you've tested with them they have bookings,
and the demo-data delete script (`scripts/delete_demo_data.py`) only handles accounts without
any. Use the user-cleanup script instead (on the `test-deluser` branch until merged), passing the
`*.dummy@mendyr.app` emails. Re-running the seed afterwards recreates them.

## Related

The smaller presentation dataset (`asha.patel.demo@mendyr.app` plus three professionals, same
password) comes from `scripts/seed_demo_data.py` and the **Seed demo data** workflow. It is
separate from these accounts and lives near MG Road, so its professionals also see bookings
from many of the patients above.
