#!/usr/bin/env python3
"""Checks a plugin's i18n catalogs against en.json and the code that uses them.

  i18n_check.py I18N_DIR [--sources DIR ...]   report problems, exit 1 on any
  i18n_check.py I18N_DIR --en-only ...          the same for en.json alone, before translations exist
  i18n_check.py I18N_DIR --stamp LANG ...       record LANG as translated from the current English
  i18n_check.py I18N_DIR --pseudo OUT.json      write a longer pseudo-language for layout tests
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

LANGUAGES = ["pl", "de", "fr", "es-MX", "pt-BR", "it", "nl", "ru", "uk", "zh-CN", "ja"]
MANIFEST = "translation-manifest.json"
# Tr.t / Tr.tn in QML and JS; tr / trn in Python; i18n_t / i18n_tn in shell.
USE = re.compile(r"""(?:\bTr\.tn?|\btrn?|\bi18n_tn?)\(\s*["']([A-Za-z0-9_.-]+)["']""")
SOURCE_SUFFIXES = {".qml", ".js", ".py", ".sh", ""}
PLACEHOLDER = re.compile(r"%(\d)")


def category(code, n):
    n = abs(int(n))
    n10, n100 = n % 10, n % 100
    millions = n != 0 and n % 1000000 == 0
    if code in ("ja", "zh-CN"):
        return "other"
    if code in ("fr", "pt-BR"):
        return "one" if n <= 1 else "many" if millions else "other"
    if code in ("es-MX", "it"):
        return "one" if n == 1 else "many" if millions else "other"
    if code in ("pl", "ru", "uk"):
        if code == "pl" and n == 1 or code != "pl" and n10 == 1 and n100 != 11:
            return "one"
        return "few" if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else "many"
    return "one" if n == 1 else "other"


def categories(code):
    seen = {category(code, n) for n in list(range(1001)) + [1000000]} | {"other"}
    return [c for c in ("zero", "one", "two", "few", "many", "other") if c in seen]


def load(path):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return None, f"{path.name}: {error}"
    if not isinstance(data, dict):
        return None, f"{path.name}: not a JSON object"
    return data, None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def placeholders(value):
    texts = value.values() if isinstance(value, dict) else [value]
    return set().union(*(set(PLACEHOLDER.findall(t)) for t in texts if isinstance(t, str)))


def check_entry(lang, key, en, tr, errors):
    if isinstance(en, dict) != isinstance(tr, dict):
        errors.append(f"{lang}: {key}: plural shape differs from en")
        return
    if isinstance(tr, dict):
        if not all(isinstance(v, str) and v for v in tr.values()):
            errors.append(f"{lang}: {key}: empty or non-string plural form")
        missing = [c for c in categories(lang) if c not in tr]
        if missing:
            errors.append(f"{lang}: {key}: plural forms missing {missing}")
        for form, text in tr.items():
            if placeholders(en) != placeholders(text):
                errors.append(f"{lang}: {key}.{form}: placeholders {sorted(placeholders(text))}, en has {sorted(placeholders(en))}")
    elif not isinstance(tr, str) or not tr:
        errors.append(f"{lang}: {key}: empty or not a string")
    elif placeholders(en) != placeholders(tr):
        errors.append(f"{lang}: {key}: placeholders {sorted(placeholders(tr))}, en has {sorted(placeholders(en))}")


def used_keys(dirs, skip):
    found = {}
    for root in dirs:
        for path in pathlib.Path(root).rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES and skip not in path.parents and path.stat().st_size < 2_000_000:
                try:
                    text = path.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
                for key in USE.findall(text):
                    found.setdefault(key, str(path))
    return found


def pseudo(text):
    swap = str.maketrans("aceinosuyACEINOSUY", "àçéîñöšûýÀÇÉÎÑÖŠÛÝ")
    parts = re.split(r"(%\d)", text)
    body = "".join(p if PLACEHOLDER.fullmatch(p) else p.translate(swap) for p in parts)
    return "[" + body + "~" * max(2, len(text) * 2 // 5) + "]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir", type=pathlib.Path)
    parser.add_argument("--sources", nargs="*", default=[])
    parser.add_argument("--stamp", nargs="*")
    parser.add_argument("--pseudo", type=pathlib.Path)
    parser.add_argument("--en-only", action="store_true")
    args = parser.parse_args()

    en, error = load(args.dir / "en.json")
    if en is None:
        sys.exit(error)
    manifest_path = args.dir / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    if args.pseudo:
        args.pseudo.write_text(json.dumps({k: ({f: pseudo(t) for f, t in v.items()} if isinstance(v, dict) else pseudo(v))
                                           for k, v in en.items()}, ensure_ascii=False, indent=2) + "\n")
        return
    if args.stamp:
        for lang in args.stamp:
            catalog, error = load(args.dir / f"{lang}.json")
            if catalog is None:
                sys.exit(error)
            manifest[lang] = {key: digest(en[key]) for key in sorted(catalog) if key in en}
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return

    errors, warnings = [], []
    for lang in [] if args.en_only else LANGUAGES:
        path = args.dir / f"{lang}.json"
        if not path.exists():
            errors.append(f"{lang}: no {path.name}")
            continue
        catalog, error = load(path)
        if catalog is None:
            errors.append(str(error))
            continue
        stamps = manifest.get(lang, {})
        for key in sorted(en.keys() - catalog.keys()):
            errors.append(f"{lang}: {key}: missing")
        for key in sorted(catalog.keys() - en.keys()):
            errors.append(f"{lang}: {key}: not in en.json")
        for key in sorted(en.keys() & catalog.keys()):
            check_entry(lang, key, en[key], catalog[key], errors)
            if stamps.get(key) != digest(en[key]):
                errors.append(f"{lang}: {key}: stale or unstamped (English changed since translation; run --stamp after updating)")
    for path in sorted(args.dir.glob("*.json")):
        if path.stem not in LANGUAGES + ["en"] and path.name != MANIFEST:
            warnings.append(f"{path.name}: not a shipped language")
    if args.sources:
        used = used_keys(args.sources, args.dir.resolve())
        for key, where in sorted(used.items()):
            if key not in en:
                errors.append(f"en: {key}: used in {where} but missing")
        for key in sorted(en.keys() - used.keys()):
            warnings.append(f"en: {key}: never used as a literal key (fine if built at runtime)")

    for line in warnings:
        print("warning: " + line)
    for line in errors:
        print("error: " + line)
    print(f"{len(en)} keys, {len(LANGUAGES)} languages, {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
