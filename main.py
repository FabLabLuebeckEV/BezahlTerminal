import csv
import os
from dotenv import load_dotenv
import json
import random
import string
import math
import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from easyverein.models.invoice import Invoice, InvoiceCreate, InvoiceUpdate
from easyverein.models.invoice_item import InvoiceItem, InvoiceItemCreate
from easyverein import EasyvereinAPI
import re
import json, logging, pathlib, shutil, tempfile
logging.basicConfig(level=logging.INFO)

TOKEN_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.I)   # EasyVerein-Token: 40 Hex-Zeichen

CONFIG_PATH = pathlib.Path("config.json")
CONFIG_BAK  = CONFIG_PATH.with_suffix(".bak")       # z. B. config.bak
DEFAULT_CFG = {"APIKEY": "", "REFRESH_TOKEN": ""}

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ersetzen_durch_einen_geheimen_schluessel")

CSV_FILE_PATH = "abrechnungen.csv"
PRICES_JSON_PATH = "Preise.json"

with open(PRICES_JSON_PATH, "r", encoding="utf-8") as f:
    price_data = json.load(f)

# Mapping: Wir gehen davon aus, dass price_data[x]["kosten"] in der Reihenfolge
# [Nichtmitglied, Fördermitglied, Ordentliches Mitglied] steht.
membership_index = {
    "Nichtmitglied": 0,
    "Fördermitglied": 1,
    "Ordentliches Mitglied": 2
}

def load_config() -> dict:
    """
    Lädt die Konfiguration.
    Fällt auf Backup oder Defaults zurück, wenn etwas nicht stimmt.
    """
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f) or DEFAULT_CFG
    except FileNotFoundError:
        logging.warning("config.json fehlt – lege neue Datei an.")
    except json.JSONDecodeError as e:
        logging.error("config.json defekt (%s) – versuche Backup.", e)
        # falls ein Backup existiert, kopieren wir es zurück
        if CONFIG_BAK.exists():
            shutil.copy(CONFIG_BAK, CONFIG_PATH)
            return load_config()
    # konnte nicht geladen werden → Defaults verwenden
    return DEFAULT_CFG


def atomic_write_json(path: pathlib.Path, data: dict):
    """
    Schreibt JSON erst in eine temporäre Datei und ersetzt
    das Original dann atomisch. Damit bleibt das alte File intakt,
    falls der Schreibvorgang abbricht.
    """
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".__cfg_", suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.flush()          # sicherstellen, dass alles im Puffer ist
            os.fsync(tmp_file.fileno())
        # Backup der aktuellen Datei anlegen
        if path.exists():
            shutil.copy2(path, CONFIG_BAK)
        # Jetzt das temp-File atomisch verschieben
        os.replace(tmp_name, path)
    finally:
        # Falls etwas schiefging, temporäre Datei entsorgen
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass

def handle_token_refresh(token: str | None):
    """
    Wird von EasyvereinAPI aufgerufen, wenn ein neuer Token kommt.
    * Speichert nur **gültige** Tokens (40 Hex-Zeichen).
    * Lässt den alten Schlüssel unangetastet, wenn der neue leer/ungültig ist.
    """
    if not token:
        logging.error("Token-Refresh: Kein Token erhalten – behalte alten Wert.")
        return

    if not TOKEN_PATTERN.fullmatch(token):
        logging.error("Token-Refresh: Ungültiges Format (%s…) – behalte alten Wert.", str(token)[:8])
        return

    # alles gut → Konfiguration aktualisieren
    config["APIKEY"] = token
    try:
        atomic_write_json(CONFIG_PATH, config)        # Funktion aus vorheriger Antwort
        logging.info("Token-Refresh: Neuer Schlüssel gespeichert.")
    except Exception:
        logging.exception("Token-Refresh: Konnte config.json nicht schreiben – behalte alten Wert.")


