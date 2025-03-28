/*
  In diesem Script:
  - Erzeugen wir dynamisch Zeilen für Positionen.
  - Jede Zeile hat name="position_name_X" und name="menge_X", damit sie im POST ankommen.
  - Beim Absenden wird der Button zu einem Progress-Indikator.
  - Zudem werden bei der Auswahl von bestimmten Geräten automatisch die entsprechenden Partnergeräte ergänzt.
*/

let positionCounter = 0;

// Mapping: Welcher Mitgliedsstatus -> Index im "kosten"-Array
const membershipIndexMap = {
  "Nichtmitglied": 0,
  "Fördermitglied": 1,
  "Ordentliches Mitglied": 2
};

// Definiere die Gerätepaare (für automatische Ergänzungen)
// Für FDM: Wenn irgendein "FDM-Drucker Material" gewählt wird, soll "FDM-Drucker" hinzugefügt werden.
// Umgekehrt: Wenn "FDM-Drucker" gewählt wird, soll "FDM-Drucker Material normal" hinzugefügt werden.
// Analog für SLA und UV.
const devicePairs = [
  { primary: "FDM-Drucker", secondary: "FDM-Drucker Material normal" },
  { primary: "SLA-Drucker", secondary: "SLA-Drucker Material" },
  { primary: "UV-Drucker", secondary: "UV-Drucker Reinigung" }
];

