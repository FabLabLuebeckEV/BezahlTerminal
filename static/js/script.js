/*
  In diesem Script:
  - Dynamisches Erzeugen von Zeilen für Positionen mit name="position_name_X" und name="menge_X".
  - Beim Absenden des Formulars wird der Button zu einem Progress-Indikator.
  - Bei Kartenzahlung erscheint ein benutzerdefinierter Modal-Bestätigungsdialog, der den Submit pausiert.
  - Bei der Auswahl von bestimmten Geräten werden automatisch passende Partnergeräte ergänzt.
  - Ein zusätzlicher "Clear All"-Button lädt die Seite neu.
*/

let positionCounter = 0;

// Mapping: Mitgliedsstatus -> Index im "kosten"-Array
const membershipIndexMap = {
  "Nichtmitglied": 0,
  "Fördermitglied": 1,
  "Ordentliches Mitglied": 2
};

// Gerätepaare für automatische Ergänzungen
const devicePairs = [
  { primary: "FDM-Drucker", secondary: "FDM-Drucker Material normal" },
  { primary: "SLA-Drucker", secondary: "SLA-Drucker Material" },
  { primary: "UV-Drucker", secondary: "UV-Drucker reinigung" }
];

document.addEventListener("DOMContentLoaded", async () => {
  const rnInput = document.getElementById("rechnungsnummer-input");
  const rnSpan = document.getElementById("rechnungsnummer");

  if (!rnInput.value) {
    const newRn = await generateRechnungsnr();
    rnInput.value = newRn;
    rnSpan.textContent = newRn; // Nur sichtbar bei Karte, sonst bleibt es leer
  }
  setupHandlers();
  addPositionRow();
  await updateCardHinweis();
  recalcSummary();

  // Clear All Button (falls im HTML vorhanden)
  const clearBtn = document.getElementById("clear-all-btn");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      location.reload();
    });
  }

  // Submit-Handler: immer default verhindern, dann manuell submitten
  document.getElementById("billing-form").addEventListener("submit", async (e) => {
    e.preventDefault(); // immer verhindern
    if (document.getElementById("bezahlter_betrag").value < document.getElementById("subtotal-display").textContent) {
      document.getElementById("bezahlter_betrag").value = document.getElementById("subtotal-display").textContent;
      //alert("Der bezahlte Betrag ist kleiner als die Gesamtsumme. Bitte korrigieren Sie den Betrag.");
      //return;
    }
    const rows = document.querySelectorAll(".position-row");
    let hasFilled = false;
    rows.forEach(row => {
      const input = row.querySelector(".dropdown-input");
      if (input && input.value.trim() !== "") {
        hasFilled = true;
      }
    });
    if (rows.length === 0 || !hasFilled) {
      alert("Es wurde keine Position ausgewählt. Bitte fügen Sie mindestens eine Position hinzu.");
      return;
    }

    // Bei Kartenzahlung: Modal-Bestätigung
    const zahlungsmethode = document.getElementById("zahlungsmethode").value;
    if (zahlungsmethode.toLowerCase() === "karte") {
      const bezahlterBetrag = document.getElementById("bezahlter_betrag").value;
      const confirmMessage = `War die Bezahlung von ${bezahlterBetrag} € mit der Karte erfolgreich?`;
      const confirmed = await customConfirm(confirmMessage);
      if (!confirmed) {
        const submitBtn = document.querySelector(".form-actions button");
        submitBtn.disabled = false;
        submitBtn.textContent = "Abrechnung abschicken";
        return;
      }
    }

    // Submit-Button als Progress-Indikator setzen
    const submitBtn = document.querySelector(".form-actions button");
    submitBtn.disabled = true;
    submitBtn.textContent = "Verarbeitung...";

    // Nach allen Prüfungen, Formular manuell absenden
    document.getElementById("billing-form").submit();
  });
});