def create_invoice_with_attachment(file: Path, totalPrice: float, isCash: bool = True, name: string = "Sammelnutzer", date_for_invoice: datetime.date = None):
    logging.info("Try: Generating invoice with attachment")
    ev_connection = EasyvereinAPI(api_key=api_key,
                      api_version='v2.0', token_refresh_callback=handle_token_refresh, auto_refresh_token=True)  # token_refresh_callback=handle_token_refresh, auto_refresh_token=True,
    # Create a invoice
    invoice_model = InvoiceCreate(
        invNumber=file.stem,
        totalPrice=totalPrice,
        date=date_for_invoice if date_for_invoice else datetime.date.today(),
        isDraft=True,
        gross=False,
        description="Gerätenutzung",
        isRequest=False,
        taxRate=0.00,
        receiver=name,
        kind="revenue",
    )
    try:
        invoice = ev_connection.invoice.create(invoice_model)
    except Exception as e:
        logging.error("Error creating invoice", exc_info=True)
        return
    try:
        ev_connection.invoice.upload_attachment(invoice=invoice, file=file)
        logging.info(invoice)
    except Exception as e:
        logging.error("Error uploading invoice", exc_info=True)
        return
    try:
        update_data = InvoiceUpdate(
            isDraft=False,
            selectionAcc=186457852,
            paymentInformation='cash' if isCash else 'debit',
            #isCash?'cash':'card',
        )
        invoice = ev_connection.invoice.update(target=invoice, data=update_data)
        logging.info(invoice)
    except Exception as e:
        logging.error("Error updating invoice", exc_info=True)
        return
    #invoice = ev_connection.invoice.create_with_attachment(invoice_model, file, True)
    #print(invoice)

def generate_unique_invoice_number():
    while True:
        invoice_number = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if not invoice_number_exists(invoice_number):
            return invoice_number