document.addEventListener("DOMContentLoaded", () => {
  setupHandlers();
  // Eine erste Position sofort hinzufügen
  addPositionRow();
  updateCardHinweis();
  recalcSummary();

  document.getElementById("billing-form").addEventListener("submit", (e) => {
  const rows = document.querySelectorAll(".position-row");
  let hasFilled = false;
  rows.forEach(row => {
    const input = row.querySelector(".dropdown-input");
    if (input && input.value.trim() !== "") {
      hasFilled = true;
    }
  });
  if (rows.length === 0 || !hasFilled) {
    e.preventDefault();
    alert("Es wurde keine Position ausgewählt. Bitte fügen Sie mindestens eine Position hinzu.");
    return;
  }

  // Falls Zahlungsmethode "Karte" ist, Bestätigungsdialog einblenden:
  const zahlungsmethode = document.getElementById("zahlungsmethode").value;
  if (zahlungsmethode.toLowerCase() === "karte") {
    const bezahlterBetrag = document.getElementById("bezahlter_betrag").value;
    // Hole alle gefüllten Positionen
    const positions = Array.from(document.querySelectorAll(".dropdown-input"))
                          .map(input => input.value.trim())
                          .filter(val => val !== "");
    const positionsText = positions.join(", ");
    const confirmMessage = `War die Bezahlung von ${bezahlterBetrag} € mit der Karte und dem Zweck "${document.getElementById("rechnungsnummer").innerText}" erfolgreich?`;
    if (!confirm(confirmMessage)) {
      e.preventDefault();
      return;
    }
  }

  // Submit-Button als Progress-Indikator setzen:
  const submitBtn = document.querySelector(".form-actions button");
  submitBtn.disabled = true;
  submitBtn.textContent = "Verarbeitung...";
});

function setupHandlers() {
  document.getElementById("add-position-btn").addEventListener("click", addPositionRow);

  document.getElementById("mitgliedsstatus").addEventListener("change", recalcSummary);
  document.getElementById("zahlungsmethode").addEventListener("change", () => {
    updateCardHinweis();
    recalcSummary();
  });
  document.getElementById("bezahlter_betrag").addEventListener("input", recalcSummary);
}

function updateCardHinweis() {
  const payMethod = document.getElementById("zahlungsmethode").value;
  const cardHinweis = document.getElementById("card-hinweis");
  const rnSpan = document.getElementById("rechnungsnummer");

  if (payMethod === "Karte") {
    cardHinweis.classList.remove("hidden");
    rnSpan.textContent = generateRechnungsnr();
  } else {
    cardHinweis.classList.add("hidden");
    rnSpan.textContent = "";
  }
}

function generateRechnungsnr() {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let result = "";
  for (let i = 0; i < 4; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

// Fügt eine neue Position-Row hinzu
function addPositionRow() {
  positionCounter++;
  const container = document.getElementById("positions-container");

  const rowDiv = document.createElement("div");
  rowDiv.classList.add("position-row");
  rowDiv.dataset.posId = positionCounter;

  rowDiv.innerHTML = `
    <div>
      <label>Gerät/Material:</label>
      <div class="dropdown-container">
        <input
          type="text"
          class="dropdown-input"
          name="position_name_${positionCounter}"
          placeholder="Gerät wählen..."
        />
        <div class="dropdown-list hidden"></div>
      </div>

      <label>Menge:</label>
      <input
        type="number"
        step="0.01"
        class="menge-input"
        name="menge_${positionCounter}"
        value="1"
        style="width:80px;"
      />

      <span class="einheit-span"></span>
      <span class="price-span">0.00 €</span>
      <button type="button" class="remove-btn">Entfernen</button>
    </div>
  `;

  // Remove-Handler
  rowDiv.querySelector(".remove-btn").addEventListener("click", () => {
    container.removeChild(rowDiv);
    recalcSummary();
  });

  // Setup fürs "Dropdown mit Filter"
  const dropdownInput = rowDiv.querySelector(".dropdown-input");
  const dropdownList = rowDiv.querySelector(".dropdown-list");

  dropdownInput.addEventListener("focus", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  dropdownInput.addEventListener("input", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  document.addEventListener("click", (evt) => {
    if (!rowDiv.contains(evt.target)) {
      dropdownList.classList.add("hidden");
    }
  });

  const mengeInput = rowDiv.querySelector(".menge-input");
  mengeInput.addEventListener("input", recalcSummary);

  container.appendChild(rowDiv);
  recalcSummary();
}

// Hilfsfunktion: Fügt eine neue Zeile hinzu und setzt den Gerätenamen
function addRowWithDevice(deviceName) {
  addPositionRow();
  const rows = document.querySelectorAll(".position-row");
  const lastRow = rows[rows.length - 1];
  if (lastRow) {
    lastRow.querySelector(".dropdown-input").value = deviceName;
    lastRow.querySelector(".dropdown-list").classList.add("hidden");
    recalcSummary();
  }
}

// Füllt das Dropdown mit gefilterten Einträgen
function fillDropdownList(listEl, filterValue) {
  const val = filterValue.toLowerCase().trim();
  listEl.innerHTML = "";

  const filteredItems = priceData.filter(item => item.name.toLowerCase().includes(val));
  filteredItems.forEach(item => {
    const divOpt = document.createElement("div");
    divOpt.classList.add("dropdown-option");
    divOpt.textContent = item.name;
    divOpt.addEventListener("click", () => {
      const parentRow = listEl.closest(".position-row");
      parentRow.querySelector(".dropdown-input").value = item.name;
      listEl.classList.add("hidden");
      recalcSummary();
      // Prüfe Geräte-Paar-Regeln
      checkPairRules(item.name);
    });
    listEl.appendChild(divOpt);
  });

  if (filteredItems.length === 0) {
    const divOpt = document.createElement("div");
    divOpt.classList.add("dropdown-option");
    divOpt.textContent = "Keine Treffer";
    divOpt.style.color = "#999";
    listEl.appendChild(divOpt);
  }
}

// Prüft, ob ein gepaartes Gerät ergänzt werden muss
function checkPairRules(selectedDevice) {
  devicePairs.forEach(pair => {
    // Für FDM: Falls der Secondary-Name als Teilstring im Namen vorkommt (z.B. "fdm-drucker material")
    if (selectedDevice.toLowerCase().includes("fdm-drucker material") && pair.primary === "FDM-Drucker") {
      // Prüfe, ob ein FDM-Drucker bereits existiert
      let found = false;
      document.querySelectorAll(".dropdown-input").forEach(input => {
        if (input.value.trim() === pair.primary) {
          found = true;
        }
      });
      if (!found) {
        addRowWithDevice(pair.primary);
      }
    }
    // Umgekehrt: Falls der Primary gewählt wird, füge den Secondary hinzu (nur für FDM und für die anderen exakte Vergleiche)
    else if (selectedDevice === pair.primary) {
      let found = false;
      document.querySelectorAll(".dropdown-input").forEach(input => {
        if (pair.primary === "FDM-Drucker") {
          // Für FDM, suche nach "fdm-drucker material" im Namen
          if (input.value.trim().toLowerCase().includes("fdm-drucker material")) {
            found = true;
          }
        } else {
          if (input.value.trim() === pair.secondary) {
            found = true;
          }
        }
      });
      if (!found) {
        addRowWithDevice(pair.secondary);
      }
    }
    // Analog für SLA und UV (exakte Übereinstimmung)
    else if (selectedDevice === pair.secondary && pair.primary !== "FDM-Drucker") {
      let found = false;
      document.querySelectorAll(".dropdown-input").forEach(input => {
        if (input.value.trim() === pair.primary) {
          found = true;
        }
      });
      if (!found) {
        addRowWithDevice(pair.primary);
      }
    }
  });
}

// Gesamtsumme berechnen
function recalcSummary() {
  const rows = document.querySelectorAll(".position-row");
  const memberStatus = document.getElementById("mitgliedsstatus").value;
  const costIndex = membershipIndexMap[memberStatus] || 0;

  let subtotal = 0;

  // Erster Durchlauf: Finde den höchsten Tagespauschalenpreis
  let maxDaily = 0;
  rows.forEach(row => {
    const deviceName = row.querySelector(".dropdown-input").value.trim();
    const item = priceData.find(d => d.name === deviceName);
    if (item && item.Einheit.toLowerCase().includes("tagespauschale")) {
      const dailyPrice = item.kosten[costIndex];
      if (dailyPrice > maxDaily) {
        maxDaily = dailyPrice;
      }
    }
  });

  let dailyCounted = false;

  // Zweiter Durchlauf: Berechne den Preis pro Zeile
  rows.forEach(row => {
    const deviceName = row.querySelector(".dropdown-input").value.trim();
    const mengeVal = parseFloat(row.querySelector(".menge-input").value) || 0;
    const einheitSpan = row.querySelector(".einheit-span");
    const priceSpan = row.querySelector(".price-span");

    const item = priceData.find(d => d.name === deviceName);
    if (!deviceName || !item) {
      einheitSpan.textContent = "";
      priceSpan.textContent = "0.00 €";
      return;
    }

    einheitSpan.textContent = `(${item.Einheit})`;
    const preisProE = item.kosten[costIndex];
    let rowTotal = 0;

    if (item.Einheit.toLowerCase().includes("tagespauschale")) {
      if (!dailyCounted && preisProE === maxDaily) {
        rowTotal = preisProE;
        dailyCounted = true;
      } else {
        rowTotal = 0;
      }
    } else if (item.Einheit.toLowerCase().includes("angefangene 10 minuten")) {
      const parted = Math.ceil(mengeVal / 10);
      rowTotal = parted * preisProE;
    } else if (item.Einheit.toLowerCase().includes("1/2h")) {
      const parted = Math.ceil(mengeVal / 0.5);
      rowTotal = parted * preisProE;
    } else {
      rowTotal = preisProE * mengeVal;
    }

    priceSpan.textContent = rowTotal.toFixed(2) + " €";
    subtotal += rowTotal;
  });

  document.getElementById("subtotal-display").textContent = subtotal.toFixed(2);
  const bezahlt = parseFloat(document.getElementById("bezahlter_betrag").value) || 0;
  let spende = 0;
  if (bezahlt > subtotal) {
    spende = bezahlt - subtotal;
  }
  document.getElementById("spende-display").textContent = spende.toFixed(2);}});
