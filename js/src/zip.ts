import { inflateRawSync } from "node:zlib";

/** The files of a zip archive, read lazily from memory. */
export class ZipReader {
  private readonly data: Buffer;
  private readonly entries = new Map<string, { method: number; size: number; offset: number }>();

  /** Read the central directory. Throws an Error when the bytes are not a zip archive. */
  constructor(bytes: Uint8Array) {
    this.data = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const d = this.data;
    let eocd = -1;
    for (let i = d.length - 22; i >= Math.max(0, d.length - 22 - 65535); i--) {
      if (d.readUInt32LE(i) === 0x06054b50) {
        eocd = i;
        break;
      }
    }
    if (eocd === -1) throw new Error("File is not a zip file");
    const count = d.readUInt16LE(eocd + 10);
    let p = d.readUInt32LE(eocd + 16);
    for (let n = 0; n < count; n++) {
      if (d.readUInt32LE(p) !== 0x02014b50) throw new Error("bad central directory");
      const method = d.readUInt16LE(p + 10);
      const size = d.readUInt32LE(p + 20);
      const nameLen = d.readUInt16LE(p + 28);
      const extraLen = d.readUInt16LE(p + 30);
      const commentLen = d.readUInt16LE(p + 32);
      const offset = d.readUInt32LE(p + 42);
      const name = d.toString("utf8", p + 46, p + 46 + nameLen);
      this.entries.set(name, { method, size, offset });
      p += 46 + nameLen + extraLen + commentLen;
    }
  }

  /** True when the archive holds a file of this name. */
  has(name: string): boolean {
    return this.entries.has(name);
  }

  /** The bytes of a file. Throws an Error when it is missing or uses an unsupported method. */
  read(name: string): Buffer {
    const entry = this.entries.get(name);
    if (entry === undefined) throw new Error(`There is no item named '${name}' in the archive`);
    const d = this.data;
    if (d.readUInt32LE(entry.offset) !== 0x04034b50) throw new Error("bad local header");
    const start = entry.offset + 30 + d.readUInt16LE(entry.offset + 26) + d.readUInt16LE(entry.offset + 28);
    const raw = d.subarray(start, start + entry.size);
    if (entry.method === 0) return raw;
    if (entry.method === 8) return inflateRawSync(raw);
    throw new Error(`compression method ${entry.method} is not supported`);
  }
}
