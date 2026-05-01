"""
data_store.py — Magasin de données partagé (remplacer par PostgreSQL en prod)
"""
from datetime import datetime, timedelta
from uuid import uuid4

def uid(): return str(uuid4())

# ─── SERVICES (Wards) ─────────────────────────────────────────────────────────
WARDS = {
    "URG-A":    {"id": "w1", "code": "URG-A",    "name": "Urgences",           "service": "urgences",          "floor": 0, "total": 30},
    "REA-1":    {"id": "w2", "code": "REA-1",     "name": "Réanimation",        "service": "réanimation",       "floor": 1, "total": 12},
    "CARDIO-A": {"id": "w3", "code": "CARDIO-A",  "name": "Cardiologie",        "service": "cardiologie",       "floor": 2, "total": 24},
    "CHIR-A":   {"id": "w4", "code": "CHIR-A",    "name": "Chirurgie",          "service": "chirurgie",         "floor": 3, "total": 20},
    "MED-B":    {"id": "w5", "code": "MED-B",     "name": "Médecine Interne",   "service": "médecine_interne",  "floor": 1, "total": 28},
    "NEURO-A":  {"id": "w6", "code": "NEURO-A",   "name": "Neurologie",         "service": "neurologie",        "floor": 2, "total": 16},
    "ONCO-B":   {"id": "w7", "code": "ONCO-B",    "name": "Oncologie",          "service": "oncologie",         "floor": 4, "total": 18},
    "GER-C":    {"id": "w8", "code": "GER-C",     "name": "Gériatrie",          "service": "gériatrie",         "floor": 3, "total": 20},
}

# ─── LITS ─────────────────────────────────────────────────────────────────────
STATUS_CYCLE = ["occupé", "occupé", "libre", "nettoyage", "occupé", "libre", "réservé", "occupé", "maintenance", "libre"]

BEDS = {}
for ward in WARDS.values():
    for i in range(1, ward["total"] + 1):
        bid = uid()
        status = STATUS_CYCLE[i % len(STATUS_CYCLE)]
        BEDS[bid] = {
            "id": bid,
            "number": f"{ward['code']}-{i:02d}",
            "ward_code": ward["code"],
            "ward_name": ward["name"],
            "service": ward["service"],
            "status": status,
            "patient_id": None,
            "patient_name": None,
            "occupied_since": (datetime.now() - timedelta(hours=i*2)).strftime("%d/%m %H:%M") if status == "occupé" else None,
            "last_change": datetime.now().strftime("%H:%M"),
            "has_monitoring": ward["code"] == "REA-1",
            "is_isolation": i % 7 == 0,
            "notes": ""
        }

# ─── PATIENTS ─────────────────────────────────────────────────────────────────
now = datetime.now
PATIENTS = {}

_patient_data = [
    ("Alice",    "DUPONT",    "1965-03-12", "F", "urgent",     "cardiologie",      "hospitalisé",      "CARDIO-A"),
    ("Bernard",  "MARTIN",    "1948-07-22", "M", "critique",   "réanimation",      "hospitalisé",      "REA-1"),
    ("Claire",   "LEFEBVRE",  "1978-11-05", "F", "standard",   "médecine_interne", "en_attente",       None),
    ("Denis",    "MOREAU",    "1955-09-18", "M", "urgent",     "chirurgie",        "admis",            "CHIR-A"),
    ("Emma",     "PETIT",     "1990-02-28", "F", "standard",   "neurologie",       "hospitalisé",      "NEURO-A"),
    ("Fabrice",  "LEROY",     "1972-06-14", "M", "non_urgent", "médecine_interne", "sortie_prévue",    "MED-B"),
    ("Geneviève","THOMAS",    "1940-12-01", "F", "urgent",     "gériatrie",        "hospitalisé",      "GER-C"),
    ("Henri",    "RICHARD",   "1983-04-19", "M", "standard",   "chirurgie",        "en_attente",       None),
    ("Isabelle", "DURAND",    "1961-08-30", "F", "critique",   "réanimation",      "en_attente",       None),
    ("Jacques",  "SIMON",     "1975-01-15", "M", "standard",   "cardiologie",      "sortie_prévue",    "CARDIO-A"),
]

