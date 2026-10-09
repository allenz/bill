import re

def ct_label(name):
    if "chest" in name or "thorax" in name or "thoracic" in name:
        return "chest"
    if "head" in name or "brain" in name:
        return "head"
    if "abdomen" in name or "abdominal" in name:
        if "pelvis" in name or "pelvic" in name:
            return "abd/pelvic"
        return "abd"
    for part in re.split(r"[\s\-]+", name):
        if part not in ("", "ct"):
            return part
    return "ct"


# The report tails that end the `IMPRESSION` section (rule 9e): the
# signed-by / radiologist-hotline / referral-letter lines, the
# report's `RECOMMENDATION` / `DIAGNOSES` / `ADDENDUM` / `DISCLAIMER`
# section heads, and the `FLEISCHNER SOCIETY FOLLOW-UP GUIDELINES`
# head whose nodule-size table trails the impression.
_CT_TAIL_RE = re.compile(
    r"electronically\s+signed\s+by"
    r"|thank\s+you\s+for"
    r"|radiologist\s+hotline"
    r"|^\s*(?:recommendations?|diagnoses|addendum|disclaimer)\s*:"
    r"|^\s*recommended\s+follow[- ]?up\s*:?\s*$"
    r"|^\s*fleischner\s+society\b"
    r"|^\s*computed tomography\s+of\b|^\s*history\s*:"
    r"|^\s*findings\s*:", re.M | re.I)
# The Fleischner / ACR-White-Paper guideline citations that trail a
# finding's follow-up sentence (rule 9e): the citation and the
# guideline's own recommendation text are not part of the finding.
_CT_GUIDE_CITE_RE = re.compile(
    r"\b(?:\d{4}\s+ACR\s+)?Fleischner\b|\bACR\s+White\s+Paper\b"
    r"|\bMacMahon\b|Herts et al", re.I)
# Impression sentences that are boilerplate or counseling, not
# findings (rule 9e): the report-transmission lines, the radiologist-
# signature lines (an `M.D.` / `Diplomate` / `CAQ` line), the emphysema
# report's LDCT-screening counseling block, the `recommendation applies
# unless` / `advised to consult` advice lines, the AI nodule-detection
# disclaimer lines, the guideline-citation journal lines that the
# sentence split leaves behind, and the exam-head / technique / dose
# lines of a report with no `IMPRESSION` section (the
# `_ct_impression`'s head check keeps those out of the impression;
# the lines are skipped for safety), the `chronic and ancillary` /
# `Please see above` filler lines, and the LUNG-RADS template's
# version / category lines.
_CT_SKIP_RE = re.compile(
    r"^\s*exam\s*#|^\s*exam\s+performed\s+at\b"
    r"|^\s*indication\b|^\s*technique\b|^\s*comparison\b"
    r"|^\s*contrast\s*:|radiation\s+dose|ctdi\s+volume|\balara\b"
    r"|optiray|\bdlp\b|prior known ct or cardiac"
    r"|given\s+the\s+positive\s+findings|simonmed\s+assistant"
    r"|to be communicated to the ordering"
    r"|\bM\.D\.?\b|\bDiplomate\b|American Board of Radiology"
    r"|\bCAQ\b|\bDABR\b"
    r"|\bdisclaimer\b|ai lung nodule detection|nodule prediction"
    r"|ai-assisted analysis|refer to the radiologist"
    r"|independent\s+risk\s+factor\s+for\s+lung\s+cancer"
    r"|\bldct\b|low-dose\s+ct\s+(?:lung\s+cancer\s+)?screening"
    r"|\bconsider\s+enrollment\b|recommendation\s+applies\s+unless"
    r"|\badvised\s+to\s+consult\b|comprehensive\s+cardiovascular\s+risk"
    r"|baseline\s+for\s+future\s+screening"
    r"|chronic\s+and\s+ancillary|please\s+see\s+above"
    r"|^\s*clinical\s+indication\b|contrast\s+used\b|highest\s+ctdi\b"
    r"|multiplanar\s+reconstructions"
    r"|\bversion\s+\d\s+\.\s+\d\s+edition\b|^\s*category\s+\d"
    r"|correlation with urine analysis"
    r"|\bet\s+al\b|\bJ\s+Am\s+Coll\s+Radiol\b"
    r"|\bRadiology\s+\d{4}\b|\bsuggest\s+the\s+following\b"
    r"|\bhigh\s+index\s+of\s+suspicion\b"
    r"|\bas\s+clinically\s+indicated\b"
    r"|\bclinical\s+correlation\b", re.I)
