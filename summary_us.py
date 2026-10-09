import re

_BIRADS_RE = re.compile(r"BI-?RADS\s*(\d)", re.I)


def us_label(name):
    """The yellow notes' region label for a `US ...` order name
    (rule 9c): the first matching keyword's label, else the first
    name word that is not the `us` / `plus` / `ultrasound` shorthand
    or a `2d` / `3d` view tag."""
    for keyword, label in (
            ("aaa", "AAA"),
            ("elastography", "abd w/ liver elastography"),
            ("breast", "breast"),
            ("thyroid", "thyroid"),
            ("renal", "renal"),
            ("pelvic", "pelvic"),
            ("carotid", "carotid"),
            ("neck", "neck"),
            ("soft tissue", "soft tissue"),
            ("testicular", "testicular"),
            ("abdomen", "abd"),
            ("abdominal", "abd"),
    ):
        if keyword in name:
            return label
    for word in re.split(r"\W+", name):
        if word not in ("", "us", "plus", "ultrasound", "2d", "3d"):
            return word
    return "us"


# Report tails that end the `IMPRESSION` section (rule 9c).
_US_TAIL_RE = re.compile(
    r"electronically\s+signed|a\s+letter\s+stating"
    r"|in\s+compliance\s+with\s+mqsa|thank\s+you\s+for", re.I)


def _us_impression(notes):
    """The report's `IMPRESSION` section text -- the head is
    `IMPRESSION` / `CONCLUSION` / `ASSESSMENT...` (the Plus breast
    reports' `ASSESSMENT/MANAGEMENT`); when the report carries no
    such head, the whole report -- without the signed-by / letter /
    MQSA tail (rule 9c)."""
    m = re.search(r"^\s*(?:IMPRESSION|CONCLUSION|ASSESSMENT[^:]*)\s*:\s*",
                  notes, re.M | re.I)
    rest = notes[m.end():] if m is not None else notes
    if m := _US_TAIL_RE.search(rest):
        rest = rest[:m.start()]
    return rest


# Impression sentences that are boilerplate or advice, not findings
# (rule 9c): the lifetime-risk / Tyrer-Cuzick lines, the `BI-RADS` /
# `LI-RADS` assessment lines, the ACR TI-RADS guideline block and its
# source / disclaimer lines, the radiologist-signature lines (an
# `M.D.` / `DABR` / `CAQ` line), the `Given the positive findings`
# transmission line, the `refer to` deferral, the `rescanning may be
# considered` / `nonspecific finding` lines, the annual-screening-
# scheduling lines, the report's `Exam #` / `Exam Performed at` head
# lines (the reports with no `IMPRESSION` head), the liver-fat
# grading-scale lines (`Liver fat is graded...` / `hepatocytes
# contain fat` / `Grade N (...) = ...`), and the `correlate with
# ... laboratory parameters` / `clinical correlation` advice lines.
_US_SKIP_RE = re.compile(
    r"lifetime\s+risk|tyrer-?cuzick|breast\s+cancer\s+risk"
    r"|^\s*bi-?rads\b|^\s*li-?rads\b"
    r"|american\s+college\s+of\s+radiology|ti-?rads\s*\(tr\)"
    r"|\bTR\d\s*:|follow-up\s+ultrasound\s+guidelines"
    r"|^\s*source:|\btesler\b|j\s*am\s*coll\s*radiol|koios\s+ai\s+adapter"
    r"|\bM\.D\.?|\bDABR\b|\bCAQ\b"
    r"|\bgiven\s+the\s+positive\s+findings\b"
    r"|^\s*refer\s+to\b|^\s*exam\s*#|^\s*exam\s+performed\s+at\b"
    r"|\brescanning\s+may\s+be\s+considered|\bnonspecific\s+finding\b"
    r"|annual\s+routine\s+bilateral\s+screening"
    r"|increased\s+breast\s+density|adding\s+screening\s+ultrasound"
    r"|liver fat is graded|hepatocytes contain fat|^\s*grade \d+ \("
    r"|\bcorrelate\b.*\blaboratory\b|\bclinical\s+correlation\b"
    r"|^\s*correlate\s+with\b"
    r"|\bcorrelation\s+is\s+advised\b"
    r"|\bcorrelation\s+with\s+(?:liver\s+function\s+tests?|laboratory)\b",
    re.I)