def invoice_number_exists(invoice_number):
    if not os.path.exists(CSV_FILE_PATH):
        return False
    with open(CSV_FILE_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["rechnungsnummer"] == invoice_number:
                return True
    return False


def write_to_csv(data_dict):
    file_exists = os.path.exists(CSV_FILE_PATH)
    with open(CSV_FILE_PATH, "a", newline="", encoding="utf-8-sig") as f:
        fieldnames = [
            "datum",
            "rechnungsnummer",
            "name",
            "mitgliedsstatus",
            "zahlungsmethode",
            "bezahlter_betrag",
            "berechneter_gesamtpreis",
            "spendenbetrag",
            "positionen",
            "notiz"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_dict)


def generate_pdf_receipt(data_dict, effective_datetime_obj):
    """
    Erzeugt einen PDF-Beleg anhand der Eintragsdaten und einer Vorlage aus beleg.json.
    Der PDF-Name basiert auf dem aktuellen Zeitstempel.
    """
    # Lade die Vorlage
    with open("beleg.json", "r", encoding="utf-8") as f:
        beleg_template = json.load(f)

    # Erstelle einen Dateinamen anhand des Zeitstempels
    #data_dict.get('datum')
    timestamp = effective_datetime_obj.strftime("%d%m%Y%H%M%S")
    #timestamp = data_dict.get('datum').strftime("%d.%m.%Y %H:%M:%S")
    pdf_filename = os.path.join("pdfs", f"{timestamp}.pdf")
    os.makedirs("pdfs", exist_ok=True)

    c = canvas.Canvas(pdf_filename, pagesize=A4)
    width, height = A4

    # HEADER
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 50, beleg_template.get("header", "Beleg / Receipt"))
    c.setLineWidth(1)
    c.line(50, height - 60, width - 50, height - 60)

    # RECHNUNGSINFORMATIONEN (oben)
    c.setFont("Helvetica", 12)
    invoice_start_y = height - 100
    invoice_text = c.beginText(50, invoice_start_y)
    invoice_lines = [
        f"Datum: {data_dict.get('datum')}",
        f"Rechnungsnummer: {data_dict.get('rechnungsnummer') or '-'}",
        f"Name: {data_dict.get('name')}",
        f"Mitgliedsstatus: {data_dict.get('mitgliedsstatus')}",
        f"Zahlungsmethode: {data_dict.get('zahlungsmethode')}",
        f"Bezahlter Betrag: {data_dict.get('bezahlter_betrag')} €",
        f"Berechneter Gesamtpreis: {data_dict.get('berechneter_gesamtpreis')} €",
        f"Spendenbetrag: {data_dict.get('spendenbetrag')} €",
        "Positionen:"
    ]
    for line in invoice_lines:
        invoice_text.textLine(line)

    # Positionen: Aufsplitten und jede in einer neuen Zeile anzeigen
    positions_field = data_dict.get("positionen", "")
    if positions_field and positions_field != "Keine Positionen":
        for pos_line in positions_field.split("; "):
            invoice_text.textLine("  " + pos_line)
    else:
        invoice_text.textLine("  Keine Positionen")

    invoice_text.textLine(f"Notiz: {data_dict.get('notiz')}")
    c.drawText(invoice_text)

    # KONTAKT & REGISTER (unten, oberhalb des Footers)
    contact_start_y = 150
    contact_text = c.beginText(50, contact_start_y)
    recipient = beleg_template.get("recipient", {})
    contact_text.textLine("Kontakt:")
    contact_info = recipient.get("contact", {})
    contact_text.textLine(f"  Telefon: {contact_info.get('Telefon', '')}")
    contact_text.textLine(f"  E-Mail: {contact_info.get('E-Mail', '')}")
    contact_text.textLine("")
    contact_text.textLine("Registereintrag:")
    register_info = recipient.get("register", {})
    contact_text.textLine(f"  Registergericht: {register_info.get('Registergericht', '')}")
    contact_text.textLine(f"  Registernummer: {register_info.get('Registernummer', '')}")
    c.drawText(contact_text)

    # FOOTER
    c.setFont("Helvetica-Oblique", 10)
    c.drawCentredString(width / 2, 40, beleg_template.get("footer", "Vielen Dank für Ihre Nutzung!"))

    c.showPage()
    c.save()
    return pdf_filename


