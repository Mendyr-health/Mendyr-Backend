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

## Patient ↔ professional mapping

A booking reaches every professional **of the booked service's profession** whose 15 km radius
covers the patient's home address. The tables below show those pairs. Distances are straight-line
distances computed by PostGIS from the seeded locations, the same check the app uses.

Doctors appear for completeness, but they get no requests until the catalogue has a doctor
service.

### Which professionals each patient can book

Professionals whose 15 km radius covers the patient's home, nearest first, with the distance.

| Patient (area) | Nurse | Physiotherapist | Caretaker | Baby care | Lab technician | Doctor |
|---|---|---|---|---|---|---|
| `patient01` (Whitefield) | `nurse02` 11.8 km | `physio02` 14.1 km | `caretaker02` 12.1 km | `babycare02` 13.2 km<br>`babycare01` 13.6 km | `labtech02` 12.9 km | `doctor02` 10.9 km<br>`doctor01` 14.8 km |
| `patient02` (Marathahalli) | `nurse02` 6.3 km<br>`nurse03` 11.9 km<br>`nurse01` 13.8 km | `physio02` 8.3 km<br>`physio03` 13.5 km | `caretaker02` 6.4 km<br>`caretaker03` 10.6 km<br>`caretaker01` 13 km | `babycare02` 7.9 km<br>`babycare01` 9.8 km<br>`babycare03` 10.2 km | `labtech02` 7.6 km<br>`labtech03` 13.6 km<br>`labtech01` 13.7 km | `doctor02` 5.1 km<br>`doctor01` 9.8 km |
| `patient03` (Electronic City) | `nurse03` 11.4 km<br>`nurse02` 14.2 km | `physio03` 10.5 km<br>`physio02` 10.7 km | `caretaker03` 9.6 km<br>`caretaker02` 13 km | `babycare03` 7.2 km | `labtech02` 7.5 km<br>`labtech03` 14.3 km | `doctor02` 12.7 km |
| `patient04` (Yelahanka) | `nurse01` 7.2 km | `physio01` 11.3 km | `caretaker01` 8.8 km | `babycare01` 9.3 km<br>`babycare02` 13.6 km | `labtech01` 10.5 km | `doctor01` 11.5 km<br>`doctor03` 13 km |
| `patient05` (Bellandur) | `nurse02` 6.1 km<br>`nurse03` 9.2 km<br>`nurse01` 14.6 km | `physio02` 5.9 km<br>`physio03` 10.4 km<br>`physio01` 14.8 km | `caretaker02` 5.5 km<br>`caretaker03` 7.6 km<br>`caretaker01` 13.5 km | `babycare03` 6.7 km<br>`babycare02` 7.8 km<br>`babycare01` 11.6 km | `labtech02` 4 km<br>`labtech03` 11.5 km<br>`labtech01` 13.5 km | `doctor02` 4.5 km<br>`doctor01` 10.1 km |
| `patient06` (Vijayanagar) | `nurse03` 8.4 km<br>`nurse01` 9.9 km<br>`nurse02` 11.8 km | `physio01` 4.8 km<br>`physio03` 9.2 km<br>`physio02` 10.7 km | `caretaker01` 8.8 km<br>`caretaker03` 10.4 km<br>`caretaker02` 11.5 km | `babycare02` 10.4 km<br>`babycare03` 12.8 km<br>`babycare01` 13.2 km | `labtech03` 5.5 km<br>`labtech01` 6.5 km<br>`labtech02` 14.1 km | `doctor03` 3 km<br>`doctor01` 9.6 km<br>`doctor02` 12.8 km |
| `patient07` (Banaswadi) | `nurse02` 4.8 km<br>`nurse01` 6.4 km<br>`nurse03` 11.7 km | `physio02` 9.2 km<br>`physio01` 9.6 km<br>`physio03` 13.9 km | `caretaker02` 6 km<br>`caretaker01` 6.1 km<br>`caretaker03` 11.7 km | `babycare01` 2 km<br>`babycare02` 4.4 km<br>`babycare03` 13 km | `labtech01` 7.7 km<br>`labtech02` 11.3 km<br>`labtech03` 11.6 km | `doctor01` 4.1 km<br>`doctor02` 6 km<br>`doctor03` 11.1 km |
| `patient08` (Yeshwanthpur) | `nurse01` 6.2 km<br>`nurse02` 12.6 km<br>`nurse03` 12.9 km | `physio01` 3.9 km<br>`physio02` 13.8 km<br>`physio03` 14.4 km | `caretaker01` 6.1 km<br>`caretaker02` 13.1 km<br>`caretaker03` 14.5 km | `babycare01` 10.8 km<br>`babycare02` 10.9 km | `labtech01` 5.1 km<br>`labtech03` 10.2 km | `doctor03` 4.4 km<br>`doctor01` 9 km<br>`doctor02` 14.1 km |
| `patient09` (Shivajinagar) | `nurse02` 4.1 km<br>`nurse01` 5.6 km<br>`nurse03` 6.8 km | `physio01` 4.9 km<br>`physio02` 5.9 km<br>`physio03` 9 km | `caretaker01` 4.1 km<br>`caretaker02` 4.5 km<br>`caretaker03` 7.7 km | `babycare02` 2.5 km<br>`babycare01` 6 km<br>`babycare03` 9.7 km | `labtech01` 3.5 km<br>`labtech03` 5.9 km<br>`labtech02` 9.4 km | `doctor01` 1.9 km<br>`doctor02` 5.6 km<br>`doctor03` 5.8 km |
| `patient10` (Sarjapur Road) | `nurse02` 8.5 km<br>`nurse03` 10.2 km | `physio02` 7.3 km<br>`physio03` 11 km | `caretaker02` 7.7 km<br>`caretaker03` 8.4 km | `babycare03` 6.8 km<br>`babycare02` 10.2 km<br>`babycare01` 14 km | `labtech02` 4.3 km<br>`labtech03` 12.8 km | `doctor02` 6.8 km<br>`doctor01` 12.4 km |
| `patient11` (RR Nagar) | `nurse03` 8.5 km<br>`nurse02` 14.5 km<br>`nurse01` 14.9 km | `physio03` 8 km<br>`physio01` 9.9 km<br>`physio02` 11.9 km | `caretaker03` 10.3 km<br>`caretaker01` 13.6 km<br>`caretaker02` 13.9 km | `babycare03` 12.3 km<br>`babycare02` 13.7 km | `labtech03` 6.5 km<br>`labtech01` 11.3 km<br>`labtech02` 14.4 km | `doctor03` 8.1 km<br>`doctor01` 13.5 km |
| `patient12` (Cooke Town) | `nurse02` 3.2 km<br>`nurse01` 5.4 km<br>`nurse03` 8.9 km | `physio01` 6.9 km<br>`physio02` 7 km<br>`physio03` 11.1 km | `caretaker01` 4.3 km<br>`caretaker02` 4.3 km<br>`caretaker03` 9.2 km | `babycare02` 1.8 km<br>`babycare01` 3.6 km<br>`babycare03` 10.8 km | `labtech01` 5.2 km<br>`labtech03` 8.5 km<br>`labtech02` 9.8 km | `doctor01` 1.2 km<br>`doctor02` 4.8 km<br>`doctor03` 8.2 km |