# A `No A, B or C ...` list of absent findings (the head reports'
# `No hemorrhage, mass or large infarct identified`, `No free fluid
# or free air`) is a negative statement, not a finding (rule 9e).
_CT_NEG_LIST_RE = re.compile(r"^\s*no\s+.+\bor\b", re.I)
# Negative-statement phrases that make an impression sentence an `nl`
# statement, not a finding (rule 9e).
_CT_NEG_PHRASE_RE = re.compile(
    r"unremarkable|\bwithin normal limits\b|\bno evidence\b"
    r"|\bno acute\b|\bno abnormal\b|\bno suspicious\b|\bno focal\b"
    r"|\bno definite\b"
    r"|\bno\s+(?:other\s+|additional\s+)?significant\b"
    r"|\bno significant interval change\b"
    r"|\bno need for (?:further\s+)?follow-?up\b"
    r"|\bno further (?:follow-?up|evaluation)\b"
    r"|\bno hemorrhage\b"
    r"|\bnot (?:seen|dilated|enlarged)\b|\bis not seen\b"
    r"|\bappears? (?:to be )?normal\b|\bis normal\b|\bgrossly normal\b"
    r"|\bno (?:free fluid|free air)\b", re.I)
# The finding words that keep a `No ...` / `Normal ...` sentence a
# finding (a followed-up mass, a nodule `measuring` a size, a fatty
# liver) (rule 9e).
_CT_FINDING_RE = re.compile(
    r"\bmasses?\b|\bcysts?\b|\bstones?\b|\bcalcul\w*"
    r"|\bnodules?[^.]*\bmeasuring\b|\bfatty\b|\bsteatos\b", re.I)
# A bare two-word line / sentence with no punctuation (the
# radiologist's signature name `Piampiano Peter` / `ZINN WILLIAM`, the
# report's `Or her` dictation typo) is not a finding (rule 9e).
_CT_NAME_LINE_RE = re.compile(r"^\s*[A-Z]\w*\s+\w+\s*$")
# A bare all-caps section header with nothing after its colon (the
# report template's empty `MIPS:` attestation line) is not a finding
# (rule 9e).
_CT_HEADER_RE = re.compile(r"^\s*[A-Z][A-Z0-9 /&\-]*:\s*$")
# Remove just the trailing cross-reference in a finding sentence
# (`..., and additional findings as above`,
#  `... and other chronic and ancillary findings as described above`)
_CROSSREF_TAIL_RE = re.compile(
    r"\s*[,;]?\s*(?:and\s+)?"
    r"(?:other\s+|additional\s+)?"
    r"(?:chronic\s+and\s+ancillary\s+)?"
    r"findings?(?:\s+and\s+details)?\s+as\s+(?:above|described)\s*\.?$")


def _ct_impression(notes):
    m = re.search(r"^\s*(?:IMPRESSION|CONCLUSION|ASSESSMENT)\s*:?\s*",
                  notes, re.M | re.I)
    if m is None:
        return None
    rest = notes[m.end():]
    cuts = [mm.start() for mm in _CT_TAIL_RE.finditer(rest)]
    if cuts:
        rest = rest[:min(cuts)]
    return rest


def _ct_cut_citation(sent):
    """The sentence without its Fleischner / ACR-White-Paper guideline."""
    m = _CT_GUIDE_CITE_RE.search(sent)
    if m is None:
        return sent
    cut = re.sub(r"(\s*(?:in keeping with|per|according to|as))+\s*$",
                 "", sent[:m.start()].rstrip(), flags=re.I)
    return re.sub(r"\s*(?:;|,)\s*$", "", cut)


def ct_findings(notes):
    impression = _ct_impression(notes)
    if impression is None:
        return [], False
    segs = []
    for raw in impression.splitlines():
        line = re.sub(r"^\s*\d+\.\s*", "", raw.strip())
        if not line:
            continue
        if _CT_NAME_LINE_RE.match(line):
            continue
        if _CT_HEADER_RE.match(line):
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
            if not sent:
                continue
            # the citation is cut before the skip checks: a finding's
            # sentence can carry the citation's journal line in the
            # same sentence (the guideline block trails it)
            sent = _ct_cut_citation(sent)
            if not sent or _CT_NAME_LINE_RE.match(sent) \
                    or _CT_SKIP_RE.search(sent):
                continue
            # the cross-reference tail pointing back at the findings
            # section is cut, the finding kept; a sentence of only
            # tail is dropped and does not count as usable
            sent = _CROSSREF_TAIL_RE.sub("", sent).strip()
            if not sent.rstrip("."):
                continue
            any_sent = True
            if _CT_NEG_PHRASE_RE.search(sent):
                continue
            if (re.match(r"^(?:no|non)[\s\-]", sent, re.I)
                    or re.match(r"^(?:otherwise\s+)?normal\b", sent, re.I)):
                if _CT_NEG_LIST_RE.search(sent) \
                        or not _CT_FINDING_RE.search(sent):
                    continue
            findings.append(sent.rstrip("."))
    return findings, any_sent


def ct_token(notes, label):
    findings, any_sent = ct_findings(notes)
    if not any_sent:
        return None
    if not findings:
        return f"CT {label} nl"
    return f"CT {label}: " + ". ".join(findings)
