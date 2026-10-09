"""Parsing of Encounter.note for the /encounter page.

Encounter.note is the raw SOAP envelope XML db.progress_notes() fetched
from the ECW physician's dashboard: besides UI-state elements, the
clinical content lives in <subItems> blocks (Subjective/Objective/
Assessment/Plan/Billing). Two envelope shapes are stored: the older one
holds a run of <item> entries per block, the newer one (2026 dashboards)
holds named content blocks instead (cc, hpi, ros, CurrentMeds,
PastHistory, Hospitalization, allergies, SurgicalHistory, FamilyHistory,
SocialHistory, examination, vitals2BR, assessment, treatment, FollowUp,
procedures, Immunization, Injection, preventive, labs, xrays,
ProcedureReport, ...).

parse_note() reduces either shape to (section_title, groups) for the
/encounter page. Each group is a (label, children) pair: label is the
group's heading (an item's itemName, a category's categoryName, the name
ECW renders for a block, or None) and children is the ordered list of
("t", text) lines and ("g", group) nested groups below it. The renderer
shows a group's label as an h4 (an h5, indented with its lines, when
nested) and the text lines as paragraphs. The nesting preserves the
envelope's grouping: the lines of a category (Tobacco Use, ...) stay
with it, and block-level lines after it (Social History Verified, ...)
are not rendered inside it. The UI-state elements and the
display-duplicate variants (*ValueAssessment, *ValueTrmt,
notesBRMedValue, StData/structDataValueHtml, rosNotes2, hpiNotes2,
PastHistoryData, ProcedureData, familyNotesHtml, itemNotesHtmHtml,
vitalGroupHtml, ...) are skipped.
"""
import html
import re
import xml.etree.ElementTree as ET


def _clean(text):
    """Normalized lines from a stored note value: <br> becomes a newline,
    the remaining HTML tags (<font>, <b>, <div>, ...) are stripped, entities
    are unescaped. [] when nothing is left."""
    if not text:
        return []
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _has_text(children):
    """Whether a children list holds any text line, nested groups included."""
    for n in children:
        if n[0] == "t":
            return True
        if n[0] == "g" and _has_text(n[1][1]):
            return True
    return False


def _detail_group(el):
    """Group (label, children) for one HpiDetail3/socialDetail detail
    (PHQ-9, Tobacco Use/Smoking, AUDIT-C, ...): label is the detail's
    item name, children one "question value" line per answered StData
    entry, or the detail's combined value lines when it holds no StData
    data. None when the detail carries no text."""
    label = " ".join((el.findtext("hpiName") or el.findtext("itemname")
                      or el.findtext("itemNameWithoutOption") or "").split()).rstrip(":")
    children = []
    for sd in el.findall("StData"):
        val = (sd.findtext("value") or "").strip()
        if not val:
            continue
        name = (sd.findtext("name") or "").strip()
        children.append(("t", f"{name} {val}".strip()))
    if not children:
        val = (el.findtext("notes") or el.findtext("value") or "").strip()
        children = [("t", ln) for ln in _clean(val)]
    if not children:
        return None
    return (label or None, children)


def _category_group(cat):
    """Group (label, children) for one note <category>: label is its
    categoryName (None when absent/empty), children the content-bearing
    children in document order — value lines (categoryValue, the
    medication lines in categoryNotesBR, the treatment notes in
    categoryNotesHtm), ROS answers as "symptom: answer", exam findings as
    "SYSTEM finding", HPI/social structured detail as the combined value
    (or the StData "question: answer" pairs), and nested <item> groups.
    None when the category carries no text."""
    children = []
    for ch in cat:
        if ch.tag in ("categoryValue", "categoryNotesBR", "categoryNotesHtm",
                      "hpiCatNotes"):
            new = _clean(ch.text)
            if ch.tag == "categoryNotesHtm" and new \
                    and new[0].startswith("Notes:"):
                # the stored value leads with a bare "Notes:" label
                first = new[0][len("Notes:"):].strip()
                new = ([first] if first else []) + new[1:]
            children += [("t", ln) for ln in new]
        elif ch.tag == "rosDetail":
            name = (ch.findtext("name") or "").strip()
            notes = (ch.findtext("notes") or "").strip()
            if name:
                children.append(("t", f"{name}: {notes}" if notes else name))
        elif ch.tag == "categoryInDetail":
            for det in ch.findall("cat_det"):
                sub = (det.findtext("categorySubName") or "").strip()
                notes = " ".join(_clean(det.findtext("examNotes") or ""))
                if sub or notes:
                    children.append(("t", " ".join(p for p in (sub, notes) if p)))
        elif ch.tag in ("HpiDetail3", "socialDetail"):
            g = _detail_group(ch)
            if g:
                children.append(("g", g))
        elif ch.tag == "item":
            g = _item_group(ch)
            if g:
                children.append(("g", g))
    if not _has_text(children):
        return None
    name = " ".join((cat.findtext("categoryName")
                     or cat.findtext("categoryname") or "").split()).rstrip(":")
    return (name or None, children)


