/*
  In diesem Script:
  - Erzeugt man dynamisch Zeilen für Positionen.
  - Jede Zeile enthält ein Dropdown + Suchfeld (clientseitiger Filter).
  - Hinter jeder Zeile zeigen wir den aktuellen Preis an.
  - Tagespauschale => Menge ignorieren.
  - Zusammenfassung (Zwischensumme + Spende).
  - Hinweis bei "Karte": Rechnungsnummer generieren und einblenden.
*/

let positionCounter = 0;

// Mapping zu Indizes in "kosten"
const membershipIndexMap = {
  "Nichtmitglied": 0,
  "Fördermitglied": 1,
  "Ordentliches Mitglied": 2
};

document.addEventListener("DOMContentLoaded", () => {
  setupHandlers();
  // Eine erste Position sofort
  addPositionRow();
  updateCardHinweis();
  recalcSummary();
});

function setupHandlers() {
  document.getElementById("add-position-btn").addEventListener("click", () => {
    addPositionRow();
  });

  document.getElementById("mitgliedsstatus").addEventListener("change", () => {
    recalcSummary();
  });

  document.getElementById("zahlungsmethode").addEventListener("change", () => {
    updateCardHinweis();
    recalcSummary();
  });

  document.getElementById("bezahlter_betrag").addEventListener("input", () => {
    recalcSummary();
  });
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

  // Wir bauen ein eigenes "Dropdown mit Filter" (clientseitig)
  // => <input> + <div> mit allen Optionen, bei Eingabe filtern wir
  //    und blenden nur passende an.

  rowDiv.innerHTML = `
    <div>
      <label>Gerät/Material:</label>
      <div class="dropdown-container">
        <input type="text" class="dropdown-input" placeholder="Gerät wählen..." />
        <div class="dropdown-list hidden"></div>
      </div>

      <label>Menge:</label>
      <input type="number" step="0.01" class="menge-input" value="1" style="width:80px;" />

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

  // Beim Klick => alle Optionen anzeigen
  dropdownInput.addEventListener("focus", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  // Bei Eingabe => Filter
  dropdownInput.addEventListener("input", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  // Klick außerhalb => schließt Dropdown
  document.addEventListener("click", (evt) => {
    if (!rowDiv.contains(evt.target)) {
      dropdownList.classList.add("hidden");
    }
  });

  // Menge => Neuberechnung
  const mengeInput = rowDiv.querySelector(".menge-input");
  mengeInput.addEventListener("input", () => {
    recalcSummary();
  });

  container.appendChild(rowDiv);

  recalcSummary();
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
      // Beim Klick übernehmen wir den Wert ins Input
      const parentRow = listEl.closest(".position-row");
      parentRow.querySelector(".dropdown-input").value = item.name;
      listEl.classList.add("hidden");

      // Einheit und Preis aktualisieren
      recalcSummary();
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

// Gesamtsumme berechnen
function recalcSummary() {
  let subtotal = 0;
  const rows = document.querySelectorAll(".position-row");
  const memberStatus = document.getElementById("mitgliedsstatus").value;
  const costIndex = membershipIndexMap[memberStatus] || 0;

  // Gehe durch alle Einheiten und finde die maximale Tagespauschale
  let maxTagespauschaleFound = 0;

  rows.forEach(row => {
    const deviceName = row.querySelector(".dropdown-input").value.trim();
    const item = priceData.find(d => d.name === deviceName);

    if (item && item.Einheit.includes("Tagespauschale")) {
      maxTagespauschaleFound = Math.max(maxTagespauschaleFound, item.kosten[costIndex]);
    }
  });
  let maxTagespauschale = 0;
  rows.forEach(row => {
    const deviceName = row.querySelector(".dropdown-input").value.trim();
    const mengeVal = parseFloat(row.querySelector(".menge-input").value) || 0;
    const einheitSpan = row.querySelector(".einheit-span");
    const priceSpan = row.querySelector(".price-span");

    // Finde in priceData
    const item = priceData.find(d => d.name === deviceName);
    if (!deviceName || !item) {
      einheitSpan.textContent = "";
      priceSpan.textContent = "0.00 €";
      return;
    }

    // Einheit anzeigen
    einheitSpan.textContent = `(${item.Einheit})`;

    const preisProE = item.kosten[costIndex];

    // Basis-Logik
    let rowTotal = 0;
    if (item.Einheit.includes("Tagespauschale")) {
        if (preisProE > maxTagespauschale && maxTagespauschaleFound === preisProE) {
            maxTagespauschale = preisProE;
            rowTotal = preisProE;
        } else {
          rowTotal = 0;
        }
    } else if (item.Einheit.toLowerCase().includes("angefangene 10 minuten")) {
      // abgerundetes Bsp: wir gehen davon aus, dass mengeVal = Minuten
      // => parted = aufrunden(mengeVal / 10)
      const parted = Math.ceil(mengeVal / 10);
      rowTotal = parted * preisProE;
    } else if (item.Einheit.toLowerCase().includes("1/2h")) {
      // Bsp: parted = ceil(mengeVal / 0.5)
      const parted = Math.ceil(mengeVal / 0.5);
      rowTotal = parted * preisProE;
    } else {
      // normal
      rowTotal = preisProE * mengeVal;
    }

    // Anzeigen
    priceSpan.textContent = rowTotal.toFixed(2) + " €";
    subtotal += rowTotal;
  });

  // Zwischensumme
  document.getElementById("subtotal-display").textContent = subtotal.toFixed(2);

  // Spende
  const bezahlt = parseFloat(document.getElementById("bezahlter_betrag").value) || 0;
  let spende = 0;
  if (bezahlt > subtotal) {
    spende = bezahlt - subtotal;
  }
  document.getElementById("spende-display").textContent = spende.toFixed(2);
}