for i, (fn, ln, bd, g, prio, svc, status, ward) in enumerate(_patient_data):
    pid = uid()
    arrival = now() - timedelta(hours=i*3+1)
    hosp = arrival + timedelta(hours=2) if status in ("hospitalisé", "sortie_prévue", "admis") else None
    discharge = hosp + timedelta(days=3) if status == "sortie_prévue" and hosp else None
    PATIENTS[pid] = {
        "id": pid,
        "ipp": f"P{i+1:03d}",
        "first_name": fn,
        "last_name": ln,
        "full_name": f"{fn} {ln}",
        "birth_date": bd,
        "gender": g,
        "priority": prio,
        "target_service": svc,
        "status": status,
        "ward_code": ward,
        "bed_id": None,
        "bed_number": None,
        "diagnosis": ["Infarctus", "Polytraumatisme", "Pneumonie", "Appendicite", "AVC", "Insuffisance rénale", "Fracture", "Infection", "Embolie", "Arythmie"][i],
        "physician": ["Dr. Martin", "Dr. Dupont", "Dr. Leroy", "Dr. Bernard", "Dr. Chen"][i % 5],
        "arrival_at": arrival.strftime("%d/%m/%Y %H:%M"),
        "arrival_ts": arrival,
        "hospitalization_at": hosp.strftime("%d/%m/%Y %H:%M") if hosp else None,
        "discharge_planned_at": discharge.strftime("%d/%m/%Y %H:%M") if discharge else None,
        "needs_isolation": i % 5 == 0,
        "mobility_restricted": i % 4 == 0,
        "events": [
            {"type": "Arrivée", "location": "Urgences", "time": arrival.strftime("%H:%M"), "icon": "🚑"},
            {"type": "Triage", "location": f"Priorité {prio}", "time": (arrival + timedelta(minutes=5)).strftime("%H:%M"), "icon": "📋"},
        ] + ([{"type": "Admission", "location": ward or svc, "time": hosp.strftime("%H:%M") if hosp else "—", "icon": "🛏️"}] if hosp else [])
          + ([{"type": "Sortie prévue", "location": "—", "time": discharge.strftime("%d/%m %H:%M") if discharge else "—", "icon": "🏠"}] if discharge else [])
    }

# ─── NOTIFICATIONS ─────────────────────────────────────────────────────────────
NOTIFICATIONS = {}

_notif_data = [
    ("critique", "brancardier", "🔴", "Brancardage urgent — Bernard MARTIN", "Transfert REA → Cardiologie. Priorité critique.", False),
    ("warning",  "cadre",       "🟠", "Nettoyage requis — URG-A-07",          "Le lit URG-A-07 est prêt pour nettoyage.",       False),
    ("critique", "direction",   "🔴", "Saturation REA-1 — 92%",               "Réanimation proche de la capacité maximale.",    False),
    ("info",     "cadre",       "🟢", "Lit disponible — CARDIO-A-03",          "Le lit CARDIO-A-03 est maintenant libre.",       True),
    ("warning",  "urgentiste",  "🟡", "Patient P3 en attente — 2h",            "Claire LEFEBVRE attend un lit depuis 2h.",       False),
    ("info",     "brancardier", "🔵", "Affectation confirmée — Denis MOREAU",  "Patient MOREAU → CHIR-A-08.",                   True),
]

for i, (lvl, role, icon, title, msg, read) in enumerate(_notif_data):
    nid = uid()
    NOTIFICATIONS[nid] = {
        "id": nid,
        "level": lvl,
        "role": role,
        "icon": icon,
        "title": title,
        "message": msg,
        "is_read": read,
        "is_acknowledged": read,
        "created_at": (now() - timedelta(minutes=i*15)).strftime("%H:%M"),
        "created_ts": now() - timedelta(minutes=i*15),
    }