def _item_group(item):
    """Group (label, children) for one note <item>: label is its itemName,
    children the content-bearing children in document order — itemValue /
    itemValueBR / familyNotes / vitalValue text lines, surgHxItemDetail
    reasons, each <category> group and nested <item> groups flattened.
    The envelope stores some content twice (e.g. familyNotes and its
    <br>-form sibling), so duplicate lines are dropped. When the item
    holds no combined value, its StData "question: answer" pairs are
    used instead. None when the item carries no display text."""
    label = " ".join(
        (item.findtext("itemName") or item.findtext("itemname") or "").split()
    ).rstrip(":")
    children, seen = [], set()

    def add(kind, text):
        if text and (kind, text) not in seen:
            seen.add((kind, text))
            children.append((kind, text))

    for ch in item:
        if ch.tag in ("itemValue", "itemValueBR", "familyNotes", "vitalValue"):
            for ln in _clean(ch.text):
                add("t", ln)
        elif ch.tag == "surgHxItemDetail":
            for ln in _clean(ch.findtext("reason") or ""):
                add("t", ln)
        elif ch.tag == "category":
            g = _category_group(ch)
            if g:
                children.append(("g", g))
        elif ch.tag == "item":
            g = _item_group(ch)
            if g:
                children.append(("g", g))
    if not _has_text(children):
        # no combined value in the item: fall back to its structured
        # StData detail, the "question: answer" pairs joined per line
        pairs = []
        for sd in item.findall("StData"):
            val = (sd.findtext("value") or "").strip()
            if not val:
                continue
            name = (sd.findtext("name") or "").strip()
            pairs.append(f"{name}: {val}" if name else val)
        if not pairs:
            return None
        children.append(("t", "; ".join(pairs)))
    return (label or None, children)


# Content-bearing text elements of the newer dashboard envelopes' named
# blocks: either a leaf whose own text is the content (a direct child of
# a <subItems> block, e.g. vitals2BR, FollowUp, notesBR) or nested inside
# a named block (e.g. the itemValue lines of cc / CurrentMeds).
_TEXT_TAGS = ("itemValue", "itemValueBR", "familyNotes", "vitalValue",
              "notesBR", "rx", "itemDetails", "allergiesVerified",
              "categoryNotesBR", "categoryNotesHtm", "FollowUp",
              "vitals2BR", "RPMNotes", "vitalGroupHtml")

# Block-level headings for the newer dashboard shape: unlike the older
# items (whose itemName supplies the heading), these blocks carry no label
# in the envelope, so the names ECW renders for them are supplied here.
_BLOCK_HEADINGS = {
    "cc": "Chief complaints",
    "hpi": "History of Present Illness",
    "CurrentMeds": "Current Medications",
    "PastHistory": "Past Medical History",
    "allergies": "Allergies",
    "SurgicalHistory": "Surgical History",
    "FamilyHistory": "Family History",
    "SocialHistory": "Social History",
    "ros": "Review of system",
    "Hospitalization": "Hospitalization / Major Diagnostic Procedures",
    "examination": "Examination",
    "vitals2BR": "Vitals",
    "treatment": "Treatment",
    "FollowUp": "Follow Up",
    "preventive": "Preventive",
    "procedures": "Procedures",
    "labs": "Labs",
    "xrays": "X-Rays",
    "ProcedureReport": "Procedure Reports",
    "RPMNotes": "Remote Monitoring",
}


def _text_lines(el):
    """Cleaned display lines of one content-bearing text element, the
    leading bare "Notes:" label of notesBR values dropped."""
    lines = _clean(el.text)
    if el.tag == "notesBR" and lines and lines[0].startswith("Notes:"):
        first = lines[0][len("Notes:"):].strip()
        lines = ([first] if first else []) + lines[1:]
    return lines


def _assessment_node(a):
    """Node for one <assessment> element: a bare diagnosis line when it
    holds plain text, or a group (its name label + its children in
    document order — rx lines, Test orders as "LAB: name", Xrayname
    orders as "IMAGING: name", and notes lines, leading "Notes:" label
    dropped) when it is a Plan-section treatment entry. None when it has
    nothing to show."""
    children = []
    for ch in a:
        if ch.tag == "rx":
            children += [("t", ln) for ln in _clean(ch.text)]
        elif ch.tag in ("Test", "Xrayname"):
            name = (ch.findtext("TestName") or "").strip()
            if name:
                prefix = "LAB: " if ch.tag == "Test" else "IMAGING: "
                children.append(("t", prefix + name))
        elif ch.tag == "notesBR":
            lines = _clean(ch.text)
            if lines and lines[0].startswith("Notes:"):
                first = lines[0][len("Notes:"):].strip()
                lines = ([first] if first else []) + lines[1:]
            children += [("t", ln) for ln in lines]
    if children:
        name = " ".join((a.findtext("name") or "").split()).rstrip(":")
        return ("g", (name or None, children))
    lines = _clean(a.text)
    if not lines:
        return None
    return ("t", "\n".join(lines))


