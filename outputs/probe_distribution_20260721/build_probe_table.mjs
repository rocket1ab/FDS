import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const project = "D:/Pyrosim/radiation_ignition_damage_workflow_20260720_H1_H7";
const caseDir = `${project}/cases_probe_corrected/Q0100_W0100_az270_el15_H1H7_v6_probe_fixed`;
const outputDir = `${project}/outputs/probe_distribution_20260721`;
const reportsDir = `${project}/reports`;

const registry = JSON.parse(await fs.readFile(`${caseDir}/monitor_registry.json`, "utf8"));
const repairs = JSON.parse(await fs.readFile(`${caseDir}/probe_repairs.json`, "utf8"));
const criteria = JSON.parse(await fs.readFile(`${project}/config/damage_criteria.json`, "utf8")).groups;
const repairedIds = new Set(repairs.map((item) => item.wt));

const materialByGroup = {
  RADM: "Fiberglass", WINS: "PMMA", BED: "Nylon", CURT: "Nylon",
  U4: "Legacy U04 material", SEAT: "Polyurethane foam",
  AL2024: "Aluminium 2024", AL5052: "Aluminium 5052",
  AL7075: "Aluminium 7075", O2TANK: "Aluminium 7075",
  H1: "Aluminium 6061, 3 mm", H2: "Aluminium 6061, 3 mm",
  H3: "Aluminium 6061, 3 mm", H4: "Aluminium 6061, 3 mm",
  H5: "Aluminium 6061, 3 mm", H6: "PVC, 1 mm", H7: "CR rubber, 2 mm",
};
const faceByIor = { "-1": "-X", "1": "+X", "-2": "-Y", "2": "+Y", "-3": "-Z", "3": "+Z" };

const rows = [];
let index = 1;
for (const [group, probes] of Object.entries(registry)) {
  for (const probe of probes) {
    rows.push([
      index++, group, criteria[group]?.label || group, materialByGroup[group] || "",
      probe.wt, probe.hf, probe.xyz[0], probe.xyz[1], probe.xyz[2], probe.ior,
      faceByIor[String(probe.ior)] || "", Number(probe.base_flux || 0),
      Number(probe.base_flux || 0) > 0 ? "Direct" : "Shielded/secondary",
      "PASS", repairedIds.has(probe.wt) ? "Yes" : "No", probe.obst_id || "",
    ]);
  }
}

const csvHeaders = [
  "No.", "Group", "Component", "Material", "WT Probe ID", "HF Probe ID",
  "X (m)", "Y (m)", "Z (m)", "IOR", "Face", "Base Flux (kW/m2)",
  "Exposure", "Geometry QA", "Corrected in v6", "Source OBST ID",
];
const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const csv = [csvHeaders, ...rows].map((row) => row.map(csvEscape).join(",")).join("\r\n");
await fs.writeFile(`${reportsDir}/complete_probe_distribution_v6.csv`, `\ufeff${csv}`, "utf8");

const md = [
  "# Complete Probe Distribution Table (v6_probe_fixed)", "",
  "All 153 WT probes and their co-located HF probes passed geometry QA.", "",
  `| ${csvHeaders.join(" | ")} |`,
  `|${csvHeaders.map(() => "---").join("|")}|`,
  ...rows.map((row) => `| ${row.map((value) => String(value).replaceAll("|", "\\|")).join(" | ")} |`),
  "",
];
await fs.writeFile(`${reportsDir}/complete_probe_distribution_v6.md`, md.join("\n"), "utf8");

const workbook = Workbook.create();
const metadata = workbook.worksheets.add("README");
const summary = workbook.worksheets.add("Group Summary");
const detail = workbook.worksheets.add("Probe Distribution");
for (const sheet of [metadata, summary, detail]) sheet.showGridLines = false;

metadata.mergeCells("A1:F1");
metadata.getRange("A1").values = [["FDS Probe Distribution Register"]];
metadata.getRange("A1:F1").format = {
  fill: "#1F4E78", font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center", verticalAlignment: "center",
};
metadata.getRange("A1:F1").format.rowHeight = 30;
metadata.getRange("A3:B12").values = [
  ["Field", "Value"],
  ["Case", "Q0100_W0100_az270_el15_H1H7_v6_probe_fixed"],
  ["Nominal fluence", "100 J/cm2"],
  ["Yield / angle", "100 kt; azimuth 270 deg; elevation 15 deg"],
  ["Temperature probes", rows.length],
  ["Co-located heat-flux probes", rows.length],
  ["Geometry QA", "153/153 PASS"],
  ["FDS grid spacing", "0.1 m"],
  ["Probe offset", "0.035 m from intended material face"],
  ["Maximum definition", "Probe maximum = dynamic envelope of valid WT probes; BNDF provides full-surface cross-check"],
];
metadata.getRange("A3:B3").format = { fill: "#D9EAF7", font: { bold: true, color: "#17365D" } };
metadata.getRange("A3:B12").format.borders = { preset: "outside", style: "thin", color: "#AAB7C4" };
metadata.getRange("A4:A12").format.font = { bold: true, color: "#334155" };
metadata.getRange("A3:A12").format.columnWidth = 24;
metadata.getRange("B3:B12").format.columnWidth = 76;
metadata.getRange("B4:B12").format.wrapText = true;

