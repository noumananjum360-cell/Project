"""Pakistani vehicle number plate formats.

Registration numbers in Pakistan are essentially an alphabetic series code
followed by a serial number, written e.g. "LEA-1234", "BKF 456", "ICT-123" or
"A 1234" (KP). Provinces add small header text (PUNJAB, SINDH, ...) and some
show the registration year, which we ignore. Commercial goods vehicles in Sindh
commonly carry "TL?" style series codes.

This module normalises noisy OCR output into a canonical ``LETTERS-DIGITS``
form, fixes the usual letter/digit confusions using the position (a series code
is letters, the serial is digits), guesses the province, and scores how
plausible the result is.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

# Series prefixes by province (non exhaustive - used only as a hint).
PUNJAB_PREFIXES = [
    "LEA", "LEB", "LEC", "LED", "LEE", "LEF", "LEH", "LER", "LES", "LEZ",
    "RIK", "RIL", "RIM", "FDA", "FDB", "FDC", "MNA", "MNB", "GAA", "GAB",
    "SGA", "SKA", "BRA", "DGA", "RYK", "BWP", "SLA", "JHA", "OKA", "LEJ",
]
SINDH_PREFIXES = [
    "AAA", "ABC", "AEF", "AFR", "AJK", "AKZ", "ALM", "AXL", "AYD", "BAA",
    "BKF", "BKM", "BSB", "BTE", "HDA", "HDB", "SKR", "LRK", "TLA", "TLB",
    "TLC", "TLE", "TLF", "TLG", "TLH", "TLJ", "TLK", "TLM", "JY", "JV",
]
KP_PREFIXES = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "PR", "MRD", "ABT", "SWT"]
BALOCHISTAN_PREFIXES = ["QAA", "QAB", "QAC", "QAD", "BAA", "BAB", "BLC", "TRB", "GWD"]
ICT_PREFIXES = ["ICT", "IDA", "IDB", "IDC", "IDD", "IDE", "IDF", "AN", "BF", "EP", "GA", "RIZ"]

PROVINCE_HEADERS = {
    "Punjab": "PUNJAB",
    "Sindh": "SINDH",
    "KP": "KHYBER PAKHTUNKHWA",
    "Balochistan": "BALOCHISTAN",
    "ICT": "ISLAMABAD",
}

_LETTER_FIX = {"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B"}
_DIGIT_FIX = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "T": "7", "Z": "2",
              "S": "5", "B": "8", "G": "6", "A": "4", "J": "1"}

PLATE_RE = re.compile(r"^([A-Z]{1,4})-([0-9]{1,4})$")


@dataclass
class PlateParse:
    raw: str
    text: str            # canonical "LEA-1234" (empty if unparseable)
    province: str        # Punjab/Sindh/KP/Balochistan/ICT/Unknown
    commercial: bool
    plausibility: float  # 0..1


def clean(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def guess_province(letters: str) -> str:
    for name, prefixes in (("ICT", ICT_PREFIXES), ("Punjab", PUNJAB_PREFIXES),
                           ("Sindh", SINDH_PREFIXES), ("Balochistan", BALOCHISTAN_PREFIXES),
                           ("KP", KP_PREFIXES)):
        if letters in prefixes:
            return name
    if letters.startswith("TL") or letters.startswith("J"):
        return "Sindh"
    if letters.startswith("Q"):
        return "Balochistan"
    if letters.startswith("ID") or letters == "ICT":
        return "ICT"
    if len(letters) == 3 and letters[:2] in {"LE", "RI", "FD", "MN", "GA"}:
        return "Punjab"
    return "Unknown"


def parse(raw: str) -> PlateParse:
    """Normalise OCR output into a canonical plate string."""
    s = clean(raw)
    if not s:
        return PlateParse(raw, "", "Unknown", False, 0.0)
    # Find split point: longest leading run that "should" be letters. A series
    # code has 1-4 chars and starts with a letter; the serial is the rest.
    best = None
    for k in range(1, min(4, len(s) - 1) + 1):
        letters, digits = s[:k], s[k:]
        if not (1 <= len(digits) <= 4):
            continue
        fixes = 0
        lf = []
        for ch in letters:
            if ch.isalpha():
                lf.append(ch)
            elif ch in _LETTER_FIX:
                lf.append(_LETTER_FIX[ch]); fixes += 1
            else:
                lf = None; break
        if lf is None:
            continue
        df = []
        for ch in digits:
            if ch.isdigit():
                df.append(ch)
            elif ch in _DIGIT_FIX:
                df.append(_DIGIT_FIX[ch]); fixes += 1
            else:
                df = None; break
        if df is None:
            continue
        letters_f, digits_f = "".join(lf), "".join(df)
        prov = guess_province(letters_f)
        score = 1.0 - 0.15 * fixes
        if prov != "Unknown":
            score += 0.1
        if len(letters_f) in (2, 3):
            score += 0.05
        if len(digits_f) in (3, 4):
            score += 0.05
        cand = (score, letters_f, digits_f, prov)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return PlateParse(raw, "", "Unknown", False, 0.0)
    score, letters, digits, prov = best
    commercial = letters.startswith("TL") or letters.startswith("J") or letters.startswith("C")
    return PlateParse(raw, f"{letters}-{digits}", prov, commercial, max(0.0, min(1.0, score)))


def canonical(text: str) -> str:
    p = parse(text)
    return p.text or clean(text)


def edit_distance(a: str, b: str) -> int:
    a, b = clean(a), clean(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def plates_match(a: str, b: str, max_distance: int = 1) -> bool:
    if not a or not b:
        return False
    return edit_distance(canonical(a), canonical(b)) <= max_distance


def random_plate(rng: random.Random | None = None) -> tuple[str, str]:
    """Generate a realistic random plate (text, province) for synthetic data."""
    rng = rng or random.Random()
    prov = rng.choice(["Punjab", "Punjab", "Sindh", "Sindh", "KP", "Balochistan", "ICT"])
    pool = {"Punjab": PUNJAB_PREFIXES, "Sindh": SINDH_PREFIXES, "KP": KP_PREFIXES,
            "Balochistan": BALOCHISTAN_PREFIXES, "ICT": ICT_PREFIXES}[prov]
    letters = rng.choice(pool)
    digits = str(rng.randint(1, 9999 if len(letters) <= 2 else 9999))
    if rng.random() < 0.3:
        digits = str(rng.randint(100, 999))
    return f"{letters}-{digits}", prov