### How many patients each professional covers

| Professional | Profession | Area | Patients in range | Which patients |
|---|---|---|---|---|
| `nurse01` | Nurse | Hebbal | **9** / 12 | 02, 04, 05, 06, 07, 08, 09, 11, 12 |
| `nurse02` | Nurse | Indiranagar | **11** / 12 | 01, 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `nurse03` | Nurse | Jayanagar | **10** / 12 | 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `physio01` | Physiotherapist | Malleshwaram | **8** / 12 | 04, 05, 06, 07, 08, 09, 11, 12 |
| `physio02` | Physiotherapist | Koramangala | **11** / 12 | 01, 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `physio03` | Physiotherapist | JP Nagar | **10** / 12 | 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `caretaker01` | Caretaker | RT Nagar | **9** / 12 | 02, 04, 05, 06, 07, 08, 09, 11, 12 |
| `caretaker02` | Caretaker | Domlur | **11** / 12 | 01, 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `caretaker03` | Caretaker | BTM Layout | **10** / 12 | 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `babycare01` | Baby care | Kalyan Nagar | **10** / 12 | 01, 02, 04, 05, 06, 07, 08, 09, 10, 12 |
| `babycare02` | Baby care | Ulsoor | **11** / 12 | 01, 02, 04, 05, 06, 07, 08, 09, 10, 11, 12 |
| `babycare03` | Baby care | Bommanahalli | **9** / 12 | 02, 03, 05, 06, 07, 09, 10, 11, 12 |
| `labtech01` | Lab technician | Sadashivanagar | **9** / 12 | 02, 04, 05, 06, 07, 08, 09, 11, 12 |
| `labtech02` | Lab technician | HSR Layout | **10** / 12 | 01, 02, 03, 05, 06, 07, 09, 10, 11, 12 |
| `labtech03` | Lab technician | Basavanagudi | **10** / 12 | 02, 03, 05, 06, 07, 08, 09, 10, 11, 12 |
| `doctor01` | Doctor | Frazer Town | **11** / 12 | 01, 02, 04, 05, 06, 07, 08, 09, 10, 11, 12 |
| `doctor02` | Doctor | Old Airport Road | **10** / 12 | 01, 02, 03, 05, 06, 07, 08, 09, 10, 12 |
| `doctor03` | Doctor | Rajajinagar | **7** / 12 | 04, 06, 07, 08, 09, 11, 12 |

### Per profession

| Profession | Professionals | Patients covered | Professionals reachable per patient | Patients with only one choice |
|---|---|---|---|---|
| Nurse | 3 | **12** / 12 | 1–3 (avg 2.5) | `patient01`, `patient04` |
| Physiotherapist | 3 | **12** / 12 | 1–3 (avg 2.4) | `patient01`, `patient04` |
| Caretaker | 3 | **12** / 12 | 1–3 (avg 2.5) | `patient01`, `patient04` |
| Baby care | 3 | **12** / 12 | 1–3 (avg 2.5) | `patient03` |
| Lab technician | 3 | **12** / 12 | 1–3 (avg 2.4) | `patient01`, `patient04` |
| Doctor | 3 | **12** / 12 | 1–3 (avg 2.3) | `patient03` |

**Choosing who to test with:**
- **Exactly one professional should get the request:** use `patient01` (Whitefield) or
  `patient04` (Yelahanka). For most professions there's a single professional in range, so you
  know who to log in as. `patient03` (Electronic City) works the same way for baby care.
- **"First to accept wins" (several professionals get the same request):** use a central
  patient, such as `patient09` (Shivajinagar) or `patient12` (Cooke Town). All three
  professionals of every profession are in range.
- **The widest reach:** `nurse02`, `physio02`, `caretaker02`, `babycare02` and `doctor01` each
  cover 11 of the 12 patients.

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