// Benutzerdefinierter Modal-Bestätigungsdialog
function customConfirm(message) {
  return new Promise((resolve, reject) => {
    const modal = document.getElementById("confirm-modal");
    const messageEl = document.getElementById("confirm-message");
    const yesBtn = document.getElementById("confirm-yes");
    const noBtn = document.getElementById("confirm-no");

    messageEl.textContent = message;
    modal.classList.remove("hidden");

    function cleanup() {
      modal.classList.add("hidden");
      yesBtn.removeEventListener("click", onYes);
      noBtn.removeEventListener("click", onNo);
    }
    function onYes() {
      cleanup();
      resolve(true);
    }
    function onNo() {
      cleanup();
      resolve(false);
    }
    yesBtn.addEventListener("click", onYes);
    noBtn.addEventListener("click", onNo);
  });
}

function setupHandlers() {
  document.getElementById("add-position-btn").addEventListener("click", addPositionRow);
  document.getElementById("mitgliedsstatus").addEventListener("change", recalcSummary);
  document.getElementById("zahlungsmethode").addEventListener("change", () => {
    updateCardHinweis();
    recalcSummary();
  });
  document.getElementById("bezahlter_betrag").addEventListener("input", recalcSummary);
}

async function updateCardHinweis() {
  const payMethod = document.getElementById("zahlungsmethode").value;
  const cardHinweis = document.getElementById("card-hinweis");
  const rnSpan = document.getElementById("rechnungsnummer");
  const rnValue = document.getElementById("rechnungsnummer-input");

  if (payMethod === "Karte") {
    cardHinweis.classList.remove("hidden");
    let rnV = rnValue.value;
    if (!rnValue.value) {
      rnV = await generateRechnungsnr();
    }
    rnSpan.textContent = rnV;
    rnValue.value = rnV;
  } else {
    cardHinweis.classList.add("hidden");
    rnSpan.textContent = "";
  }
}

async function generateRechnungsnr() {
  try {
    const response = await fetch("/api/generate_invoice_number");
    const data = await response.json();
    return data.invoice_number;
  } catch (error) {
    console.error("Fehler beim Generieren der Rechnungsnummer:", error);
    return "";
  }
}

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
  rowDiv.querySelector(".remove-btn").addEventListener("click", () => {
    container.removeChild(rowDiv);
    recalcSummary();
  });
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

function fillDropdownList(listEl, filterValue) {
  const val = filterValue.toLowerCase().trim();
  listEl.innerHTML = "";

  const filteredItems = priceData.filter(item => {
    const nameMatches = item.name.toLowerCase().includes(val);
    let keywordMatches = false;
    if (item.keywords && Array.isArray(item.keywords)) {
      keywordMatches = item.keywords.some(keyword => keyword.toLowerCase().includes(val));
    }
    return nameMatches || keywordMatches;
  });

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


function checkPairRules(selectedDevice) {
  devicePairs.forEach(pair => {
    // Wenn "FDM-Drucker Material" gewählt wird, soll "FDM-Drucker" ergänzt werden.
    if (selectedDevice.toLowerCase().includes("fdm-drucker material") && pair.primary === "FDM-Drucker") {
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
    // Umgekehrt: Falls der Primary gewählt wird, füge den Secondary hinzu (für FDM und exakte Vergleiche bei den anderen)
    else if (selectedDevice === pair.primary) {
      let found = false;
      document.querySelectorAll(".dropdown-input").forEach(input => {
        if (pair.primary === "FDM-Drucker") {
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
    // Analog: Falls der Secondary gewählt wird (außer FDM), ergänze den Primary
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

function recalcSummary() {
  const rows = document.querySelectorAll(".position-row");
  const memberStatus = document.getElementById("mitgliedsstatus").value;
  const costIndex = membershipIndexMap[memberStatus] || 0;

  // 1. Finde höchste Tagespauschale
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

  // 2. Berechne Gesamtsumme
  let subtotal = 0;
  let dailyApplied = false;
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
      if (!dailyApplied && preisProE === maxDaily) {
        rowTotal = preisProE;
        dailyApplied = true;
      } else {
        rowTotal = 0;
      }
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

