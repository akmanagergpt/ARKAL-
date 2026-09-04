#!/usr/bin/env node
/**
 * Real, parser-backed structural inspection of JS/JSX/TS/TSX source files
 * under one directory -- for `engineering.product_change`'s own source
 * inspection step (D-030). Read-only: nothing here writes, executes, or
 * imports anything from the inspected tree; every file is parsed as
 * syntax only, via the TypeScript compiler's own `createSourceFile`
 * (handles plain JS/JSX too, not just `.ts`/`.tsx`).
 *
 * WHY THIS REUSES `frontend/node_modules/typescript` RATHER THAN A NEW
 * DEPENDENCY. ARKALI's own frontend toolchain already installs the real
 * TypeScript compiler package; this script resolves it from there instead
 * of adding a second parser dependency anywhere.
 *
 * Usage: node scripts/inspect_js_source.mjs <directory>
 * Output: one JSON object on stdout: { files: [ { path, kind, imports,
 *   declarations, jsxElements, byteLength } ], errors: [ { path, message } ] }
 */

import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPTS_DIR, '..');
const require = createRequire(path.join(ROOT, 'frontend', 'package.json'));
const ts = require('typescript');

const SKIP_DIR_NAMES = new Set(['node_modules', 'build', 'dist', '.git', 'coverage']);
const SOURCE_EXTENSIONS = new Set(['.js', '.jsx', '.ts', '.tsx']);

function listSourceFiles(root) {
  const found = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (!SKIP_DIR_NAMES.has(entry.name)) stack.push(full);
      } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
        found.push(full);
      }
    }
  }
  found.sort();
  return found;
}

function scriptKindFor(filePath) {
  switch (path.extname(filePath)) {
    case '.tsx':
      return ts.ScriptKind.TSX;
    case '.ts':
      return ts.ScriptKind.TS;
    case '.jsx':
      return ts.ScriptKind.JSX;
    default:
      return ts.ScriptKind.JS;
  }
}

function inspectOne(filePath, root) {
  const relative = path.relative(root, filePath).split(path.sep).join('/');
  const text = fs.readFileSync(filePath, 'utf8');
  const source = ts.createSourceFile(
    filePath, text, ts.ScriptTarget.Latest, true, scriptKindFor(filePath),
  );
  const imports = [];
  const declarations = [];
  const jsxElements = new Set();

  function walk(node) {
    if (ts.isImportDeclaration(node) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      imports.push(node.moduleSpecifier.text);
    } else if (ts.isFunctionDeclaration(node) && node.name) {
      declarations.push({ kind: 'function', name: node.name.text });
    } else if (ts.isClassDeclaration(node) && node.name) {
      declarations.push({ kind: 'class', name: node.name.text });
    } else if (ts.isVariableStatement(node)) {
      for (const decl of node.declarationList.declarations) {
        if (ts.isIdentifier(decl.name)) {
          declarations.push({ kind: 'const', name: decl.name.text });
        }
      }
    } else if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tagName = node.tagName;
      if (ts.isIdentifier(tagName)) jsxElements.add(tagName.text);
    }
    ts.forEachChild(node, walk);
  }
  walk(source);

  return {
    path: relative,
    kind: ts.ScriptKind[scriptKindFor(filePath)],
    imports: [...new Set(imports)].sort(),
    declarations,
    jsxElements: [...jsxElements].sort(),
    byteLength: Buffer.byteLength(text, 'utf8'),
  };
}

function main() {
  const target = process.argv[2];
  if (!target) {
    console.error('usage: node inspect_js_source.mjs <directory>');
    process.exit(2);
  }
  const root = path.resolve(target);
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    console.error(`not a directory: ${root}`);
    process.exit(2);
  }
  const files = [];
  const errors = [];
  for (const filePath of listSourceFiles(root)) {
    try {
      files.push(inspectOne(filePath, root));
    } catch (error) {
      errors.push({ path: path.relative(root, filePath), message: String(error && error.message || error) });
    }
  }
  process.stdout.write(JSON.stringify({ files, errors }));
}

main();