@app.route("/abrechnungen.csv")
def download_abrechnungen():
    if os.path.exists(CSV_FILE_PATH):
        return send_file(
            CSV_FILE_PATH,
            mimetype="text/csv",
            as_attachment=True,
            download_name="abrechnungen.csv"
        )
    else:
        flash("Die Datei 'abrechnungen.csv' wurde nicht gefunden.", "error")
        return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Allgemeine Formularfelder
        name = request.form.get("name", "").strip()
        mitgliedsstatus = request.form.get("mitgliedsstatus", "Nichtmitglied").strip()
        zahlungsmethode = request.form.get("zahlungsmethode", "Bar").strip()
        bezahlter_betrag = float(request.form.get("bezahlter_betrag", 0.0))
        notiz = request.form.get("notiz", "").strip()

        # Alle Positionen auslesen
        position_names = []
        mengen = []
        for key, val in request.form.items():
            # Debug: print(key, val)
            if key.startswith("position_name_"):
                index = key.split("_")[2]
                position_names.append((index, val.strip()))
            elif key.startswith("menge_"):
                index = key.split("_")[1]
                mengen.append((index, val.strip()))

        position_names.sort(key=lambda x: x[0])
        mengen.sort(key=lambda x: x[0])

        positions = []
        for (idx_name, device_name), (idx_menge, menge_str) in zip(position_names, mengen):
            try:
                menge_val = float(menge_str)
            except ValueError:
                menge_val = 0.0
            positions.append((device_name, menge_val))

        status_idx = membership_index.get(mitgliedsstatus, 0)

        # Erster Durchlauf: Finde den höchsten Tagespauschalenpreis
        max_daily = 0.0
        for device_name, _ in positions:
            if not device_name:
                continue
            device_entry = next((item for item in price_data if item["name"] == device_name), None)
            if not device_entry:
                continue
            einheit = device_entry["Einheit"]
            if "tagespauschale" in einheit.lower():
                preis = device_entry["kosten"][status_idx]
                if preis > max_daily:
                    max_daily = preis

        # Zweiter Durchlauf: Berechne Gesamtsumme & erstelle CSV-Liste
        gesamtpreis = 0.0
        positions_for_csv = []
        daily_counted = False

        for device_name, menge_val in positions:
            if not device_name:
                continue
            device_entry = next((item for item in price_data if item["name"] == device_name), None)
            if not device_entry:
                continue
            preis_pro_einheit = device_entry["kosten"][status_idx]
            einheit = device_entry["Einheit"]

            if "tagespauschale" in einheit.lower():
                if not daily_counted and preis_pro_einheit == max_daily:
                    item_gesamt = preis_pro_einheit
                    daily_counted = True
                else:
                    item_gesamt = 0.0
            else:
                item_gesamt = preis_pro_einheit * menge_val

            gesamtpreis += item_gesamt
            positions_for_csv.append(f"{device_name} x {menge_val} => {item_gesamt:.2f}€")

        if not positions_for_csv:
            positions_field = "Keine Positionen"
        else:
            positions_field = "; ".join(positions_for_csv)

        spende = 0.0
        if bezahlter_betrag > gesamtpreis:
            spende = bezahlter_betrag - gesamtpreis

        rechnungsnummer = request.form.get("rechnungsnummer", "").strip();
        #if zahlungsmethode.lower() == "karte":
        #    rechnungsnummer = generate_unique_invoice_number()

        custom_date_str = request.form.get("custom_date", "").strip()
        if custom_date_str:
            try:
                custom_date_obj = datetime.datetime.strptime(custom_date_str, "%Y-%m-%d")
                # Combine parsed date with current time
                effective_datetime_obj = datetime.datetime.combine(custom_date_obj.date(), datetime.datetime.now().time())
            except ValueError:
                effective_datetime_obj = datetime.datetime.now()  # Fallback to now if parsing fails
        else:
            effective_datetime_obj = datetime.datetime.now()  # Default to now if custom_date is empty

        data_dict = {
            "datum": effective_datetime_obj.strftime("%d.%m.%Y %H:%M:%S"),
            "rechnungsnummer": rechnungsnummer,
            "name": name,
            "mitgliedsstatus": mitgliedsstatus,
            "zahlungsmethode": zahlungsmethode,
            "bezahlter_betrag": f"{bezahlter_betrag:.2f}",
            "berechneter_gesamtpreis": f"{gesamtpreis:.2f}",
            "spendenbetrag": f"{spende:.2f}",
            "positionen": positions_field,
            "notiz": notiz
        }
        write_to_csv(data_dict)

        # PDF-Beleg generieren
        pdf_file = generate_pdf_receipt(data_dict, effective_datetime_obj)
        create_invoice_with_attachment(Path(pdf_file), bezahlter_betrag, zahlungsmethode.lower() == "bar", name, date_for_invoice=effective_datetime_obj.date())
        flash(
            f"Abrechnung gespeichert! bezahlter Betrag: {bezahlter_betrag:.2f} €, Spende: {spende:.2f}, Rechnungsnr.: {rechnungsnummer}. PDF: {os.path.basename(pdf_file)}", "success")
        return redirect(url_for("index"))
    auth_active = is_authenticated()
    return render_template("index.html", price_data=price_data, auth_active=auth_active)

@app.route("/api/generate_invoice_number")
def generate_invoice_number_api():
    invoice_number = generate_unique_invoice_number()
    return jsonify({"invoice_number": invoice_number})


### Einfacher HTTP Basic Auth Schutz ###
def check_auth(username, password):
    return username == os.getenv("ADMIN_USERNAME", "admin") and password == os.getenv("ADMIN_PASSWORD", "secret")


