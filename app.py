"""
app.py — Application Flask Hôpital
Gestion des Lits et Flux Hospitaliers
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from uuid import uuid4
import data_store as db

app = Flask(__name__)
app.secret_key = "hopital-secret-2025"

def uid(): return str(uuid4())

# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    stats     = db.get_global_stats()
    ward_stats = db.get_ward_stats()
    notifs    = sorted(db.NOTIFICATIONS.values(), key=lambda n: n["created_ts"], reverse=True)[:5]
    transports = [t for t in db.TRANSPORTS.values() if t["status"] in ("pending","assigned","in_progress")]
    discharges = [p for p in db.PATIENTS.values() if p["status"] == "sortie_prévue"]
    waiting   = sorted([p for p in db.PATIENTS.values() if p["status"] == "en_attente"],
                        key=lambda p: (list(db.PRIORITY_COLORS.keys()).index(p["priority"]), p["arrival_ts"]))
    return render_template("dashboard.html",
        stats=stats, ward_stats=ward_stats,
        notifs=notifs, transports=transports,
        discharges=discharges, waiting=waiting,
        now=datetime.now().strftime("%d/%m/%Y %H:%M"),
        PRIORITY_COLORS=db.PRIORITY_COLORS,
        PATIENT_STATUS_COLORS=db.PATIENT_STATUS_COLORS,
    )

# ══════════════════════════════════════════════════════════════
#  LITS
# ══════════════════════════════════════════════════════════════

@app.route("/beds")
def beds():
    ward_filter   = request.args.get("ward", "")
    status_filter = request.args.get("status", "")
    beds_list = list(db.BEDS.values())
    if ward_filter:   beds_list = [b for b in beds_list if b["ward_code"] == ward_filter]
    if status_filter: beds_list = [b for b in beds_list if b["status"] == status_filter]
    beds_list.sort(key=lambda b: (b["ward_code"], b["number"]))
    ward_stats = db.get_ward_stats()
    return render_template("beds/index.html",
        beds=beds_list, wards=db.WARDS, ward_stats=ward_stats,
        ward_filter=ward_filter, status_filter=status_filter,
        STATUS_COLORS=db.STATUS_COLORS,
        VALID_TRANSITIONS=db.VALID_TRANSITIONS,
    )

@app.route("/beds/<bed_id>")
def bed_detail(bed_id):
    bed = db.BEDS.get(bed_id)
    if not bed: flash("Lit introuvable", "danger"); return redirect(url_for("beds"))
    patient = db.PATIENTS.get(bed["patient_id"]) if bed["patient_id"] else None
    transitions = db.VALID_TRANSITIONS.get(bed["status"], [])
    return render_template("beds/detail.html", bed=bed, patient=patient,
        transitions=transitions, STATUS_COLORS=db.STATUS_COLORS,
        PRIORITY_COLORS=db.PRIORITY_COLORS)

@app.route("/beds/<bed_id>/status", methods=["POST"])
def update_bed_status(bed_id):
    bed = db.BEDS.get(bed_id)
    if not bed: return jsonify({"error": "Lit introuvable"}), 404
    new_status = request.form.get("status") or request.json.get("status", "")
    allowed = db.VALID_TRANSITIONS.get(bed["status"], [])
    if new_status not in allowed:
        if request.is_json:
            return jsonify({"error": f"Transition {bed['status']} → {new_status} non autorisée"}), 422
        flash(f"Transition non autorisée : {bed['status']} → {new_status}", "danger")
        return redirect(url_for("bed_detail", bed_id=bed_id))

    old = bed["status"]
    bed["status"]      = new_status
    bed["last_change"] = datetime.now().strftime("%H:%M")

    if new_status == "libre":
        bed["patient_id"]   = None
        bed["patient_name"] = None
        bed["occupied_since"] = None
        _add_notif("info", "cadre", "🟢", f"Lit disponible — {bed['number']}", f"Le lit {bed['number']} est maintenant libre.")
    elif new_status == "nettoyage":
        bed["patient_id"]   = None
        bed["patient_name"] = None
        bed["occupied_since"] = None
        _add_notif("warning", "brancardier", "🟡", f"Nettoyage requis — {bed['number']}", f"Le lit {bed['number']} attend le nettoyage.")
    elif new_status == "occupé":
        bed["occupied_since"] = datetime.now().strftime("%d/%m %H:%M")

    if request.is_json:
        return jsonify({"success": True, "new_status": new_status, "bed": bed})
    flash(f"Lit {bed['number']} : {old} → {new_status}", "success")
    return redirect(url_for("beds"))

@app.route("/beds/assign", methods=["POST"])
def assign_bed():
    patient_id  = request.form.get("patient_id")
    service     = request.form.get("service")
    assigned_by = request.form.get("assigned_by", "Système")
    patient = db.PATIENTS.get(patient_id)
    if not patient: flash("Patient introuvable", "danger"); return redirect(url_for("patients"))

    # Trouver un lit libre dans le service demandé
    free_beds = [b for b in db.BEDS.values()
                 if b["status"] == "libre" and (not service or b["service"] == service)]
    if not free_beds:
        flash(f"Aucun lit libre disponible en {service or 'hôpital'}. Envisager un transfert.", "danger")
        return redirect(url_for("patients"))

    bed = free_beds[0]
    bed["status"]       = "réservé"
    bed["patient_id"]   = patient_id
    bed["patient_name"] = patient["full_name"]
    bed["last_change"]  = datetime.now().strftime("%H:%M")
    patient["bed_id"]   = bed["id"]
    patient["bed_number"] = bed["number"]
    patient["ward_code"]  = bed["ward_code"]
    patient["status"]     = "admis"
    patient["events"].append({"type": "Lit attribué", "location": bed["number"], "time": datetime.now().strftime("%H:%M"), "icon": "🛏️"})
    _add_notif("warning", "brancardier", "🟠", f"Brancardage — {patient['full_name']}", f"Patient → Lit {bed['number']} ({bed['ward_code']}). Par {assigned_by}.")
    flash(f"Lit {bed['number']} attribué à {patient['full_name']}", "success")
    return redirect(url_for("patient_detail", patient_id=patient_id))

# ══════════════════════════════════════════════════════════════
#  PATIENTS
# ══════════════════════════════════════════════════════════════

@app.route("/patients")
def patients():
    status_f = request.args.get("status", "")
    prio_f   = request.args.get("priority", "")
    svc_f    = request.args.get("service", "")
    pts = list(db.PATIENTS.values())
    if status_f: pts = [p for p in pts if p["status"] == status_f]
    if prio_f:   pts = [p for p in pts if p["priority"] == prio_f]
    if svc_f:    pts = [p for p in pts if p["target_service"] == svc_f]
    prio_order = {"critique": 0, "urgent": 1, "standard": 2, "non_urgent": 3}
    pts.sort(key=lambda p: (prio_order.get(p["priority"], 9), p["arrival_ts"]))
    services = sorted(set(p["target_service"] for p in db.PATIENTS.values()))
    return render_template("patients/index.html",
        patients=pts, status_filter=status_f, prio_filter=prio_f, svc_filter=svc_f,
        services=services, PRIORITY_COLORS=db.PRIORITY_COLORS,
        PATIENT_STATUS_COLORS=db.PATIENT_STATUS_COLORS)

@app.route("/patients/new", methods=["GET", "POST"])
def new_patient():
    if request.method == "POST":
        pid = uid()
        prio = request.form.get("priority", "standard")
        svc  = request.form.get("target_service", "médecine_interne")
        fn   = request.form.get("first_name", "").strip()
        ln   = request.form.get("last_name", "").strip()
        now  = datetime.now()
        db.PATIENTS[pid] = {
            "id": pid, "ipp": f"P{len(db.PATIENTS)+1:03d}",
            "first_name": fn, "last_name": ln, "full_name": f"{fn} {ln}",
            "birth_date": request.form.get("birth_date", ""),
            "gender": request.form.get("gender", "M"),
            "priority": prio, "target_service": svc,
            "status": "en_attente",
            "ward_code": None, "bed_id": None, "bed_number": None,
            "diagnosis": request.form.get("diagnosis", ""),
            "physician": request.form.get("physician", ""),
            "arrival_at": now.strftime("%d/%m/%Y %H:%M"),
            "arrival_ts": now,
            "hospitalization_at": None, "discharge_planned_at": None,
            "needs_isolation": "needs_isolation" in request.form,
            "mobility_restricted": "mobility_restricted" in request.form,
            "events": [
                {"type": "Arrivée", "location": "Urgences", "time": now.strftime("%H:%M"), "icon": "🚑"},
                {"type": "Triage",  "location": f"Priorité {prio}", "time": now.strftime("%H:%M"), "icon": "📋"},
            ]
        }
        _add_notif(
            "warning" if prio in ("critique","urgent") else "info",
            "cadre", "🔵",
            f"Nouveau patient — {fn} {ln} ({prio})",
            f"Orientation demandée vers : {svc}."
        )
        flash(f"Patient {fn} {ln} admis avec succès", "success")
        return redirect(url_for("patient_detail", patient_id=pid))
    services = list(set(p["target_service"] for p in db.PATIENTS.values()))
    return render_template("patients/new.html", services=services,
        PRIORITY_COLORS=db.PRIORITY_COLORS)

@app.route("/patients/<patient_id>")
def patient_detail(patient_id):
    patient = db.PATIENTS.get(patient_id)
    if not patient: flash("Patient introuvable", "danger"); return redirect(url_for("patients"))
    bed = db.BEDS.get(patient["bed_id"]) if patient["bed_id"] else None
    transitions = db.PATIENT_TRANSITIONS.get(patient["status"], [])
    free_beds = {svc: [b for b in db.BEDS.values() if b["status"] == "libre" and b["service"] == svc]
                 for svc in set(p["target_service"] for p in db.PATIENTS.values())}
    return render_template("patients/detail.html",
        patient=patient, bed=bed, transitions=transitions,
        PRIORITY_COLORS=db.PRIORITY_COLORS,
        PATIENT_STATUS_COLORS=db.PATIENT_STATUS_COLORS,
        free_beds_count=sum(1 for b in db.BEDS.values() if b["status"] == "libre" and b["service"] == patient["target_service"]),
        WARDS=db.WARDS)

@app.route("/patients/<patient_id>/status", methods=["POST"])
def update_patient_status(patient_id):
    patient = db.PATIENTS.get(patient_id)
    if not patient: flash("Patient introuvable","danger"); return redirect(url_for("patients"))
    new_status = request.form.get("status")
    allowed = db.PATIENT_TRANSITIONS.get(patient["status"], [])
    if new_status not in allowed:
        flash(f"Transition non autorisée : {patient['status']} → {new_status}", "danger")
        return redirect(url_for("patient_detail", patient_id=patient_id))

    old = patient["status"]
    patient["status"] = new_status
    patient["events"].append({"type": new_status.replace("_"," ").title(),
                               "location": patient.get("ward_code") or "—",
                               "time": datetime.now().strftime("%H:%M"), "icon": "🔄"})
    if new_status == "hospitalisé":
        patient["hospitalization_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        if patient["bed_id"]:
            bed = db.BEDS.get(patient["bed_id"])
            if bed:
                bed["status"]       = "occupé"
                bed["patient_id"]   = patient_id
                bed["patient_name"] = patient["full_name"]
                bed["occupied_since"] = datetime.now().strftime("%d/%m %H:%M")
    elif new_status == "sortie_prévue":
        hours = int(request.form.get("hours_ahead", 4))
        patient["discharge_planned_at"] = (datetime.now() + timedelta(hours=hours)).strftime("%d/%m/%Y %H:%M")
        _add_notif("info", "cadre", "🏠", f"Sortie planifiée — {patient['full_name']}",
                   f"Sortie prévue à {patient['discharge_planned_at']}. Lit {patient.get('bed_number','—')} à libérer.")
    elif new_status == "sorti":
        patient["discharged_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        if patient["bed_id"]:
            bed = db.BEDS.get(patient["bed_id"])
            if bed:
                bed["status"]       = "nettoyage"
                bed["patient_id"]   = None
                bed["patient_name"] = None
                bed["last_change"]  = datetime.now().strftime("%H:%M")
                _add_notif("warning", "brancardier", "🟡", f"Nettoyage — {bed['number']}",
                           f"Patient {patient['full_name']} sorti. Lit à nettoyer.")
        patient["bed_id"]     = None
        patient["bed_number"] = None

    flash(f"Statut mis à jour : {old} → {new_status}", "success")
    return redirect(url_for("patient_detail", patient_id=patient_id))

# ══════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════════════

@app.route("/notifications")
def notifications():
    role_f  = request.args.get("role", "")
    level_f = request.args.get("level", "")
    unread  = request.args.get("unread", "")
    notifs  = list(db.NOTIFICATIONS.values())
    if role_f:  notifs = [n for n in notifs if n["role"] == role_f]
    if level_f: notifs = [n for n in notifs if n["level"] == level_f]
    if unread:  notifs = [n for n in notifs if not n["is_read"]]
    notifs.sort(key=lambda n: n["created_ts"], reverse=True)
    transports = sorted(db.TRANSPORTS.values(), key=lambda t: t["requested_at"], reverse=True)
    roles = sorted(set(n["role"] for n in db.NOTIFICATIONS.values()))
    summary = {
        "total": len(db.NOTIFICATIONS),
        "unread": sum(1 for n in db.NOTIFICATIONS.values() if not n["is_read"]),
        "critical": sum(1 for n in db.NOTIFICATIONS.values() if n["level"] == "critique"),
    }
    return render_template("notifications.html",
        notifications=notifs, transports=transports,
        roles=roles, role_filter=role_f, level_filter=level_f, unread_filter=unread,
        summary=summary)

@app.route("/notifications/<notif_id>/acknowledge", methods=["POST"])
def acknowledge_notif(notif_id):
    n = db.NOTIFICATIONS.get(notif_id)
    if n:
        n["is_read"] = True
        n["is_acknowledged"] = True
    return redirect(url_for("notifications"))

@app.route("/notifications/acknowledge-all", methods=["POST"])
def acknowledge_all():
    for n in db.NOTIFICATIONS.values():
        n["is_read"] = True; n["is_acknowledged"] = True
    flash("Toutes les notifications acquittées", "success")
    return redirect(url_for("notifications"))

@app.route("/transports/<transport_id>/update", methods=["POST"])
def update_transport(transport_id):
    t = db.TRANSPORTS.get(transport_id)
    if t:
        action = request.form.get("action")
        if action == "assign":
            t["status"] = "assigned"
            t["agent"]  = request.form.get("agent", "Brancardier")
        elif action == "complete":
            t["status"]       = "completed"
            t["completed_at"] = datetime.now().strftime("%H:%M")
    return redirect(url_for("notifications"))

# ══════════════════════════════════════════════════════════════
#  CAPACITÉ & PRÉVISIONS
# ══════════════════════════════════════════════════════════════

@app.route("/capacity")
def capacity():
    import math
    ward_stats = db.get_ward_stats()
    global_stats = db.get_global_stats()
    now = datetime.now()

    HOURLY_ADM = {0:.3,1:.2,2:.2,3:.2,4:.3,5:.4,6:.6,7:.9,8:1.2,9:1.4,10:1.3,11:1.2,
                  12:1.,13:1.1,14:1.2,15:1.3,16:1.2,17:1.1,18:1.,19:.9,20:.8,21:.6,22:.5,23:.4}
    HOURLY_DIS = {0:0,1:0,2:0,3:0,4:0,5:.1,6:.2,7:.5,8:1.2,9:1.5,10:1.8,11:1.6,
                  12:1.,13:.8,14:1.,15:1.2,16:1.4,17:1.,18:.5,19:.3,20:.2,21:.1,22:0,23:0}
    WEEKDAY    = {0:1.1,1:1.,2:1.,3:1.05,4:1.15,5:.85,6:.75}

    forecasts = []
    for code, ws in ward_stats.items():
        total  = ws["total_actual"]
        occ    = ws["occupé"]
        rate   = ws["occupancy_rate"] / 100
        # Simuler +6h
        for h in range(6):
            fh  = (now.hour + h) % 24
            fd  = (now.weekday() + (now.hour + h)//24) % 7
            adm = (8/24) * HOURLY_ADM.get(fh,1.) * WEEKDAY.get(fd,1.)
            dis = (7/24) * HOURLY_DIS.get(fh,1.) * WEEKDAY.get(fd,1.)
            occ = max(0, min(total, occ + adm - dis))
        pred_rate = round(occ / total * 100) if total else 0
        risk = "danger" if pred_rate >= 95 else "warning" if pred_rate >= 85 else "success"
        forecasts.append({**ws, "pred_rate": pred_rate, "pred_free": max(0, total - round(occ)),
                          "risk": risk, "confidence": max(50, 95 - 6*2)})

    forecasts.sort(key=lambda f: -f["pred_rate"])
    return render_template("capacity.html",
        ward_stats=ward_stats, forecasts=forecasts, global_stats=global_stats,
        now=now.strftime("%d/%m/%Y %H:%M"))

# ══════════════════════════════════════════════════════════════
#  API JSON (pour AJAX)
# ══════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_global_stats())

@app.route("/api/ward-stats")
def api_ward_stats():
    return jsonify(db.get_ward_stats())

@app.route("/api/notifications/count")
def api_notif_count():
    unread = sum(1 for n in db.NOTIFICATIONS.values() if not n["is_read"])
    return jsonify({"unread": unread})

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _add_notif(level, role, icon, title, message):
    nid = uid()
    db.NOTIFICATIONS[nid] = {
        "id": nid, "level": level, "role": role, "icon": icon,
        "title": title, "message": message,
        "is_read": False, "is_acknowledged": False,
        "created_at": datetime.now().strftime("%H:%M"),
        "created_ts": datetime.now(),
    }

@app.context_processor
def inject_globals():
    return {
        "unread_count": sum(1 for n in db.NOTIFICATIONS.values() if not n["is_read"]),
        "waiting_count": sum(1 for p in db.PATIENTS.values() if p["status"] == "en_attente"),
    }

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
