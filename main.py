import csv
import os
import json
import random
import string
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "ersetzen_durch_einen_geheimen_schluessel"

CSV_FILE_PATH = "abrechnungen.csv"
PRICES_JSON_PATH = "Preise.json"

with open(PRICES_JSON_PATH, "r", encoding="utf-8") as f:
    price_data = json.load(f)

# Mapping: So interpretieren wir die Indizes in price_data[x]["kosten"]
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
            "rechnungsnummer",
            "name",
            "mitgliedsstatus",
            "zahlungsmethode",
            "bezahlter_betrag",
            "positionen",
            "berechneter_gesamtpreis",
            "spendenbetrag"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data_dict)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Allgemeine Formularfelder
        name = request.form.get("name", "").strip()
        mitgliedsstatus = request.form.get("mitgliedsstatus", "Nichtmitglied").strip()
        zahlungsmethode = request.form.get("zahlungsmethode", "Bar").strip()
        bezahlter_betrag = float(request.form.get("bezahlter_betrag", 0.0))

        # Alle Positionen auslesen
        # Wir suchen z.B. nach feldern "position_name_0, position_name_1, ..." und "menge_0, menge_1, ...".
        # Dann bauen wir uns die Listen zusammen.
        position_names = []
        mengen = []

        for key, val in request.form.items():
            if key.startswith("position_name_"):
                # extrahiere index
                index = key.split("_")[2]
                position_names.append((index, val.strip()))
            elif key.startswith("menge_"):
                index = key.split("_")[1]
                mengen.append((index, val.strip()))

        # Sortieren nach index, damit die Reihenfolge stimmt
        position_names.sort(key=lambda x: x[0])
        mengen.sort(key=lambda x: x[0])

        # Paare bilden
        positions = []
        for (idx_name, device_name), (idx_menge, menge_str) in zip(position_names, mengen):
            # menge konvertieren
            menge_val = 0.0
            try:
                menge_val = float(menge_str)
            except:
                menge_val = 0.0
            positions.append((device_name, menge_val))

        # Jetzt berechnen wir die Gesamtsumme
        status_idx = membership_index.get(mitgliedsstatus, 0)
        gesamtpreis = 0.0

        # Wir bauen uns auch eine Liste für die CSV (Welche Geräte und Mengen)
        positions_for_csv = []

        for device_name, menge_val in positions:
            if not device_name:
                continue  # Überspringen

            # Suche Eintrag in price_data
            device_entry = next((item for item in price_data if item["name"] == device_name), None)
            if not device_entry:
                # Unbekanntes Gerät
                continue

            preis_pro_einheit = device_entry["kosten"][status_idx]
            einheit = device_entry["Einheit"]

            # Tagespauschale
            if "Tagespauschale" in einheit:
                item_gesamt = preis_pro_einheit
            elif "angefangene 10 Minuten" in einheit.lower():
                # Beispiel: "pro angefangene 10 Minuten" => wir runden menge_val / 10 auf
                # Hier vereinfachter Ansatz: menge_val (vermutlich Min.) -> parted = ceil(menge_val / 10)
                import math
                parted = math.ceil(menge_val / 10.0)
                item_gesamt = parted * preis_pro_einheit
            elif "1/2h" in einheit.lower():
                # z.B. "Pro 1/2h" => menge_val in Minuten? in Stunden?
                # Das hängt von deiner Definition ab.
                # Angenommen menge_val ist in Stunden, dann parted = ceil(menge_val / 0.5)
                import math
                parted = math.ceil(menge_val / 0.5)
                item_gesamt = parted * preis_pro_einheit
            else:
                # Normal: preis_pro_einheit * menge_val
                item_gesamt = preis_pro_einheit * menge_val

            gesamtpreis += item_gesamt
            positions_for_csv.append(f"{device_name} x {menge_val} => {item_gesamt:.2f}€")

        # Spende
        spende = 0.0
        if bezahlter_betrag > gesamtpreis:
            spende = bezahlter_betrag - gesamtpreis

        # Rechnungsnummer nur bei Karte
        rechnungsnummer = ""
        if zahlungsmethode.lower() == "karte":
            rechnungsnummer = generate_unique_invoice_number()

        data_dict = {
            "rechnungsnummer": rechnungsnummer,
            "name": name,
            "mitgliedsstatus": mitgliedsstatus,
            "zahlungsmethode": zahlungsmethode,
            "bezahlter_betrag": f"{bezahlter_betrag:.2f}",
            "positionen": "; ".join(positions_for_csv),  # z.B. "FDM x 2 => 2.00€; Laser x 1 => 4.00€"
            "berechneter_gesamtpreis": f"{gesamtpreis:.2f}",
            "spendenbetrag": f"{spende:.2f}"
        }
        write_to_csv(data_dict)

        flash(f"Abrechnung gespeichert! Gesamtpreis: {gesamtpreis:.2f} €, Spende: {spende:.2f}, Rechnungsnr.: {rechnungsnummer}")
        return redirect(url_for("index"))

    # GET: Formular anzeigen
    # Übergib price_data ans Template (Jinja2)
    return render_template("index.html", price_data=price_data)

if __name__ == "__main__":
    app.run(debug=True)