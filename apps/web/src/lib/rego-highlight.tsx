import { Fragment, type ReactNode } from "react";

/**
 * A small Rego highlighter.
 *
 * Hand-rolled rather than pulling in a highlighting library: Rego has no
 * off-the-shelf grammar in the common bundles anyway, and the language's
 * surface is small enough that a tokenizer covering keywords, strings,
 * comments, numbers and rule heads reads better than a generic fallback.
 *
 * It is presentational only — the policies are rendered read-only.
 */
const KEYWORDS = new Set([
  "package", "import", "default", "not", "with", "as", "some", "every",
  "in", "if", "contains", "else", "null", "true", "false",
]);

const BUILTINS = new Set([
  "count", "sum", "max", "min", "sort", "union", "object", "input", "data",
  "startswith", "endswith", "sprintf", "to_number", "split", "concat",
]);

type Token = { text: string; kind: string };

const PATTERN = new RegExp(
  [
    "(#[^\\n]*)", // comment
    '("(?:[^"\\\\]|\\\\.)*")', // string
    "(\\b\\d+(?:\\.\\d+)?\\b)", // number
    "([A-Za-z_][A-Za-z0-9_]*)", // word
    "(:=|==|!=|>=|<=|=|\\[|\\]|\\{|\\}|\\(|\\)|,|\\.|;|\\+|-|\\*|/|<|>)", // punctuation
    "(\\s+)", // whitespace
  ].join("|"),
  "g",
);

// Syntax colours here are deliberately NOT the product's reserved status hues
// (allow/approval/block) — this is a code viewer, not a decision surface, and
// reusing those three would blur the one rule the rest of the UI depends on.
const CLASS: Record<string, string> = {
  comment: "text-ink-muted italic",
  string: "text-[#0B7285]",
  number: "text-[#9333EA]",
  keyword: "text-accent",
  builtin: "text-[#2563EB]",
  punct: "text-ink-muted",
  plain: "text-ink",
};

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let match: RegExpExecArray | null;
  PATTERN.lastIndex = 0;
  while ((match = PATTERN.exec(source)) !== null) {
    const [text, comment, str, num, word, punct, space] = match;
    if (comment !== undefined) tokens.push({ text, kind: "comment" });
    else if (str !== undefined) tokens.push({ text, kind: "string" });
    else if (num !== undefined) tokens.push({ text, kind: "number" });
    else if (word !== undefined)
      tokens.push({
        text,
        kind: KEYWORDS.has(word) ? "keyword" : BUILTINS.has(word) ? "builtin" : "plain",
      });
    else if (punct !== undefined) tokens.push({ text, kind: "punct" });
    else if (space !== undefined) tokens.push({ text, kind: "plain" });
  }
  return tokens;
}

export function highlightRego(source: string): ReactNode {
  return tokenize(source).map((token, index) => (
    <span key={index} className={CLASS[token.kind] ?? CLASS.plain}>
      {token.text}
    </span>
  ));
}

export function RegoBlock({ source }: { source: string }) {
  const lines = source.split("\n");
  return (
    <pre className="overflow-x-auto p-3 font-mono text-[11px] leading-[1.65]">
      <code>
        {lines.map((line, index) => (
          <Fragment key={index}>
            <span className="mr-3 inline-block w-7 select-none text-right text-ink-muted/60">
              {index + 1}
            </span>
            {highlightRego(line)}
            {"\n"}
          </Fragment>
        ))}
      </code>
    </pre>
  );
}