def _block_group(block):
    """Group (label, children) for one named content block: a <subItems>
    child that is not an <item> entry (cc, hpi, ros, CurrentMeds,
    PastHistory, Hospitalization, allergies, SurgicalHistory,
    FamilyHistory, SocialHistory, examination, vitals2BR, treatment,
    FollowUp, procedures, Immunization, Injection, preventive, labs,
    xrays, ProcedureReport, ...). The content-bearing children are
    reduced as in _item_group/_category_group: text elements to lines,
    <category>/<item> to groups, <SubItems> blocks recursively,
    <assessment> via _assessment_node, and lab/xray/procedure details to
    their TestName lines. The group's label comes from its <itemName>
    child when present (the Immunization/Injection blocks), else from
    _BLOCK_HEADINGS. UI-state and display-duplicate children (rxData,
    PastHistoryData, ProcedureData, assessmentData/categoryValueAssessment,
    familyNotesHtml, itemNotesHtmHtml, structDataDisplay, ...) are
    skipped, and duplicate lines are dropped. A text element in
    _TEXT_TAGS used as a block is a leaf: its own text is the content.
    None when the block carries no display text."""
    children, seen = [], set()

    def add(kind, text):
        if text and (kind, text) not in seen:
            seen.add((kind, text))
            children.append((kind, text))

    if block.tag == "assessment":
        n = _assessment_node(block)
        if n is None:
            return None
        if n[0] == "g":
            return n[1]
        return (None, [n])
    if block.tag in _TEXT_TAGS:
        lines = _text_lines(block)
        if not lines:
            return None
        label = _BLOCK_HEADINGS.get(block.tag, "")
        return (label or None, [("t", ln) for ln in lines])

    for ch in block:
        if ch.tag in _TEXT_TAGS:
            for ln in _text_lines(ch):
                add("t", ln)
        elif ch.tag == "category":
            if block.tag == "CurrentMeds":
                # the Taking category is a structured duplicate of the
                # "Taking ..." itemValue lines shown in the render
                continue
            g = _category_group(ch)
            if g:
                children.append(("g", g))
        elif ch.tag == "item":
            g = _item_group(ch)
            if g:
                children.append(("g", g))
        elif ch.tag in ("SubItems", "additionalSubItems"):
            g = _block_group(ch)
            if g:
                children.append(("g", g))
        elif ch.tag == "treatment":
            for a in ch:
                if a.tag == "assessment":
                    n = _assessment_node(a)
                    if n is not None:
                        children.append(n)
        elif ch.tag == "assessment":
            n = _assessment_node(ch)
            if n is not None:
                children.append(n)
        elif ch.tag in ("labdetail", "xraydetail", "procedureDetail"):
            name = (ch.findtext("TestName") or "").strip()
            if name:
                add("t", name)
        # anything else is UI state or a display duplicate: skip
    if not _has_text(children):
        return None
    label = " ".join(
        (block.findtext("itemName") or block.findtext("itemname") or "").split()
    ).rstrip(":")
    if not label:
        label = _BLOCK_HEADINGS.get(block.tag, "")
    return (label or None, children)


def parse_note(note):
    """Parse an Encounter.note (the raw ECW physician-dashboard SOAP envelope
    stored by db.progress_notes()) into its clinical sections for the
    /encounter page: a list of (section_title, groups). Each group is a
    (label, children) pair, children being the ordered ("t", text) lines
    and ("g", group) nested groups of the section's items and named
    content blocks, from the envelope's <subItems> blocks. The UI-state
    elements and the display-duplicate fields are skipped. None when the
    XML can't be parsed (the caller then shows the raw note); [] when it
    parses but holds no clinical sections (nothing to show)."""
    xml = note
    if xml.lstrip().startswith("<?xml"):
        xml = xml.split("?>", 1)[1]
    try:
        ret = ET.fromstring(xml).find(".//return")
    except ET.ParseError:
        return None
    if ret is None:
        return None
    sections = []
    for sub in ret.findall("subItems"):
        title = " ".join((sub.findtext("subItemsName") or "").split()).rstrip(":")
        groups = []
        for ch in sub:
            if ch.tag == "subItemsName":
                continue
            g = _item_group(ch) if ch.tag == "item" else _block_group(ch)
            if g:
                groups.append(g)
        if groups:
            sections.append((title, groups))
    return sections