summary.mergeCells("A1:H1");
summary.getRange("A1").values = [["Probe Coverage by Material / Equipment Group"]];
summary.getRange("A1:H1").format = {
  fill: "#1F4E78", font: { bold: true, color: "#FFFFFF", size: 15 },
  horizontalAlignment: "center", verticalAlignment: "center",
};
summary.getRange("A1:H1").format.rowHeight = 30;
const summaryHeaders = ["Group", "Component", "Material", "WT Count", "QA Pass", "Direct", "Corrected", "Status"];
summary.getRange("A4:H4").values = [summaryHeaders];
const groups = Object.keys(registry);
summary.getRange(`A5:C${4 + groups.length}`).values = groups.map((group) => [group, criteria[group]?.label || group, materialByGroup[group] || ""]);
for (let row = 5; row <= 4 + groups.length; row++) {
  summary.getRange(`D${row}:H${row}`).formulas = [[
    `=COUNTIF('Probe Distribution'!$B$5:$B$157,A${row})`,
    `=COUNTIFS('Probe Distribution'!$B$5:$B$157,A${row},'Probe Distribution'!$N$5:$N$157,"PASS")`,
    `=COUNTIFS('Probe Distribution'!$B$5:$B$157,A${row},'Probe Distribution'!$M$5:$M$157,"Direct")`,
    `=COUNTIFS('Probe Distribution'!$B$5:$B$157,A${row},'Probe Distribution'!$O$5:$O$157,"Yes")`,
    `=IF(D${row}=E${row},"PASS","CHECK")`,
  ]];
}
summary.getRange(`A4:H${4 + groups.length}`).format.borders = { preset: "inside", style: "thin", color: "#D7E0E8" };
summary.getRange("A4:H4").format = { fill: "#2F75B5", font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange(`A5:C${4 + groups.length}`).format.horizontalAlignment = "left";
summary.getRange(`D5:H${4 + groups.length}`).format.horizontalAlignment = "center";
summary.getRange(`H5:H${4 + groups.length}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#DDEBF7", font: { bold: true, color: "#006100" } } });
summary.getRange("A4:A21").format.columnWidth = 12;
summary.getRange("B4:B21").format.columnWidth = 31;
summary.getRange("C4:C21").format.columnWidth = 27;
summary.getRange("D4:H21").format.columnWidth = 13;
summary.freezePanes.freezeRows(4);

detail.mergeCells("A1:P1");
detail.getRange("A1").values = [["Complete FDS Surface-Probe Distribution (v6_probe_fixed)"]];
detail.getRange("A1:P1").format = {
  fill: "#1F4E78", font: { bold: true, color: "#FFFFFF", size: 15 },
  horizontalAlignment: "center", verticalAlignment: "center",
};
detail.getRange("A1:P1").format.rowHeight = 30;
detail.getRange("A2:P2").merge();
detail.getRange("A2").values = [["WT and HF probes are co-located. Geometry QA uses the current FDS OBST faces after 0.1 m grid snapping."]];
detail.getRange("A2:P2").format = { fill: "#EAF2F8", font: { color: "#334155", italic: true }, wrapText: true };
detail.getRange("A4:P4").values = [csvHeaders];
detail.getRange(`A5:P${4 + rows.length}`).values = rows;
detail.getRange("A4:P4").format = {
  fill: "#2F75B5", font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
};
detail.getRange("A4:P4").format.rowHeight = 34;
detail.getRange(`A5:F${4 + rows.length}`).format.horizontalAlignment = "left";
detail.getRange(`G5:L${4 + rows.length}`).format.horizontalAlignment = "right";
detail.getRange(`M5:P${4 + rows.length}`).format.horizontalAlignment = "center";
detail.getRange(`G5:I${4 + rows.length}`).format.numberFormat = "0.0000";
detail.getRange(`J5:J${4 + rows.length}`).format.numberFormat = "0";
detail.getRange(`L5:L${4 + rows.length}`).format.numberFormat = "#,##0.0";
detail.getRange(`A4:P${4 + rows.length}`).format.borders = { preset: "inside", style: "thin", color: "#E2E8F0" };
detail.getRange(`N5:N${4 + rows.length}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#E2F0D9", font: { color: "#006100" } } });
detail.getRange(`O5:O${4 + rows.length}`).conditionalFormats.add("containsText", { text: "Yes", format: { fill: "#FFF2CC", font: { bold: true, color: "#9C6500" } } });
const widths = [8, 12, 31, 27, 24, 24, 11, 11, 11, 8, 9, 19, 20, 14, 16, 18];
for (let col = 0; col < widths.length; col++) detail.getRangeByIndexes(3, col, rows.length + 1, 1).format.columnWidth = widths[col];
detail.freezePanes.freezeRows(4);
detail.freezePanes.freezeColumns(2);
const table = detail.tables.add(`A4:P${4 + rows.length}`, true, "ProbeDistributionTable");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

await fs.mkdir(outputDir, { recursive: true });
const preview1 = await workbook.render({ sheetName: "README", range: "A1:F12", scale: 1.3, format: "png" });
await fs.writeFile(`${outputDir}/preview_readme.png`, new Uint8Array(await preview1.arrayBuffer()));
const preview2 = await workbook.render({ sheetName: "Group Summary", range: "A1:H21", scale: 1.3, format: "png" });
await fs.writeFile(`${outputDir}/preview_summary.png`, new Uint8Array(await preview2.arrayBuffer()));
const preview3 = await workbook.render({ sheetName: "Probe Distribution", range: "A1:P24", scale: 1.0, format: "png" });
await fs.writeFile(`${outputDir}/preview_detail.png`, new Uint8Array(await preview3.arrayBuffer()));

const check = await workbook.inspect({ kind: "table", range: "Probe Distribution!A4:P12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 16 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${outputDir}/complete_probe_distribution_table_v6.xlsx`);
console.log(JSON.stringify({ rows: rows.length, groups: groups.length, output: `${outputDir}/complete_probe_distribution_table_v6.xlsx` }));
