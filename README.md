# FabLab Lübeck Abrechnungstool

Dieses Projekt ist ein webbasiertes Python/Flask-Tool, um die Abrechnung der Maschinen- und Materialnutzung im FabLab Lübeck zu digitalisieren. Nutzerinnen und Nutzer können Geräte, Material und Zeit eingeben, die jeweils automatisch bepreist werden. Anschließend wird in Echtzeit eine Zwischensumme angezeigt, und die Zahlung (Bar oder Karte) wird erfasst. Beim Bezahlen mit Karte wird eine Rechnungsnummer generiert, die auf einem externen SumUp-Terminal eingegeben werden kann.

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)  
2. [Projektstruktur](#projektstruktur)  
3. [Installation & Start](#installation--start)  
4. [Funktionen](#funktionen)  
   - [Abrechnung mehrerer Positionen](#abrechnung-mehrerer-positionen)  
   - [Tagespauschale & Speziallogiken](#tagespauschale--speziallogiken)  
   - [Live-Berechnung und Spende](#live-berechnung-und-spende)  
   - [Karte vs. Barzahlung](#karte-vs-barzahlung)  
   - [CSV-Datenexport](#csv-datenexport)  
5. [Dateiübersicht & Logik](#dateiübersicht--logik)  
6. [Anpassen der Preise & Maschinenliste](#anpassen-der-preise--maschinenliste)  
7. [Nutzungshinweise](#nutzungshinweise)  
8. [Lizenz](#lizenz)

---

## Überblick

Das Tool ermöglicht Mitgliedern und Gästen des FabLabs, die Nutzung von Maschinen (z. B. Laser, 3D-Drucker, CNC-Fräse) mit verschiedenen Einheiten (z. B. **Tagespauschale**, **pro Stunde**, **pro angefangene X Minuten**) zu erfassen. Dabei werden die Kosten für unterschiedliche Mitgliedsstatus (Nichtmitglied, Fördermitglied, Ordentliches Mitglied) aus einer zentralen JSON-Datei ausgelesen. Die Abrechnungssummen werden in eine CSV-Datei geschrieben, die später für Vereinsabrechnungen genutzt wird.

---

## Projektstruktur

```
dein_projekt/
 ├─ Preise.json               # Zentrales JSON mit allen Maschinen & Preisen
 ├─ abrechnungen.csv          # CSV-Datei, in die alle Buchungen geschrieben werden
 ├─ app.py                    # Haupt-Flask-App (Backend)
 ├─ templates/
 │   └─ index.html            # Startseite / Web-Formular
 ├─ static/
 │   ├─ css/
 │   │   └─ styles.css        # Style-Definitionen
 │   └─ js/
 │       └─ script.js         # Clientseitige Logik (Dropdown, Live-Berechnung etc.)
 └─ README.md                 # Dieses Dokument
```

---

## Installation & Start

1. **Repository klonen**  
   ```bash
   git clone <URL-zum-Repository>
   cd dein_projekt
   ```

2. **Abhängigkeiten installieren**  
   > Voraussetzung: Python 3.x  
   ```bash
   pip install flask
   ```

3. **Preise.json anpassen** (siehe unten), falls nötig.

4. **Starten**  
   ```bash
   python app.py
   ```
   Danach ist das Tool typischerweise unter http://127.0.0.1:5000/ erreichbar.

---

## Funktionen

### Abrechnung mehrerer Positionen

Über die Weboberfläche können mehrere Maschinen/Positionen pro Abrechnungsvorgang hinzugefügt werden. Jede Position enthält:
- **Geräteauswahl** (Dropdown mit Filter)
- **Menge** (z. B. Stunden, Minuten, Gramm usw.)
- Automatisch eingeblendete **Einheit** (z. B. „Tagespauschale“, „pro Stunde“, …)
- Live-Preisberechnung basierend auf JSON-Daten

### Tagespauschale & Speziallogiken

- Einige Geräte werden unabhängig von der Menge als *Tagespauschale* abgerechnet.
- Andere Geräte haben Sonderregeln, z. B. „pro angefangene 10 Minuten“ (via Rundung im Code).

### Live-Berechnung und Spende

- Sobald eine Menge oder ein Gerät geändert wird, berechnet das Frontend sofort die **Zwischensumme**.
- Gibt der Nutzer mehr Geld als die Zwischensumme an, wird die Differenz als **Spende** ausgewiesen.

### Karte vs. Barzahlung

- Bei Kartenzahlung erscheint ein Hinweis, dass eine **4-stellige Rechnungsnummer** erzeugt wird.  
- Barzahlungen erfordern keine Rechnungsnummer (kann aber angepasst werden, falls gewünscht).

### CSV-Datenexport

- Jede Abrechnung wird in `abrechnungen.csv` gespeichert, inklusive:
  - **Rechnungsnummer** (bei Kartenzahlung)
  - **Gerätenamen**, **Menge**, **Einheit** und berechnetem Preis
  - **Mitgliedsstatus**, **Spende** etc.

---

## Dateiübersicht & Logik

1. **`app.py`**  
   - Lädt die Preisdaten aus `Preise.json`.  
   - Definiert die Flask-Routen:  
     - **GET /**: Rendert das Formular (`index.html`).  
     - **POST /**: Liest die Formulardaten (mehrere Positionen) aus, berechnet Gesamtpreis & Spende, schreibt in `abrechnungen.csv`.  
   - Enthält die **Logik** für „Tagespauschale“, „angefangene 10 Minuten“, „1/2h“ etc. (mit `math.ceil`, wenn gewünscht).  
   - Generiert eine 4-stellige Rechnungsnummer für Kartenzahlungen.  

2. **`Preise.json`**  
   - Liste von Maschinen/Material, z. B.:
     ```json
     [
       {
         "name": "E-Lab",
         "kosten": [1.0, 0.0, 0.0],
         "Einheit": "Tagespauschale"
       },
       ...
     ]
     ```
   - **Reihenfolge** in `kosten`: `[Nichtmitglied, Fördermitglied, Ordentliches Mitglied]` (oder wie auch immer ihr es definiert).  
   - **Einheit**: Gibt dem Code Hinweis, ob Tagespauschale, pro Stunde, pro angefangene X Minuten usw.

3. **`templates/index.html`**  
   - Enthält das Grundgerüst des Formulars.  
   - Bietet Eingabefelder für Name, Mitgliedsstatus, Zahlungsmethode, beliebig viele Geräteslots.  
   - Bindet `script.js` und `styles.css` ein.

4. **`static/js/script.js`**  
   - Clientseitiges JavaScript.  
   - Erzeugt dynamisch neue Formularzeilen, steuert das Filter-Dropdown, zeigt die Einheit an.  
   - **Live-Berechnung**: Summiert alle Positionen, blendet den Preis neben jeder Position ein und zeigt Spende/Endbetrag an.

5. **`static/css/styles.css`**  
   - Grundlegendes Layout & Styling des Formulars, Buttons, Dropdowns etc.

6. **`abrechnungen.csv`** (wird automatisch erstellt)  
   - Hier werden die finalen Daten gespeichert.  
   - Einträge enthalten Rechnungsnummer, Geräteübersicht, Gesamtpreis, Spendenbetrag usw.

---

## Anpassen der Preise & Maschinenliste

1. **Neue Geräte hinzufügen**  
   - Öffne `Preise.json` und füge einen neuen Eintrag hinzu, z. B.:
     ```json
     {
       "name": "NeueCNC",
       "kosten": [4.0, 2.0, 1.0],
       "Einheit": "pro Stunde"
     }
     ```
   - **Wichtig**: Achte auf die korrekte Reihenfolge der Werte in `kosten` und definiere `"Einheit"` passend zu eurer Abrechnungslogik.  

2. **Preise ändern**  
   - Einfach in `Preise.json` bei `"kosten"` den entsprechenden Wert anpassen.  
   - Bei Spezifika wie „pro angefangene X Minuten“, passe ggf. die Logik in `app.py` oder `script.js` an.

3. **Neue Einheit oder neue Rundungsregel**  
   - Wenn du eine neue Abrechnungsart hinzufügen möchtest (z. B. „pro angefangene 5 Minuten“), ergänze in `app.py` und `script.js` eine if-Abfrage, die diese Einheit erkennt und entsprechend rechnet (bspw. `math.ceil(menge / 5)`).

---

## Nutzungshinweise

1. **Lokale Entwicklung**:  
   - Starte die App in einer lokalen Umgebung (z. B. `python app.py`).  
   - Browser öffnen: http://127.0.0.1:5000/.

2. **Produktion/Hosting**:  
   - Für den produktiven Einsatz mit mehreren Nutzern empfiehlt es sich, einen richtigen Webserver (z. B. `gunicorn` + Nginx) zu konfigurieren.  
   - `debug=True` in `app.run(debug=True)` sollte in Produktion deaktiviert werden.

3. **Datensicherheit**:  
   - Die CSV-Datei `abrechnungen.csv` enthält persönliche Daten (Name, Zahlbeträge). Stelle sicher, dass der Schreib-/Lesezugriff geschützt ist (Dateirechte, kein öffentlicher Download, etc.).

4. **Kein strikter Schutz gegen Manipulation**:  
   - Der Preis wird **clientseitig** zur Anzeige berechnet, aber auch **serverseitig** wieder neu berechnet (gegen Manipulationsversuche).  
   - Achte darauf, dass du im Production-Code alle erforderlichen Sicherheitsmaßnahmen und Validierungen durchführst.

---

## Lizenz

*(Optional) Füge hier eine passende Lizenzinfo ein, z. B. MIT, GPL, etc.*  

Beispiel:

> Dieses Projekt steht unter der [MIT License](LICENSE). Du kannst es gerne forken, anpassen und für dein eigenes FabLab einsetzen.  
