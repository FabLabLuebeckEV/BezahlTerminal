import csv
import os
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

app = Flask(__name__)
app.secret_key = "ersetzen_durch_einen_geheimen_schluessel"

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

def handle_token_refresh(token):
    print("Refreshing token")
    print(token)
    config['APIKEY'] = token
    with open('config.json', 'w') as filee:
        json.dump(config, filee)


def create_invoice_with_attachment(file: Path, totalPrice: float, isCash: bool = True):
    ev_connection = EasyvereinAPI(api_key=api_key,
                      api_version='v2.0', token_refresh_callback=handle_token_refresh, auto_refresh_token=True)  # token_refresh_callback=handle_token_refresh, auto_refresh_token=True,
    # Create a invoice
    invoice_model = InvoiceCreate(
        invNumber=file.stem,
        totalPrice=totalPrice,
        date=datetime.date.today(),
        isDraft=True,
        gross=False,
        description="Gerätenutzung",
        isRequest=False,
        taxRate=0.00,
        receiver="Sammelnutzer",
        kind="revenue",
    )
    try:
        invoice = ev_connection.invoice.create(invoice_model)
    except Exception as e:
        print(e)
        return
    try:
        ev_connection.invoice.upload_attachment(invoice=invoice, file=file)
        print(invoice)
    except Exception as e:
        print(e)
        return
    try:
        update_data = InvoiceUpdate(
            isDraft=False,
            selectionAcc=186457852,
            paymentInformation='cash' if isCash else 'debit',
            #isCash?'cash':'card',
        )
        invoice = ev_connection.invoice.update(target=invoice, data=update_data)
        print(invoice)
    except Exception as e:
        print(e)
        return
    #invoice = ev_connection.invoice.create_with_attachment(invoice_model, file, True)

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


def generate_pdf_receipt(data_dict):
    """
    Erzeugt einen PDF-Beleg anhand der Eintragsdaten und einer Vorlage aus beleg.json.
    Der PDF-Name basiert auf dem aktuellen Zeitstempel.
    """
    # Lade die Vorlage
    with open("beleg.json", "r", encoding="utf-8") as f:
        beleg_template = json.load(f)

    # Erstelle einen Dateinamen anhand des Zeitstempels
    timestamp = datetime.datetime.now().strftime("%d%m%Y%H%M%S")
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
        flash("Die Datei 'abrechnungen.csv' wurde nicht gefunden.")
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

        data_dict = {
            "datum": datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
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
        pdf_file = generate_pdf_receipt(data_dict)
        create_invoice_with_attachment(Path(pdf_file), gesamtpreis, zahlungsmethode.lower() == "bar")
        flash(
            f"Abrechnung gespeichert! Gesamtpreis: {gesamtpreis:.2f} €, Spende: {spende:.2f}, Rechnungsnr.: {rechnungsnummer}. PDF: {os.path.basename(pdf_file)}")
        return redirect(url_for("index"))

    return render_template("index.html", price_data=price_data)

@app.route("/api/generate_invoice_number")
def generate_invoice_number_api():
    invoice_number = generate_unique_invoice_number()
    return jsonify({"invoice_number": invoice_number})


### Einfacher HTTP Basic Auth Schutz ###
def check_auth(username, password):
    return username == "admin" and password == "secret"


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
        card_total=card_total
    )


### Route zum Download einer PDF ###
@app.route("/download/<filename>")
@requires_auth
def download_pdf(filename):
    pdf_path = os.path.join("pdfs", filename)
    if os.path.exists(pdf_path):
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    else:
        flash("Die PDF-Datei wurde nicht gefunden.")
        return redirect(url_for("admin"))


if __name__ == "__main__":
    with open('config.json', 'r') as file:
        config = json.load(file)
    api_key = config['APIKEY']

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