# ─── TRANSPORTS ───────────────────────────────────────────────────────────────
TRANSPORTS = {}
_transport_data = [
    ("Bernard MARTIN",  "Urgences",   "Réanimation",   "critique", "pending",     None),
    ("Denis MOREAU",    "Chirurgie",  "Rééducation",   "urgent",   "assigned",    "Marc D."),
    ("Emma PETIT",      "Urgences",   "Neurologie",    "standard", "in_progress", "Sophie L."),
    ("Geneviève THOMAS","Radiologie", "Gériatrie",     "urgent",   "completed",   "Pierre M."),
]
for i, (patient, from_loc, to_loc, prio, status, agent) in enumerate(_transport_data):
    tid = uid()
    TRANSPORTS[tid] = {
        "id": tid,
        "patient": patient,
        "from": from_loc,
        "to": to_loc,
        "priority": prio,
        "status": status,
        "agent": agent,
        "requested_at": (now() - timedelta(minutes=i*20+5)).strftime("%H:%M"),
        "completed_at": (now() - timedelta(minutes=5)).strftime("%H:%M") if status == "completed" else None,
    }

# ─── Helpers ──────────────────────────────────────────────────────────────────
VALID_TRANSITIONS = {
    "libre":       ["réservé", "nettoyage", "occupé", "maintenance"],
    "occupé":      ["nettoyage"],
    "nettoyage":   ["libre"],
    "réservé":     ["occupé", "libre"],
    "maintenance": ["libre"],
    "bloqué":      ["libre"],
}

PATIENT_TRANSITIONS = {
    "en_attente":    ["admis"],
    "admis":         ["hospitalisé", "en_attente"],
    "hospitalisé":   ["en_transfert", "sortie_prévue"],
    "en_transfert":  ["hospitalisé"],
    "sortie_prévue": ["sorti"],
}

STATUS_COLORS = {
    "libre":       ("bg-success",   "Libre"),
    "occupé":      ("bg-primary",   "Occupé"),
    "réservé":     ("bg-warning",   "Réservé"),
    "nettoyage":   ("bg-info",      "Nettoyage"),
    "maintenance": ("bg-secondary", "Maintenance"),
    "bloqué":      ("bg-danger",    "Bloqué"),
}

PATIENT_STATUS_COLORS = {
    "en_attente":    ("warning",  "En attente"),
    "admis":         ("info",     "Admis"),
    "hospitalisé":   ("primary",  "Hospitalisé"),
    "en_transfert":  ("secondary","En transfert"),
    "sortie_prévue": ("success",  "Sortie prévue"),
    "sorti":         ("light",    "Sorti"),
}

PRIORITY_COLORS = {
    "critique":   "danger",
    "urgent":     "warning",
    "standard":   "primary",
    "non_urgent": "secondary",
}

def get_ward_stats():
    stats = {}
    for code, ward in WARDS.items():
        ward_beds = [b for b in BEDS.values() if b["ward_code"] == code]
        counts = {s: sum(1 for b in ward_beds if b["status"] == s)
                  for s in ["libre", "occupé", "réservé", "nettoyage", "maintenance"]}
        total = len(ward_beds)
        free  = counts["libre"]
        rate  = round((total - free) / total * 100) if total else 0
        alert = "danger" if rate >= 95 else "warning" if rate >= 85 else "success"
        stats[code] = {**ward, **counts, "total_actual": total,
                       "occupancy_rate": rate, "alert": alert}
    return stats

def get_global_stats():
    all_beds = list(BEDS.values())
    total = len(all_beds)
    by_status = {s: sum(1 for b in all_beds if b["status"] == s)
                 for s in ["libre", "occupé", "réservé", "nettoyage", "maintenance"]}
    free = by_status["libre"]
    rate = round((total - free) / total * 100) if total else 0

    pts = list(PATIENTS.values())
    waiting = sum(1 for p in pts if p["status"] == "en_attente")
    hosp    = sum(1 for p in pts if p["status"] == "hospitalisé")
    planned = sum(1 for p in pts if p["status"] == "sortie_prévue")
    unread  = sum(1 for n in NOTIFICATIONS.values() if not n["is_read"])
    pending_transport = sum(1 for t in TRANSPORTS.values() if t["status"] == "pending")

    tension = min(100, rate * 0.6 + waiting * 3 + unread * 2)
    tension_level = "danger" if tension >= 70 else "warning" if tension >= 40 else "success"

    return {
        "total_beds": total,
        "by_status": by_status,
        "occupancy_rate": rate,
        "free_beds": free,
        "patients_waiting": waiting,
        "patients_hospitalized": hosp,
        "planned_discharges": planned,
        "unread_notifications": unread,
        "pending_transports": pending_transport,
        "tension_score": round(tension),
        "tension_level": tension_level,
    }