def authenticate():
    return Response(
        'Zugriff verweigert. Bitte melden Sie sich an.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated

def is_authenticated():
    auth = request.authorization
    return auth and check_auth(auth.username, auth.password)


### Route für den Admin-Bereich ###
@app.route("/admin", methods=["GET", "POST"])
@requires_auth
def admin():
    today = datetime.date.today()
    default_from = today - datetime.timedelta(days=7)

    if request.method == "POST":
        filter_from = request.form.get("from")
        filter_to = request.form.get("to")
    else:
        filter_from = request.args.get("from")
        filter_to = request.args.get("to")

    try:
        from_date = datetime.datetime.strptime(filter_from, "%Y-%m-%d").date() if filter_from else default_from
    except Exception:
        from_date = default_from
    try:
        to_date = datetime.datetime.strptime(filter_to, "%Y-%m-%d").date() if filter_to else today
    except Exception:
        to_date = today

    entries = []
    if os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    dt = datetime.datetime.strptime(row["datum"], "%d.%m.%Y %H:%M:%S")
                except Exception:
                    continue
                if from_date <= dt.date() <= to_date:
                    timestamp = dt.strftime("%d%m%Y%H%M%S")
                    row["pdf_filename"] = f"{timestamp}.pdf"
                    entries.append(row)

    bar_entries = [e for e in entries if e["zahlungsmethode"].lower() == "bar"]
    card_entries = [e for e in entries if e["zahlungsmethode"].lower() == "karte"]

    def calc_sums(group):
        usage = round(sum(float(e.get("berechneter_gesamtpreis", "0").replace(",", ".") or 0) for e in group), 2)
        spenden = round(sum(float(e.get("spendenbetrag", "0").replace(",", ".") or 0) for e in group), 2)
        total = round(usage + spenden, 2)
        return usage, spenden, total

    bar_usage, bar_spenden, bar_total = calc_sums(bar_entries)
    card_usage, card_spenden, card_total = calc_sums(card_entries)

    # === KATEGORIEN-Mapping vorbereiten ===
    kategorien_map = {}
    for eintrag in price_data:
        kategorie = eintrag.get("kategorie", "").strip() or "Sonstiges"
        kategorien_map[eintrag["name"]] = kategorie

    def kategorien_auswertung(eintraege):
        k_data = {}
        for entry in eintraege:
            datum = entry["datum"]
            filename = entry["pdf_filename"]
            person = entry["name"]
            positionen_text = entry.get("positionen", "")
            if positionen_text == "Keine Positionen":
                continue

            # === SPENDEN ===
            try:
                spende = float(entry.get("spendenbetrag", "0").replace(",", "."))
            except Exception:
                spende = 0.0
            if spende > 0:
                k_data.setdefault("Spenden", []).append({
                    "datum": datum,
                    "filename": filename,
                    "betrag": round(spende, 2),
                    "geraet": "Spende",
                    "name": person
                })

            # === POSITIONEN ===
            for pos in positionen_text.split("; "):
                if "=>" not in pos:
                    continue
                try:
                    name_menge, betrag_str = pos.split("=>")
                    betrag = float(betrag_str.strip().replace("€", "").replace(",", "."))
                    if betrag == 0:
                        continue
                    gerätename = name_menge.split("x")[0].strip()
                except Exception:
                    continue

                kategorie = kategorien_map.get(gerätename, "Sonstiges")
                k_data.setdefault(kategorie, []).append({
                    "datum": datum,
                    "filename": filename,
                    "betrag": round(betrag, 2),
                    "geraet": gerätename,
                    "name": person
                })

        # Farben für Rechnungen
        for kategorie, eintraege in k_data.items():
            eintraege.sort(key=lambda x: (x["filename"], x["datum"]))
            current_color = 0
            last_filename = None
            for eintrag in eintraege:
                fn = eintrag["filename"]
                if fn != last_filename:
                    current_color += 1
                    last_filename = fn
                eintrag["farbe"] = current_color % 2
        return k_data

    kategorien_daten_bar = kategorien_auswertung(bar_entries)
    kategorien_daten_karte = kategorien_auswertung(card_entries)

    kategorien_summen_bar = {
        k: round(sum(e["betrag"] for e in v), 2)
        for k, v in kategorien_daten_bar.items()
    }
    kategorien_summen_karte = {
        k: round(sum(e["betrag"] for e in v), 2)
        for k, v in kategorien_daten_karte.items()
    }

    return render_template(
        "admin.html",
        from_date=from_date.strftime("%Y-%m-%d"),
        to_date=to_date.strftime("%Y-%m-%d"),
        bar_entries=bar_entries,
        card_entries=card_entries,
        bar_usage=bar_usage,
        bar_spenden=bar_spenden,
        bar_total=bar_total,
        card_usage=card_usage,
        card_spenden=card_spenden,
        card_total=card_total,
        kategorien_daten_bar=kategorien_daten_bar,
        kategorien_summen_bar=kategorien_summen_bar,
        kategorien_daten_karte=kategorien_daten_karte,
        kategorien_summen_karte=kategorien_summen_karte
    )



@app.route("/delete-entry", methods=["POST"])
@requires_auth
def delete_entry():
    timestamp = request.form.get("timestamp")
    rechnungsnummer = request.form.get("rechnungsnummer")

    if not timestamp:
        flash("Kein Zeitstempel angegeben.", "error")
        return redirect(url_for("admin"))

    try:
        dt = datetime.datetime.strptime(timestamp, "%d.%m.%Y %H:%M:%S")
        pdf_name = dt.strftime("%d%m%Y%H%M%S") + ".pdf"
    except Exception:
        flash("Ungültiges Datumsformat.", "error")
        return redirect(url_for("admin"))

    # 1. CSV neu schreiben ohne den zu löschenden Eintrag
    entries = []
    if os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["datum"] != timestamp:
                    entries.append(row)

    # Überschreibe Datei
    with open(CSV_FILE_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "datum",
            "rechnungsnummer",
            "name",
            "mitgliedsstatus",
            "zahlungsmethode",
            "bezahlter_betrag",
            "berechneter_gesamtpreis",
            "spendenbetrag",
            "positionen",
            "notiz"
        ])
        writer.writeheader()
        writer.writerows(entries)

    # 2. PDF löschen (falls vorhanden)
    pdf_path = os.path.join("pdfs", pdf_name)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)

    flash(f"Eintrag vom {timestamp} wurde gelöscht.", "success")
    return redirect(url_for("admin"))

