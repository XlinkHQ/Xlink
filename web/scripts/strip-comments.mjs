import { readFileSync, writeFileSync } from "node:fs";
import ts from "typescript";

const files = process.argv.slice(2);
let changed = 0;

for (const file of files) {
  const src = readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const ranges = [];
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, ts.LanguageVariant.JSX, src);

  const visit = (node) => {
    const full = node.getFullStart();
    const start = node.getStart(sf);
    if (full < start) {
      const lead = ts.getLeadingCommentRanges(src, full);
      if (lead) for (const c of lead) ranges.push([c.pos, c.end, c.kind]);
    }
    const trail = ts.getTrailingCommentRanges(src, node.getEnd());
    if (trail) for (const c of trail) ranges.push([c.pos, c.end, c.kind]);
    ts.forEachChild(node, visit);
  };
  visit(sf);
  void scanner;

  if (ranges.length === 0) continue;

  const seen = new Set();
  const uniq = ranges
    .filter(([p, e]) => {
      const k = p + ":" + e;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .sort((a, b) => b[0] - a[0]);

  let out = src;
  for (const [pos, end, kind] of uniq) {
    let cutStart = pos;
    let cutEnd = end;
    if (kind === ts.SyntaxKind.SingleLineCommentTrivia) {
      while (cutStart > 0 && (out[cutStart - 1] === " " || out[cutStart - 1] === "\t")) cutStart--;
      if (out[cutEnd] === "\r") cutEnd++;
      if (out[cutEnd] === "\n") cutEnd++;
      if (out[cutStart - 1] === "\n" || cutStart === 0) {
        out = out.slice(0, cutStart) + out.slice(cutEnd);
        continue;
      }
    }
    out = out.slice(0, cutStart) + out.slice(cutEnd);
  }

  out = out.replace(/\n{3,}/g, "\n\n");
  if (out !== src) {
    writeFileSync(file, out);
    changed++;
  }
}

console.log(`stripped ${changed}/${files.length} files`);
