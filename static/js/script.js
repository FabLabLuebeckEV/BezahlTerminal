/*
  In diesem Script:
  - Erzeugen wir dynamisch Zeilen für Positionen.
  - Jede Zeile hat jetzt name="position_name_X" und name="menge_X", damit sie im POST ankommen.
*/

let positionCounter = 0;

// Mapping: Welcher Mitgliedsstatus -> Index im "kosten"-Array
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
  }
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

  // WICHTIG: Wir vergeben name="position_name_X" und name="menge_X"
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

  // Beim Fokussieren: alle zeigen
  dropdownInput.addEventListener("focus", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  // Bei Eingabe: filtern
  dropdownInput.addEventListener("input", () => {
    fillDropdownList(dropdownList, dropdownInput.value);
    dropdownList.classList.remove("hidden");
  });

  // Klick außerhalb => Dropdown schließen
  document.addEventListener("click", (evt) => {
    if (!rowDiv.contains(evt.target)) {
      dropdownList.classList.add("hidden");
    }
  });

  // Menge => Neuberechnung
  const mengeInput = rowDiv.querySelector(".menge-input");
  mengeInput.addEventListener("input", recalcSummary);

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
      // Klick => Wert übernehmen
      const parentRow = listEl.closest(".position-row");
      parentRow.querySelector(".dropdown-input").value = item.name;
      listEl.classList.add("hidden");
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
  const rows = document.querySelectorAll(".position-row");
  const memberStatus = document.getElementById("mitgliedsstatus").value;
  const costIndex = membershipIndexMap[memberStatus] || 0;

  let subtotal = 0;

  // 1. Pass: Finde den höchsten Tagespauschalenpreis
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

  // Flag, um sicherzustellen, dass der höchste Tagespauschalenpreis nur einmal gezählt wird
  let dailyCounted = false;

  // 2. Pass: Berechne den Preis pro Zeile
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

    // Zeige die Einheit an
    einheitSpan.textContent = `(${item.Einheit})`;

    const preisProE = item.kosten[costIndex];
    let rowTotal = 0;

    if (item.Einheit.toLowerCase().includes("tagespauschale")) {
      // Nur die höchste Tagespauschale wird gezählt – und nur einmal.
      if (!dailyCounted && preisProE === maxDaily) {
        rowTotal = preisProE;
        dailyCounted = true;
      } else {
        rowTotal = 0;
      }
    } else if (item.Einheit.toLowerCase().includes("angefangene 10 minuten")) {
      // Rundet auf die nächste 10-Minuten-Einheit
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
  document.getElementById("spende-display").textContent = spende.toFixed(2);
}