def find_invoice_in_csv(timestamp_str, rechnungsnummer):
    invoice_data = None
    if os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Vergleiche den Datums-Teil des Timestamps und die Rechnungsnummer
                if row["datum"] == timestamp_str and row["rechnungsnummer"] == rechnungsnummer:
                    invoice_data = row
                    break
    return invoice_data

@app.route("/recreate-invoice", methods=["POST"])
@requires_auth
def recreate_invoice():
    timestamp_str = request.form.get("timestamp")
    rechnungsnummer = request.form.get("rechnungsnummer")

    if not timestamp_str or not rechnungsnummer:
        flash("Fehlende Parameter: Zeitstempel und Rechnungsnummer sind erforderlich.", "error")
        return redirect(request.referrer or url_for("admin"))
    
    invoice_data = find_invoice_in_csv(timestamp_str, rechnungsnummer)

    if not invoice_data:
        flash(f"Rechnung nicht gefunden für Zeitstempel {timestamp_str} and Rechnungsnummer {rechnungsnummer}.", "error")
        return redirect(request.referrer or url_for("admin"))
    
    effective_datetime_obj = datetime.datetime.strptime(timestamp_str, "%d.%m.%Y %H:%M:%S")
    pdf_file = generate_pdf_receipt(invoice_data, effective_datetime_obj)

    flash(f"PDF recreated at {pdf_file}")
    return redirect(request.referrer or url_for("admin"))