# A two-word name line (a radiologist's signature on the old
# Health-Diagnostics reports), case-sensitive (rule 9c).
_US_NAME_LINE_RE = re.compile(r"^\s*[\w.]+ [A-Z][\w.]*$")
# Negative-statement / limitation phrases that make an impression
# sentence an `nl` statement, not a finding (rule 9c): a `... are
# obscured` sentence is the exam's limitation, not a finding.
_US_NEG_PHRASE_RE = re.compile(
    r"unremarkable|\bwithin normal limits\b|no evidence|no acute process"
    r"|no other significant|no abnormal|\bwithout residual abnormality\b"
    r"|\bwithout focal\b|\bis not seen\b|\bnot seen at present\b|\bobscured\b"
    r"|\bno significant interval change\b|\bno further follow-?up\b"
    r"|not significantly changed|\bappears? (?:to be )?normal\b|\bis normal\b",
    re.I)
# The finding words that keep a `No ...` / `Normal ...` sentence a
# finding (a followed-up mass, a stone, a nodule `measuring` a size,
# a fatty liver) (rule 9c).
_US_FINDING_RE = re.compile(
    r"\bmasses?\b|\bpolyps?\b|\bstones?\b|\bcalcul|\bplaques?\b"
    r"|\bnodules?[^.]*\bmeasuring\b|\bfatty\b|\bsteatos", re.I)


def us_findings(notes):
    rest = _us_impression(notes)
    # The breast report's `BI-RADS {n}` assessment line is not a
    # finding, nor is anything after it; the same for the ACR
    # TI-RADS guideline block, the WFUMB elastography guideline
    # table and the Koios disclaimer that trail the impression.
    for cut in (r"\bBI-?RADS\b", r"american\s+college\s+of\s+radiology",
                r"world\s+federation\s+of\s+ultrasound",
                r"koios\s+ai\s+adapter"):
        if m := re.search(cut, rest, re.I):
            rest = rest[:m.start()]
    # The `1. ` / `2. ` numbering is dropped; a lower-case-opening
    # (or parenthetical) line continues the previous line's sentence
    # (a wrapped sentence, eg the carotid report's `... stenosis on
    # either / side.`).
    segs = []
    for raw in rest.splitlines():
        line = re.sub(r"^\s*\d+\.\s*", "", raw.strip())
        if not line:
            continue
        if segs and (line[0].islower() or line[0] in "(-"):
            segs[-1] += " " + line
        else:
            segs.append(line)
    findings = []
    any_sent = False
    for seg in segs:
        seg = re.sub(r"\s+", " ", seg).strip()
        for sent in re.split(r"(?<=[.!?;])\s+(?=[A-Z\"(])", seg):
            sent = sent.strip()
            if not sent or _US_SKIP_RE.search(sent) \
                    or _US_NAME_LINE_RE.search(sent):
                continue
            any_sent = True
            if _US_NEG_PHRASE_RE.search(sent):
                continue
            if (re.match(r"^(?:no|non)[\s\-]", sent, re.I)
                    or re.match(r"^(?:otherwise\s+)?normal\b", sent, re.I)):
                if not _US_FINDING_RE.search(sent):
                    continue
            findings.append(sent.rstrip("."))
    return findings, any_sent


def us_token(notes, label):
    matches = list(_BIRADS_RE.finditer(notes))
    if matches:
        n = int(matches[-1].group(1))
        if n in (1, 2):
            return f"US {label} nl"
    findings, any_sent = us_findings(notes)
    if not any_sent or (matches and not findings):
        return None
    if not findings:
        return f"US {label} nl"
    return f"US {label}: " + ". ".join(findings)

