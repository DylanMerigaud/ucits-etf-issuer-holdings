import { deflateRawSync } from "node:zlib";

/** A minimal zip writer (stored or deflated entries). */
export function zip(files: Record<string, string>, deflate = false): Uint8Array {
  const locals: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(files)) {
    const raw = Buffer.from(text, "utf8");
    const data = deflate ? deflateRawSync(raw) : raw;
    const nameBuf = Buffer.from(name);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(deflate ? 8 : 0, 8);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    const head = Buffer.alloc(46);
    head.writeUInt32LE(0x02014b50, 0);
    head.writeUInt16LE(20, 4);
    head.writeUInt16LE(20, 6);
    head.writeUInt16LE(deflate ? 8 : 0, 10);
    head.writeUInt32LE(data.length, 20);
    head.writeUInt32LE(raw.length, 24);
    head.writeUInt16LE(nameBuf.length, 28);
    head.writeUInt32LE(offset, 42);
    locals.push(local, nameBuf, data);
    central.push(head, nameBuf);
    offset += 30 + nameBuf.length + data.length;
  }
  const cd = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(Object.keys(files).length, 8);
  end.writeUInt16LE(Object.keys(files).length, 10);
  end.writeUInt32LE(cd.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, end]);
}

export const NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
export const REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

/** A minimal workbook with one worksheet stored under a non-default file name. */
export function build(sheetXml: string, shared?: string, deflate = false): Uint8Array {
  const files: Record<string, string> = {
    "xl/workbook.xml": `<workbook ${NS} xmlns:r="${REL}"><sheets><sheet name="Data" sheetId="1" r:id="rId9"/></sheets></workbook>`,
    "xl/_rels/workbook.xml.rels":
      `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId9" Type="${REL}/worksheet" Target="worksheets/sheet7.xml"/></Relationships>`,
    "xl/worksheets/sheet7.xml": `<worksheet ${NS}><sheetData>${sheetXml}</sheetData></worksheet>`,
  };
  if (shared !== undefined) files["xl/sharedStrings.xml"] = `<sst ${NS}>${shared}</sst>`;
  return zip(files, deflate);
}

