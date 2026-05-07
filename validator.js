const express = require('express');
const { Client } = require('@notionhq/client');
const app = express();
app.use(express.json());

const notion = new Client({ auth: process.env.NOTION_TOKEN || 'dummy' });
const MENGDETABELLER_DB = '180e0d6b-d285-4232-89d7-dbcc07ea8987';

const CANONICAL_RATES = {
  manuelt_arbeid: 725,
  prosjektleder: 755,
  materialer_paslag: 20,
  underleverandorer_paslag: 15,
  servicebil: 388,
  mannskapsbrakke_uke: 1050, // Midt mellom 900-1200
  gravemaskin_dag: 4000, // Midt mellom 3750-4250
  beltedumper_dag: 2200
};

app.get("/health", (req, res) => {
  res.json({ status: 'ok', service: 'dgn-validator', version: '1.2.0' });
});

app.get('/rates', (req, res) => {
  res.json(CANONICAL_RATES);
});

// Risk factor logic moved to backend
app.get('/risk-consequences', (req, res) => {
  res.json({
    tilkomst: {
      "God": { equipment: ["gravemaskin", "lastebil"], notes: "" },
      "Begrenset": {
        equipment: ["beltedumper"],
        exclude: ["gravemaskin"],
        notes: "Vi anbefaler ikke at det tas inn en gravemaskin pga adkomst.",
        labor_multiplier: 1.3
      },
      "Vanskelig": {
        equipment: ["spesialtransport"],
        notes: "Kun manuell bæring og spesialtransport nødvendig pga vanskelig adkomst.",
        labor_multiplier: 2.0
      }
    },
    triggers: [
      { id: "cca", condition: "riving før 2004", action: "Legg til post for spesialavfall" },
      { id: "helling", condition: "helling > 5 grader", action: "Legg til membran, drensrør, fiberduk, ekstra gravearbeid" },
      { id: "fjell", condition: "fjell i grunn", action: "Legg til pigging/spesialtilpasning" }
    ]
  });
});

app.post('/validate', (req, res) => {
  const tilbud = req.body;
  const errors = [];
  const warnings = [];
  const fixes = [];

  if (!tilbud.jobbtype) errors.push("Jobbtype mangler.");
  if (!tilbud.mengdetabell || !Array.isArray(tilbud.mengdetabell)) {
    errors.push("Mengdetabell mangler eller er ugyldig.");
  } else {
    // A - Complete mengdetabell
    if (tilbud.jobbtype?.toLowerCase().includes("skifer")) {
      const hasFiberduk = tilbud.mengdetabell.some(p => p.aktivitet.toLowerCase().includes("fiberduk"));
      if (!hasFiberduk) errors.push("Fiberduk i bunn mangler (obligatorisk for skiferplass).");

      const hasDybde = tilbud.mengdetabell.some(p => p.notat?.includes("cm") && (p.notat?.includes("35") || p.notat?.includes("40") || p.notat?.includes("45")));
      if (!hasDybde) warnings.push("Utgravingsdybde (typisk 35-45 cm) bør spesifiseres i notatene.");

      const hasBærelag = tilbud.mengdetabell.some(p => p.aktivitet.toLowerCase().includes("bærelag") || p.aktivitet.toLowerCase().includes("subbus"));
      if (!hasBærelag) errors.push("Bærelag/subbus mangler.");

      const hasSettelag = tilbud.mengdetabell.some(p => p.aktivitet.toLowerCase().includes("settelag"));
      if (!hasSettelag) errors.push("Settelag mangler.");
    }
  }

  // B - Price Asymmetry & Rates
  if (tilbud.satser) {
    Object.keys(CANONICAL_RATES).forEach(key => {
      if (tilbud.satser[key] && tilbud.satser[key] !== CANONICAL_RATES[key]) {
        fixes.push(`Korrigerte ${key} til ${CANONICAL_RATES[key]}`);
        tilbud.satser[key] = CANONICAL_RATES[key];
      }
    });
  }

  // C - Structure
  if (tilbud.tilbudssum) {
    const expectedMva = Math.round(tilbud.tilbudssum.eks_mva * 0.25);
    if (Math.abs(tilbud.tilbudssum.mva - expectedMva) > 2) {
      fixes.push(`Korrigerte MVA-beregning.`);
      tilbud.tilbudssum.mva = expectedMva;
      tilbud.tilbudssum.inkl_mva = tilbud.tilbudssum.eks_mva + expectedMva;
    }
  }

  if (!tilbud.gyldighetstid_dager || tilbud.gyldighetstid_dager !== 30) {
    tilbud.gyldighetstid_dager = 30;
    fixes.push("Satte gyldighetstid til 30 dager.");
  }

  if (tilbud.betalingsbetingelser) {
    if (tilbud.betalingsbetingelser.forste_rate_pct !== 50) {
        tilbud.betalingsbetingelser.forste_rate_pct = 50;
        fixes.push("Satte første rate til 50%.");
    }
    if (tilbud.betalingsbetingelser.betalingsfrist_dager !== 14) {
        tilbud.betalingsbetingelser.betalingsfrist_dager = 14;
        fixes.push("Satte betalingsfrist til 14 dager.");
    }
  }

  res.json({ godkjent: errors.length === 0, errors, warnings, fixes, tilbud });
});

app.post('/group', (req, res) => {
  const { mengdetabell, jobbtype } = req.body;
  if (!mengdetabell) return res.status(400).json({ error: "mengdetabell required" });

  const groups = { "Topplag": [], "Konstruksjon": [], "Avfall": [], "Annet": [] };

  mengdetabell.forEach(post => {
    const kat = post.kategori || post.underkategori || "Konstruksjon";
    if (kat === "Topplag") groups["Topplag"].push(post);
    else if (["Konstruksjon", "Fundament", "Avslutning"].includes(kat)) groups["Konstruksjon"].push(post);
    else if (kat === "Avfall") groups["Avfall"].push(post);
    else groups["Annet"].push(post);
  });

  const wordTabell = [];
  if (groups["Konstruksjon"].length > 0) {
    let groupName = "Bærelag og fundament";
    if (jobbtype?.toLowerCase().includes("platting") || jobbtype?.toLowerCase().includes("terrasse")) groupName = "Underkonstruksjon";
    if (jobbtype?.toLowerCase().includes("mur")) groupName = "Fundament og bakfyll";
    wordTabell.push({
      post: groupName,
      mengde: "Inkludert",
      beskrivelse: "Komplett oppbygning iht. faglige krav: " + groups["Konstruksjon"].map(p => p.aktivitet.toLowerCase()).join(", ") + "."
    });
  }
  groups["Topplag"].forEach(p => {
    wordTabell.push({ post: p.aktivitet, mengde: `${p.mengde} ${p.enhet}`, beskrivelse: p.notat || "" });
  });
  groups["Avfall"].forEach(p => {
    wordTabell.push({ post: p.aktivitet, mengde: `ca. ${p.mengde} ${p.enhet}`, beskrivelse: p.notat || "" });
  });
  res.json({ wordTabell });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`Port ${PORT}`));
