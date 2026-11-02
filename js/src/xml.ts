/** A tiny XML reader, enough for spreadsheet parts: elements, attributes, text, namespaces. */

/** One attribute with its namespace uri resolved ("" when it has no prefix). */
export interface XmlAttr {
  uri: string;
  local: string;
  value: string;
}

/** One element: local name (any prefix dropped), attributes, leading text and children. */
export interface XmlNode {
  name: string;
  attrs: XmlAttr[];
  text: string;
  children: XmlNode[];
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decode(raw: string): string {
  if (!raw.includes("&")) return raw;
  return raw.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[A-Za-z]+);/g, (whole, body: string) => {
    if (body.startsWith("#x")) return String.fromCodePoint(parseInt(body.slice(2), 16));
    if (body.startsWith("#")) return String.fromCodePoint(parseInt(body.slice(1), 10));
    return ENTITIES[body] ?? whole;
  });
}

const ATTR = /([^\s=\/>]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;

/** Parse an XML document and return its root element. Throws an Error when it is malformed. */
export function parseXml(input: string): XmlNode {
  const stack: Array<{ node: XmlNode; scope: Map<string, string> }> = [];
  let root: XmlNode | null = null;
  let pos = 0;
  const len = input.length;
  while (pos < len) {
    const lt = input.indexOf("<", pos);
    const textEnd = lt === -1 ? len : lt;
    if (textEnd > pos && stack.length > 0) {
      const top = stack[stack.length - 1]!.node;
      if (top.children.length === 0) top.text += decode(input.slice(pos, textEnd));
    }
    if (lt === -1) break;
    if (input.startsWith("<!--", lt)) {
      const end = input.indexOf("-->", lt + 4);
      if (end === -1) throw new Error("unterminated comment");
      pos = end + 3;
    } else if (input.startsWith("<![CDATA[", lt)) {
      const end = input.indexOf("]]>", lt + 9);
      if (end === -1) throw new Error("unterminated CDATA");
      if (stack.length > 0) {
        const top = stack[stack.length - 1]!.node;
        if (top.children.length === 0) top.text += input.slice(lt + 9, end);
      }
      pos = end + 3;
    } else if (input.startsWith("<?", lt)) {
      const end = input.indexOf("?>", lt + 2);
      if (end === -1) throw new Error("unterminated declaration");
      pos = end + 2;
    } else if (input.startsWith("<!", lt)) {
      const end = input.indexOf(">", lt + 2);
      if (end === -1) throw new Error("unterminated declaration");
      pos = end + 1;
    } else if (input.startsWith("</", lt)) {
      const end = input.indexOf(">", lt + 2);
      if (end === -1) throw new Error("unterminated end tag");
      if (stack.length === 0) throw new Error("unexpected end tag");
      stack.pop();
      pos = end + 1;
    } else {
      // start tag: find the closing ">" outside quotes
      let i = lt + 1;
      let quote = "";
      for (; i < len; i++) {
        const ch = input[i]!;
        if (quote) {
          if (ch === quote) quote = "";
        } else if (ch === '"' || ch === "'") quote = ch;
        else if (ch === ">") break;
      }
      if (i >= len) throw new Error("unterminated start tag");
      let inner = input.slice(lt + 1, i);
      const selfClosing = inner.endsWith("/");
      if (selfClosing) inner = inner.slice(0, -1);
      const nameMatch = /^[^\s\/>]+/.exec(inner);
      if (!nameMatch) throw new Error("bad start tag");
      const qname = nameMatch[0];
      const rawAttrs: Array<[string, string]> = [];
      const scope = new Map(stack.length > 0 ? stack[stack.length - 1]!.scope : []);
      ATTR.lastIndex = qname.length;
      let m: RegExpExecArray | null;
      while ((m = ATTR.exec(inner)) !== null) {
        const value = decode(m[2] ?? m[3] ?? "");
        if (m[1] === "xmlns") scope.set("", value);
        else if (m[1]!.startsWith("xmlns:")) scope.set(m[1]!.slice(6), value);
        else rawAttrs.push([m[1]!, value]);
      }
      const attrs: XmlAttr[] = rawAttrs.map(([key, value]) => {
        const colon = key.indexOf(":");
        if (colon === -1) return { uri: "", local: key, value };
        return { uri: scope.get(key.slice(0, colon)) ?? "", local: key.slice(colon + 1), value };
      });
      const node: XmlNode = {
        name: qname.slice(qname.indexOf(":") + 1),
        attrs,
        text: "",
        children: [],
      };
      if (stack.length > 0) stack[stack.length - 1]!.node.children.push(node);
      else if (root === null) root = node;
      else throw new Error("more than one root element");
      if (!selfClosing) stack.push({ node, scope });
      pos = i + 1;
    }
  }
  if (root === null) throw new Error("no root element");
  if (stack.length > 0) throw new Error("unclosed element");
  return root;
}

/** The value of the attribute with this local name and namespace uri ("" for none), if any. */
export function attr(node: XmlNode, local: string, uri = ""): string | undefined {
  return node.attrs.find((a) => a.local === local && a.uri === uri)?.value;
}
