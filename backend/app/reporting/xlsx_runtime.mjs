import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [, , operation, inputPath, outputPath] = process.argv;

function colLetters(index) {
  let value = "";
  while (index > 0) {
    const remainder = (index - 1) % 26;
    value = String.fromCharCode(65 + remainder) + value;
    index = Math.floor((index - 1) / 26);
  }
  return value;
}

function typedValue(field, value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && /(date|_at)$/.test(field)) {
    return new Date(`${value}T00:00:00Z`);
  }
  return value;
}

async function build() {
  const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
  const workbook = Workbook.create();
  const structure = payload.manifest.sheet_structure[0];
  const maxHeaderRow = Math.max(...structure.header_rows);
  const columns = payload.manifest.columns;
  for (const dataSheet of payload.sheets) {
    const sheet = workbook.worksheets.add(dataSheet.name);
    sheet.showGridLines = false;
    for (const [address, value] of Object.entries(structure.header_cells)) {
      sheet.getRange(address).values = [[value]];
    }
    for (const merge of structure.merges) sheet.mergeCells(merge);
    for (const column of columns) {
      if (column.slot && dataSheet.header_overrides[column.canonical_field]) {
        sheet.getRange(column.slot.header_cell).values = [[dataSheet.header_overrides[column.canonical_field]]];
      }
    }
    if (dataSheet.rows.length) {
      const values = dataSheet.rows.map(row => row.map((value, index) => typedValue(dataSheet.fields[index], value)));
      const lastColumn = colLetters(columns.length);
      const start = maxHeaderRow + 1;
      sheet.getRange(`A${start}:${lastColumn}${start + values.length - 1}`).values = values;
    }
    const lastColumn = colLetters(columns.length);
    const headerRange = sheet.getRange(`A1:${lastColumn}${maxHeaderRow}`);
    headerRange.format.fill = "#1F4E78";
    headerRange.format.font = { bold: true, color: "#FFFFFF" };
    headerRange.format.wrapText = true;
    headerRange.format.horizontalAlignment = "center";
    headerRange.format.verticalAlignment = "center";
    headerRange.format.rowHeight = 24;
    const leaf = Math.max(...structure.header_rows);
    sheet.getRange(`A${leaf}:${lastColumn}${leaf}`).format.borders = { preset: "all", style: "thin", color: "#B4C7E7" };
    sheet.freezePanes.freezeRows(maxHeaderRow);
    sheet.autoFilter = { range: `A${leaf}:${lastColumn}${Math.max(leaf + 1, maxHeaderRow + dataSheet.rows.length)}` };
    for (let index = 0; index < columns.length; index++) {
      const column = columns[index];
      const letter = colLetters(index + 1);
      const sample = dataSheet.rows.slice(0, 50).map(row => row[index] == null ? "" : String(row[index]));
      const headerText = column.header_path.join(" ");
      const width = Math.min(28, Math.max(10, headerText.length + 2, ...sample.map(value => Math.min(28, value.length + 2))));
      const range = sheet.getRange(`${letter}1:${letter}${Math.max(maxHeaderRow + 1, maxHeaderRow + dataSheet.rows.length)}`);
      range.format.columnWidth = width;
      if (/(date|_at)$/.test(column.canonical_field)) range.format.numberFormat = "yyyy-mm-dd";
      else if (/(ratio|completion)/.test(column.canonical_field)) range.format.numberFormat = "0.00%";
      else if (/(qty|amount|price)/.test(column.canonical_field)) range.format.numberFormat = "#,##0.0000";
    }
  }
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
}

async function inspect() {
  const specification = JSON.parse(await fs.readFile(inputPath, "utf8"));
  const input = await FileBlob.load(specification.workbook_path);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const result = { sheets: [] };
  const structure = specification.manifest.sheet_structure[0];
  const maxHeaderRow = Math.max(...structure.header_rows);
  const lastColumn = colLetters(specification.manifest.columns.length);
  for (const expected of specification.sheets) {
    const sheet = workbook.worksheets.getItem(expected.name);
    const headers = specification.manifest.columns.map(column => {
      const address = column.slot ? column.slot.header_cell : column.source_header_cells[column.source_header_cells.length - 1];
      return sheet.getRange(address).values[0][0];
    });
    const firstRow = expected.row_count ? sheet.getRange(`A${maxHeaderRow + 1}:${lastColumn}${maxHeaderRow + 1}`).values[0] : [];
    const after = sheet.getRange(`A${maxHeaderRow + expected.row_count + 1}:${lastColumn}${maxHeaderRow + expected.row_count + 1}`).values[0];
    const preview = await workbook.render({ sheetName: expected.name, range: `A1:${lastColumn}${Math.min(maxHeaderRow + expected.row_count, maxHeaderRow + 5)}`, scale: 1 });
    result.sheets.push({ name: expected.name, headers, first_row: firstRow, after_last_blank: after.every(value => value == null || value === ""), preview_bytes: (await preview.arrayBuffer()).byteLength });
  }
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 4000 });
  result.formula_error_scan = errors.ndjson;
  await fs.writeFile(outputPath, JSON.stringify(result), "utf8");
}

if (operation === "build") await build();
else if (operation === "inspect") await inspect();
else throw new Error("UNKNOWN_XLSX_OPERATION");
