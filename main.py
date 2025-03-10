import csv
from datetime import datetime
import os
import json
import random
import string
import math
from flask import Flask, render_template, request, redirect, url_for, flash, send_file

app = Flask(__name__)
app.secret_key = "ersetzen_durch_einen_geheimen_schluessel"

CSV_FILE_PATH = "abrechnungen.csv"
PRICES_JSON_PATH = "Preise.json"

with open(PRICES_JSON_PATH, "r", encoding="utf-8") as f:
    price_data = json.load(f)

# Mapping: Wir gehen davon aus, dass price_data[x]["kosten"]
# in der Reihenfolge [Nichtmitglied, Fördermitglied, Ordentliches Mitglied] steht.
membership_index = {
    "Nichtmitglied": 0,
    "Fördermitglied": 1,
    "Ordentliches Mitglied": 2
}

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
    with open(CSV_FILE_PATH, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "datum",
            "rechnungsnummer",
            "name",
            "mitgliedsstatus",
            "zahlungsmethode",
            "bezahlter_betrag",
            "positionen",
            "berechneter_gesamtpreis",
            "spendenbetrag",
            "notiz"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_dict)

@app.route("/abrechnungen.csv")
def download_abrechnungen():
    if os.path.exists(CSV_FILE_PATH):
        return send_file(
            CSV_FILE_PATH,
            mimetype="text/csv",
            as_attachment=True,
            download_name="abrechnungen.csv"  # für Flask 2.x; bei älteren Versionen: attachment_filename="abrechnungen.csv"
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
            # Debug-Ausgabe (kann entfernt werden)
            print(key, val)
            if key.startswith("position_name_"):
                index = key.split("_")[2]
                position_names.append((index, val.strip()))
            elif key.startswith("menge_"):
                index = key.split("_")[1]
                mengen.append((index, val.strip()))

        # Sortieren nach Index, damit die Reihenfolge stimmt
        position_names.sort(key=lambda x: x[0])
        mengen.sort(key=lambda x: x[0])

        # Paare bilden
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

            # Berechnung je nach Einheit
            if "tagespauschale" in einheit.lower():
                if not daily_counted and preis_pro_einheit == max_daily:
                    item_gesamt = preis_pro_einheit
                    daily_counted = True
                else:
                    item_gesamt = 0.0
            elif "angefangene 10 minuten" in einheit.lower():
                parted = math.ceil(menge_val / 10.0)
                item_gesamt = parted * preis_pro_einheit
            elif "1/2h" in einheit.lower():
                parted = math.ceil(menge_val / 0.5)
                item_gesamt = parted * preis_pro_einheit
            else:
                item_gesamt = preis_pro_einheit * menge_val

            gesamtpreis += item_gesamt
            positions_for_csv.append(f"{device_name} x {menge_val} => {item_gesamt:.2f}€")

        # Spende berechnen
        spende = 0.0
        if bezahlter_betrag > gesamtpreis:
            spende = bezahlter_betrag - gesamtpreis

        # Rechnungsnummer nur bei Kartenzahlung
        rechnungsnummer = ""
        if zahlungsmethode.lower() == "karte":
            rechnungsnummer = generate_unique_invoice_number()

        data_dict = {
            "datum": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "rechnungsnummer": rechnungsnummer,
            "name": name,
            "mitgliedsstatus": mitgliedsstatus,
            "zahlungsmethode": zahlungsmethode,
            "bezahlter_betrag": f"{bezahlter_betrag:.2f}",
            "positionen": "; ".join(positions_for_csv),
            "berechneter_gesamtpreis": f"{gesamtpreis:.2f}",
            "spendenbetrag": f"{spende:.2f}",
            "notiz": notiz
        }
        write_to_csv(data_dict)

        flash(f"Abrechnung gespeichert! Gesamtpreis: {gesamtpreis:.2f} €, Spende: {spende:.2f}, Rechnungsnr.: {rechnungsnummer}")
        return redirect(url_for("index"))

    return render_template("index.html", price_data=price_data)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