@app.route("/reupload-invoice", methods=["POST"])
@requires_auth
def reupload_invoice():
    timestamp_str = request.form.get("timestamp")
    rechnungsnummer = request.form.get("rechnungsnummer")

    if not timestamp_str or not rechnungsnummer:
        flash("Fehlende Parameter: Zeitstempel und Rechnungsnummer sind erforderlich.", "error")
        return redirect(request.referrer or url_for("admin"))

    # Finde den Eintrag in der CSV
    invoice_data = find_invoice_in_csv(timestamp_str, rechnungsnummer)

    if not invoice_data:
        flash(f"Rechnung nicht gefunden für Zeitstempel {timestamp_str} and Rechnungsnummer {rechnungsnummer}.", "error")
        return redirect(request.referrer or url_for("admin"))

    pdf_filename_short = invoice_data.get("pdf_filename") # This comes from admin view, needs to be constructed if not present
    if not pdf_filename_short:
        # Konstruiere pdf_filename aus timestamp wenn nicht direkt in CSV (sollte aber da sein via admin view)
        try:
            dt_obj = datetime.datetime.strptime(timestamp_str, "%d.%m.%Y %H:%M:%S")
            pdf_filename_short = dt_obj.strftime("%d%m%Y%H%M%S") + ".pdf"
        except ValueError:
            flash("Ungültiges Zeitstempelformat in den Daten.", "error")
            return redirect(request.referrer or url_for("admin"))

    pdf_full_path = Path("pdfs") / pdf_filename_short

    if not pdf_full_path.exists():
        flash(f"PDF-Datei {pdf_filename_short} nicht gefunden.", "error")
        return redirect(request.referrer or url_for("admin"))

    try:
        total_price = float(invoice_data["bezahlter_betrag"].replace(",", "."))
    except ValueError:
        flash("Ungültiger Betrag in Rechnungsdaten.", "error")
        return redirect(request.referrer or url_for("admin"))

    is_cash = invoice_data["zahlungsmethode"].lower() == "bar"
    name = invoice_data["name"]

    try:
        create_invoice_with_attachment(pdf_full_path, total_price, is_cash, name,
                                       date_for_invoice=datetime.datetime.strptime(invoice_data["datum"], "%d.%m.%Y %H:%M:%S").date())
        flash(f"Rechnung {rechnungsnummer} erfolgreich erneut zu EasyVerein hochgeladen.", "success")
    except Exception as e:
        logging.error(f"Fehler beim erneuten Hochladen der Rechnung {rechnungsnummer}: {e}", exc_info=True)
        flash(f"Fehler beim erneuten Hochladen der Rechnung: {e}", "error")
#zurück zu der seite von der er kam
    return redirect(request.referrer or url_for("admin"))


### Route zum Download einer PDF ###
@app.route("/download/<filename>")
@requires_auth
def download_pdf(filename):
    pdf_path = os.path.join("pdfs", filename)
    if os.path.exists(pdf_path):
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=filename
        )
    else:
        flash("Die PDF-Datei wurde nicht gefunden.", "error")
        return redirect(url_for("admin"))


if __name__ == "__main__":
    config = load_config()
    api_key = config["APIKEY"]

    #c = EasyvereinAPI(api_key=api_key, api_version='v2.0')#token_refresh_callback=handle_token_refresh, auto_refresh_token=True,
    #print(c.invoice.get_by_id("190212712"))
    #print(c.invoice.get_by_id("261090770"))
    #print(c.invoice.get_by_id("260614666"))
    #for n in c.invoice.get_all():
    #    print(n)

    #exit(0)
    #check if file exists
    #test_create_invoice_with_attachment(c, Path("pdfs/28032025131031.pdf"), 1.00)
    app.run(debug=True, host='0.0.0.0')
