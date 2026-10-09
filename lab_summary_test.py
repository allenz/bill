import json

from lab_summary import build_lab_summary


def result(*items):
    """JSON text for a lab result; items are (itemName, value, flag)
    triples, (itemName, value, flag, range) 4-tuples,
    (itemName, value, flag, range, paramNotes) 5-tuples, or
    (itemName, value, flag, range, paramNotes, units) 6-tuples in
    report order."""
    data = []
    for item in items:
        name, value, flag = item[0], item[1], item[2]
        range_ = item[3] if len(item) > 3 else ""
        notes = item[4] if len(item) > 4 else ""
        units = item[5] if len(item) > 5 else ""
        data.append({
            "itemName": name,
            "value": value,
            "units": units,
            "range": range_,
            "flag": flag,
            "paramNotes": notes,
        })
    return json.dumps(data)


def row(name, result_text=None, result_date="2026-11-07", date="2026-10-20"):
    """A lab row mapping as /patient feeds it (newest first)."""
    return {
        "name": name,
        "result": result_text,
        "result_date": result_date,
        "date": date,
    }


# ----------------------------------------------------------------------
# UA
# ----------------------------------------------------------------------

def ua_labcorp(**kw):
    return row(
        "UA, Routine",
        result(
            ("Specific Gravity", "1.018", ""),
            ("pH", "6.0", ""),
            ("Urine-Color", "Yellow", ""),
            ("Appearance", "Clear", ""),
            ("WBC Esterase", "Negative", ""),
            ("Protein", "Negative", ""),
            ("Glucose", "Negative", ""),
            ("Ketones", "Negative", ""),
            ("Occult Blood", "Negative", ""),
            ("Bilirubin", "Negative", ""),
            ("Urobilinogen,Semi-Qn", "0.2", ""),
            ("Nitrite, Urine", "Negative", ""),
            ("WBC", "0-5", ""),
            ("RBC", "None seen", ""),
            ("Crystals", "Absent", ""),
        ),
        **kw,
    )


def ua_quest(**kw):
    return row(
        "UA, urine routine",
        result(
            ("COLOR", "YELLOW", "N"),
            ("APPEARANCE", "CLEAR", "N"),
            ("BILIRUBIN", "NEGATIVE", "N"),
            ("KETONES", "NEGATIVE", "N"),
            ("SPECIFIC GRAVITY", "1.015", "N"),
            ("OCCULT BLOOD", "NEGATIVE", "N"),
            ("PH", "5.5", "N"),
            ("PROTEIN", "NEGATIVE", "N"),
            ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("WBC", "NONE SEEN", "N"),
            ("RBC", "NONE SEEN", "N"),
            ("GLUCOSE", "NEGATIVE", "N"),
        ),
        **kw,
    )


def ua_22457():
    """MRN 22457's full Quest UA layout: pH at/below the lower limit
    (`< OR = 5.0`), trace protein, moderate calcium oxalate crystals,
    plus the flagged squamous epithelial cells (a contamination
    artifact) and bacteria few that are ignored."""
    return row(
        "UA, urine routine",
        result(
            ("COLOR", "YELLOW", "N"),
            ("APPEARANCE", "CLEAR", "N"),
            ("BILIRUBIN", "NEGATIVE", "N"),
            ("KETONES", "NEGATIVE", "N"),
            ("SPECIFIC GRAVITY", "1.023", "N", "1.001-1.035"),
            ("OCCULT BLOOD", "NEGATIVE", "N"),
            ("PH", "< OR = 5.0", "A", "5.0-8.0"),
            ("PROTEIN", "TRACE", "A"),
            ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("WBC", "0-5", "N", "< OR = 5"),
            ("RBC", "0-2", "N", "< OR = 2"),
            ("SQUAMOUS EPITHELIAL CELLS", "6-10", "A", "< OR = 5"),
            ("BACTERIA", "FEW", "A", "NONE SEEN"),
            ("CALCIUM OXALATE CRYSTALS", "MODERATE", "A", "NONE OR FEW"),
            ("HYALINE CAST", "NONE SEEN", "N"),
            ("GLUCOSE", "NEGATIVE", "N"),
        ),
    )


def ua_complete(**kw):
    """LabCorp's `Urinalysis, Complete` layout: the `UA, Routine`
    dipstick plus the manual-microscopy block (the `Microscopic
    Examination` section header, the `0-x`-style count ranges, the
    other count items and the `NOSEE` absent texts)."""
    return row(
        "Urinalysis, Complete",
        result(
            ("Specific Gravity", "1.022", ""),
            ("pH", "5.5", ""),
            ("Urine-Color", "Yellow", ""),
            ("Appearance", "Clear", ""),
            ("WBC Esterase", "Negative", ""),
            ("Protein", "Negative", ""),
            ("Glucose", "Negative", ""),
            ("Ketones", "Negative", ""),
            ("Occult Blood", "Negative", ""),
            ("Bilirubin", "Negative", ""),
            ("Urobilinogen,Semi-Qn", "0.2", ""),
            ("Nitrite, Urine", "Negative", ""),
            ("Microscopic Examination", "", "",
             "", "Microscopic was indicated and was performed."),
            ("Microscopic Examination", "See below:", ""),
            ("WBC", "0-5", "", "0 -  5"),
            ("RBC", "0-2", "", "0 -  2"),
            ("Epithelial Cells (non renal)", "0-10", "", "0 - 10"),
            ("Epithelial Cells (renal)", "0-10", "", "None seen"),
            ("Casts", "None seen", ""),
            ("Crystals", "NOSEE", "", "None seen"),
            ("Mucus Threads", "NOSEE", ""),
            ("Bacteria", "None seen", "", "None seen/Few"),
            ("Yeast", "NOSEE", "", "None seen"),
        ),
        **kw,
    )


def test_ua():
    # normal -> UA nl (both vendors' layouts)
    assert build_lab_summary([ua_labcorp()]) == "11/2026- UA nl"
    assert build_lab_summary([ua_quest()]) == "11/2026- UA nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("ua, routine", ua_labcorp()["result"])
    ]) == "11/2026- UA nl"

    # ignored (item, value) pairs: neither normal nor reported
    ua = ua_quest()
    data = json.loads(ua["result"])
    for item in data:
        if item["itemName"] == "KETONES":
            item.update(value="2+", flag="A")
        if item["itemName"] == "OCCULT BLOOD":
            item.update(value="TRACE", flag="A")
    assert build_lab_summary(
        [row("UA, urine routine", json.dumps(data))]) == "11/2026- UA nl"

    ua = ua_labcorp()
    data = json.loads(ua["result"])
    for item in data:
        if item["itemName"] == "WBC Esterase":
            item.update(value="Trace", flag="A")
        if item["itemName"] == "Ketones":
            item.update(value="Trace", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == "11/2026- UA nl"

    # Quest's name for WBC esterase is ignored too
    ua = ua_quest()
    data = json.loads(ua["result"])
    for item in data:
        if item["itemName"] == "LEUKOCYTE ESTERASE":
            item.update(value="TRACE", flag="A")
    assert build_lab_summary(
        [row("UA, urine routine", json.dumps(data))]) == "11/2026- UA nl"

    # Crystals = Present (the only abnormal) -> UA crystals+
    ua = ua_labcorp()
    data = json.loads(ua["result"])
    for item in data:
        if item["itemName"] == "Crystals":
            item.update(value="Present", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == "11/2026- UA crystals+"
    # ... case-insensitively
    for item in data:
        if item["itemName"] == "Crystals":
            item["value"] = "present"
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == "11/2026- UA crystals+"

    # any other abnormal -> UA {abnormal string}, lower-case `{name} {value}`
    data = json.loads(ua_labcorp()["result"])
    for item in data:
        if item["itemName"] == "Protein":
            item.update(value="30", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == "11/2026- UA protein 30"

    # multiple other abnormalities, in report order
    data = json.loads(ua_labcorp()["result"])
    for item in data:
        if item["itemName"] == "Protein":
            item.update(value="30", flag="A")
        if item["itemName"] == "Glucose":
            item.update(value="Positive", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == \
        "11/2026- UA protein 30, glucose positive"

    # a trace value gains a +
    data = json.loads(ua_labcorp()["result"])
    for item in data:
        if item["itemName"] == "Protein":
            item.update(value="Trace", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == "11/2026- UA protein trace+"

    # crystals present plus other abnormal: crystals join the string
    data = json.loads(ua_labcorp()["result"])
    for item in data:
        if item["itemName"] == "Protein":
            item.update(value="30", flag="A")
        if item["itemName"] == "Crystals":
            item.update(value="Present", flag="A")
    assert build_lab_summary(
        [row("UA, Routine", json.dumps(data))]) == \
        "11/2026- UA protein 30, crystals+"

    # 22457's UA: pH `< OR = 5.0` -> pH<5, protein trace -> protein
    # trace+, the named crystal item -> crystals+; the squamous
    # epithelial cells and bacteria few are ignored
    assert build_lab_summary([ua_22457()]) == \
        "11/2026- UA pH<5, protein trace+, crystals+"

    # a numeric pH renders with its value
    data = json.loads(ua_quest()["result"])
    for item in data:
        if item["itemName"] == "PH":
            item.update(value="4.5", flag="L")
    assert build_lab_summary(
        [row("UA, urine routine", json.dumps(data))]) == "11/2026- UA pH 4.5"

    # the squamous cells are ignored even when bacteria are not
    data = json.loads(ua_22457()["result"])
    for item in data:
        if item["itemName"] == "PH":
            item.update(value="6.0", flag="N")
        if item["itemName"] == "PROTEIN":
            item.update(value="NEGATIVE", flag="N")
        if item["itemName"] == "CALCIUM OXALATE CRYSTALS":
            item.update(value="NONE SEEN", flag="N")
    assert build_lab_summary(
        [row("UA, urine routine", json.dumps(data))]) == \
        "11/2026- UA nl"

    # the Quest `urinalysis reflex` dipstick panel: same item
    # handling; all-normal -> UA nl
    assert build_lab_summary([
        row("urinalysis reflex", result(
            ("COLOR", "YELLOW", "N"), ("APPEARANCE", "CLEAR", "N"),
            ("BILIRUBIN", "NEGATIVE", "N"), ("KETONES", "NEGATIVE", "N"),
            ("SPECIFIC GRAVITY", "1.013", "N"),
            ("OCCULT BLOOD", "NEGATIVE", "N"), ("PH", "7.5", "N"),
            ("PROTEIN", "NEGATIVE", "N"), ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("GLUCOSE", "NEGATIVE", "N")))
    ]) == "11/2026- UA nl"
    # an abnormal dipstick item is reported (trace ketones are ignored)
    assert build_lab_summary([
        row("URINALYSIS REFLEX", result(
            ("COLOR", "YELLOW", "N"), ("APPEARANCE", "CLOUDY", "A"),
            ("BILIRUBIN", "NEGATIVE", "N"), ("KETONES", "TRACE", "A"),
            ("SPECIFIC GRAVITY", "1.013", "N"),
            ("OCCULT BLOOD", "NEGATIVE", "N"), ("PH", "7.5", "N"),
            ("PROTEIN", "NEGATIVE", "N"), ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("GLUCOSE", "NEGATIVE", "N")))
    ]) == "11/2026- UA appearance cloudy"

    # LabCorp's `Urinalysis, Complete`: the dipstick plus the
    # manual-microscopy block; the `Microscopic Examination` section
    # header, the `0-x` count ranges and the `NOSEE` texts are not
    # findings -> UA nl
    assert build_lab_summary([ua_complete()]) == "11/2026- UA nl"
    # ... and name matching is case-insensitive
    assert build_lab_summary([
        row("urinalysis, complete", ua_complete()["result"])
    ]) == "11/2026- UA nl"
    # LabCorp flags its `Epithelial Cells (renal)` item A on the
    # normal `0-10` value; a count range starting at 0 is not a
    # finding, so it is not reported
    data = json.loads(ua_complete()["result"])
    for item in data:
        if item["itemName"] == "Epithelial Cells (renal)":
            item["flag"] = "A"
    assert build_lab_summary(
        [row("Urinalysis, Complete", json.dumps(data))]) == "11/2026- UA nl"
    # a flagged `NOSEE` crystals item is a negative, not crystals+
    data = json.loads(ua_complete()["result"])
    for item in data:
        if item["itemName"] == "Crystals":
            item["flag"] = "A"
    assert build_lab_summary(
        [row("Urinalysis, Complete", json.dumps(data))]) == "11/2026- UA nl"
    # the `Microscopic Examination` section header is not reported
    # even when flagged
    data = json.loads(ua_complete()["result"])
    for item in data:
        if item["itemName"] == "Microscopic Examination":
            item["flag"] = "A"
    assert build_lab_summary(
        [row("Urinalysis, Complete", json.dumps(data))]) == "11/2026- UA nl"
    # a genuine count finding (a range not starting at 0) is reported
    data = json.loads(ua_complete()["result"])
    for item in data:
        if item["itemName"] == "WBC":
            item.update(value="11-30", flag="A")
    assert build_lab_summary(
        [row("Urinalysis, Complete", json.dumps(data))]) == \
        "11/2026- UA wbc 11-30"
    # ... as is a `>10`-style range
    data = json.loads(ua_complete()["result"])
    for item in data:
        if item["itemName"] == "Epithelial Cells (non renal)":
            item.update(value=">10", flag="A")
    assert build_lab_summary(
        [row("Urinalysis, Complete", json.dumps(data))]) == \
        "11/2026- UA epithelial cells (non renal) >10"


# ----------------------------------------------------------------------
# UCX (urine culture)
# ----------------------------------------------------------------------

def ucx_labcorp(value="No growth", flag="", result_date="2026-11-07"):
    return row(
        "Culture Urine, Routine",
        result(
            ("Urine Culture, Routine", "Final report", ""),
            ("Result 1", value, flag),
            ("Antimicrobial Susceptibility", "", ""),
        ),
        result_date=result_date,
    )


def ucx_inhouse(value="", flag=""):
    return row(
        "CULTURE, URINE, ROUTINE",
        result(("CULTURE, URINE, ROUTINE", value, flag)),
    )


def ucx_quest(value="", flag="", result_date="2026-11-07"):
    """Quest's `urine reflex to culture` layout: the UA items plus the
    `REFLEXIVE URINE CULTURE` item, which carries no value until the
    reflex fires and a culture result is in."""
    return row(
        "urine reflex to culture",
        result(
            ("REFLEXIVE URINE CULTURE", value, flag),
            ("COLOR", "YELLOW", "N"),
            ("APPEARANCE", "CLEAR", "N"),
            ("BILIRUBIN", "NEGATIVE", "N"),
            ("KETONES", "NEGATIVE", "N"),
            ("SPECIFIC GRAVITY", "1.024", "N", "1.001-1.035"),
            ("OCCULT BLOOD", "NEGATIVE", "N"),
            ("PH", "6.5", "N", "5.0-8.0"),
            ("PROTEIN", "NEGATIVE", "N"),
            ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("WBC", "NONE SEEN", "N", "< OR = 5"),
            ("RBC", "0-2", "N", "< OR = 2"),
            ("SQUAMOUS EPITHELIAL CELLS", "NONE SEEN", "N", "< OR = 5"),
            ("BACTERIA", "NONE SEEN", "N", "NONE SEEN"),
            ("HYALINE CAST", "NONE SEEN", "N", "NONE SEEN"),
            ("GLUCOSE", "NEGATIVE", "N"),
        ),
        result_date=result_date,
    )


def ucx_ua_reflex():
    """A LabCorp `UA/M w/rflx Culture, Routine` order whose reflex
    never fired (an order layout in the database): the UA items only,
    no culture item."""
    return row(
        "UA/M w/rflx Culture, Routine",
        result(
            ("Specific Gravity", "1.023", ""),
            ("pH", "5.5", ""),
            ("Urine-Color", "Yellow", ""),
            ("Appearance", "Clear", ""),
            ("WBC Esterase", "Negative", ""),
            ("Protein", "Negative", ""),
            ("Glucose", "Negative", ""),
            ("Ketones", "Negative", ""),
            ("Occult Blood", "Negative", ""),
            ("Bilirubin", "Negative", ""),
            ("Urobilinogen,Semi-Qn", "0.2", ""),
            ("Nitrite, Urine", "Negative", ""),
            ("WBC", "None seen", "", "0 -  5"),
            ("RBC", "0-2", "", "0 -  2"),
            ("Epithelial Cells (non renal)", "None seen", ""),
            ("Casts", "None seen", ""),
            ("Bacteria", "None seen", ""),
        ),
    )


def test_ucx():
    # negative (all three order layouts) -> Ucx neg
    assert build_lab_summary([ucx_labcorp()]) == "11/2026- Ucx neg"
    assert build_lab_summary([ucx_quest("No growth")]) == \
        "11/2026- Ucx neg"
    assert build_lab_summary([ucx_inhouse("No growth")]) == \
        "11/2026- Ucx neg"
    # positive -> the organism text as reported on the report (the
    # yellow notes' `Ucx {organism}` shorthand)
    assert build_lab_summary(
        [ucx_labcorp("Proteus mirabilis", "A")]
    ) == "11/2026- Ucx Proteus mirabilis"
    assert build_lab_summary(
        [ucx_quest("Staphylococcus saprophyticus")]
    ) == "11/2026- Ucx Staphylococcus saprophyticus"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("culture, urine, routine",
            ucx_inhouse("No growth")["result"])
    ]) == "11/2026- Ucx neg"
    # pending: the in-house empty value and Quest's reflex that never
    # fired both produce nothing
    assert build_lab_summary([ucx_inhouse()]) == ""
    assert build_lab_summary([ucx_quest()]) == ""
    # a UA-with-reflex order whose reflex never fired carries no
    # culture item -> nothing
    assert build_lab_summary([ucx_ua_reflex()]) == ""
    # the LabCorp header item (`Final report`) is not the result item:
    # a report carrying only it produces nothing
    assert build_lab_summary([
        row("Culture Urine, Routine",
            result(("Urine Culture, Routine", "Final report", "")))
    ]) == ""
    # the newest row decides: a newer pending culture row hides the
    # older positive result
    older = ucx_labcorp("Proteus mirabilis", "A", result_date="2026-09-14")
    assert build_lab_summary([ucx_inhouse(), older]) == ""
    # Ucx renders right after the UA token
    assert build_lab_summary([ua_labcorp(), ucx_labcorp()]) == \
        "11/2026- UA nl, Ucx neg"


# ----------------------------------------------------------------------
# HCG
# ----------------------------------------------------------------------

def hcg_serum(value="5072", flag="H", **kw):
    """Quest's `HCG, TOTAL, QN` serum-quantitative layout: the single
    item is named after the order and carries no reference range (the
    nonpregnant <5 / postmenopausal <10 range sits in its
    paramNotes)."""
    return row(
        "HCG, TOTAL, QN",
        result(("HCG, TOTAL, QN", value, flag, "",
                "Reference Range\nNonpregnant or premenopausal    <5\n"
                "Postmenopausal                 <10",
                "mIU/mL")),
        **kw,
    )


def test_hcg():
    # urine qualitative test (the in-house layout's NEGATIVE value,
    # e.g. 372463)
    assert build_lab_summary([
        row("HCG, QL, URINE",
            result(("HCG, QL, URINE", "NEGATIVE", "N", "NEGATIVE")))
    ]) == "11/2026- HCG neg"
    # a positive urine test is its own token
    assert build_lab_summary([
        row("HCG, QL, URINE",
            result(("HCG, QL, URINE", "POSITIVE", "A", "NEGATIVE")))
    ]) == "11/2026- HCG+"
    # serum quantitative: a flagged (above-cutoff) value is positive
    # (367852's 5072)
    assert build_lab_summary([hcg_serum()]) == "11/2026- HCG+"
    # a below-cutoff serum value is negative: the range sits in the
    # paramNotes, so the flag decides -- an unflagged numeric or
    # <5-style value is below it
    assert build_lab_summary([hcg_serum("2.3", "N")]) == "11/2026- HCG neg"
    assert build_lab_summary([hcg_serum("<5", "N")]) == "11/2026- HCG neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hcg, total, qn", hcg_serum("2.3", "N")["result"])
    ]) == "11/2026- HCG neg"
    # a pending / empty value produces nothing
    assert build_lab_summary([hcg_serum("", "N")]) == ""
    # HCG renders right after the UA / Ucx tokens, before the TSH
    assert build_lab_summary([
        ua_labcorp(),
        hcg_serum(),
        row("TSH", result(("TSH", "2.1", ""))),
    ]) == "11/2026- UA nl, HCG+, TSH 2.1"


# ----------------------------------------------------------------------
# CBC
# ----------------------------------------------------------------------

def cbc_quest(**kw):
    """MRN 22457's full Quest CBC layout: the RBC is high (5.43 in
    3.80-5.10), and the Hct (now a reported item) and the RDW (which
    is ignored) are flagged as well."""
    return row(
        "CBC (INCLUDES DIFF/PLT)",
        result(
            ("WHITE BLOOD CELL COUNT", "9.9", "N", "3.8-10.8"),
            ("RED BLOOD CELL COUNT", "5.43", "H", "3.80-5.10"),
            ("HEMOGLOBIN", "15.4", "N", "11.7-15.5"),
            ("HEMATOCRIT", "46.8", "H", "35.9-46.0"),
            ("MCV", "86.2", "N", "81.4-101.7"),
            ("MCH", "28.4", "N", "27.0-33.0"),
            ("MCHC", "32.9", "N", "31.6-35.4"),
            ("RDW", "15.1", "H", "11.0-15.0"),
            ("PLATELET COUNT", "348", "N", "140-400"),
        ),
        **kw,
    )


def test_cbc():
    # abnormal RBC (22457's 5.43 in 3.80-5.10) -> RBC {val}(upper
    # limit), the value rounded to one decimal; the fixture's high Hct
    # (46.8 in 35.9-46.0) adds its token after the CBC items, the
    # high RDW is ignored
    assert build_lab_summary([cbc_quest()]) == \
        "11/2026- RBC 5.4(5.1), Hematocrit 46.8(46)"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("cbc (includes diff/plt)", cbc_quest()["result"])]) == \
        "11/2026- RBC 5.4(5.1), Hematocrit 46.8(46)"
    # LabCorp's layout names the item RBC
    assert build_lab_summary([
        row("CBC With Differential/Platelet", result(
            ("WBC", "7.3", "", "3.4-10.8"),
            ("RBC", "5.4", "H", "3.77-5.28"),
            ("Hemoglobin", "13.5", "", "11.1-15.9"),
            ("Platelets", "367", "", "150-450")))
    ]) == "11/2026- RBC 5.4(5.28)"
    # the LabCorp `CBC/Diff Ambiguous Default` order name (the same
    # LabCorp layout; 20739-style normal RBC produces nothing)
    assert build_lab_summary([
        row("CBC/Diff Ambiguous Default", result(
            ("RBC", "4.00", "", "3.77-5.28"),
            ("Hemoglobin", "12.4", "", "11.1-15.9"),
            ("Hematocrit", "37.6", "", "34.0-46.6"),
            ("MCV", "94", "", "79-97"),
            ("Platelets", "225", "", "150-450"),
            ("WBC", "4.6", "", "3.4-10.8")))
    ]) == ""
    assert build_lab_summary([
        row("CBC/DIFF AMBIGUOUS DEFAULT", result(
            ("RBC", "5.9", "H", "3.77-5.28"),
            ("Hemoglobin", "12.4", "", "11.1-15.9")))
    ]) == "11/2026- RBC 5.9(5.28)"
    # abnormal low -> lower limit
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] == "RED BLOOD CELL COUNT":
            item.update(value="2.94", flag="L")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- RBC 2.9(3.8), Hematocrit 46.8(46)"
    # abnormal without a parsable range -> plain value
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] == "RED BLOOD CELL COUNT":
            item.update(value="5.43", flag="H", range="")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- RBC 5.4, Hematocrit 46.8(46)"
    # an unparseable value is written out raw (the bound still comes
    # from the range)
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] == "RED BLOOD CELL COUNT":
            item.update(value="pending", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- RBC pending(5.1), Hematocrit 46.8(46)"
    # Quest's multi-letter `HH` flag reads its bound from the last
    # letter (20545's actual row: RBC 7.13 `HH` in 4.14-5.80)
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("HEMATOCRIT", "RDW"):
            item.update(flag="N")
        if item["itemName"] == "RED BLOOD CELL COUNT":
            item.update(value="7.13", flag="HH", range="4.14-5.80")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- RBC 7.1(5.8)"
    # and `LL` the lower limit (17822's actual row was an `LL`
    # absolute-neutrophil count, not a reported item; a WBC here)
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "WHITE BLOOD CELL COUNT":
            item.update(value="0.9", flag="LL")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- WBC 0.9(3.8)"
    # a normal RBC produces nothing (the normal MCV does too)
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == ""

    # MCV: low (20545's actual LabCorp row: MCV 70 in 79-97 alongside
    # the high RBC 6.85 in 4.14-5.80; the MCH / MCHC / RDW items are
    # not part of the summary) -> MCV {val}(lower limit), like the
    # yellow sticky note's `RBC 6.9(5.8)/MCV 70(79)`
    assert build_lab_summary([
        row("CBC With Differential/Platelet",
            result_date="2026-10-13", date="2026-10-12",
            result_text=result(
                ("WBC", "5.4", "", "3.4-10.8"),
                ("RBC", "6.85", "H", "4.14-5.80"),
                ("Hemoglobin", "14.6", "", "13.0-17.7"),
                ("Hematocrit", "47.7", "", "37.5-51.0"),
                ("MCV", "70", "L", "79-97"),
                ("MCH", "21.3", "L", "26.6-33.0"),
                ("MCHC", "30.6", "L", "31.5-35.7"),
                ("RDW", "16.2", "H", "11.6-15.4"),
                ("Platelets", "237", "", "150-450"),
            ))
    ]) == "10/2026- RBC 6.9(5.8), MCV 70(79)"
    # MCV high -> MCV {val}(upper limit), either vendor's layout
    assert build_lab_summary([
        row("CBC With Differential/Platelet", result(
            ("RBC", "4.9", "", "4.14-5.80"),
            ("MCV", "101", "H", "79-97")))
    ]) == "11/2026- MCV 101(97)"
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] == "MCV":
            item.update(value="105", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- RBC 5.4(5.1), MCV 105(102), Hematocrit 46.8(46)"
    # a high MCV alone (normal RBC) -> the MCV token on its own
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "MCV":
            item.update(value="105", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- MCV 105(102)"
    # the value and the bound are each rendered as integers
    # (12801's actual row: MCV 63.7 in 81.4-101.7; the yellow note
    # writes `MCV 64(81)`)
    assert build_lab_summary([row("CBC (INCLUDES DIFF/PLT)", result(
        ("MCV", "63.7", "L", "81.4-101.7"))
    )]) == "11/2026- MCV 64(81)"
    # an integer value stays (101.0 -> MCV 101)
    assert build_lab_summary([
        row("CBC With Differential/Platelet", result(
            ("MCV", "101.0", "H", "79-97")))
    ]) == "11/2026- MCV 101(97)"
    # abnormal without a parsable range -> plain value
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "MCV":
            item.update(value="105", flag="H", range="")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- MCV 105"
    # an unparseable value is written out raw (the bound still comes
    # from the range)
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "MCV":
            item.update(value="pending", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- MCV pending(102)"

    # WBC / Hb / Plt / Hct: one token per abnormal item, in that
    # order, after the MCV token (the yellow notes chain these with
    # slashes, e.g. 12575's `WBC 3.2(4)/RBC 3.8(4.4)/Hb 13.2(13.5)/
    # MCV 107/Plt 124(150)`, but the summary keeps one token per
    # item); WBC and Hb to one decimal like RBC, Plt and Hct with
    # trailing zeros stripped
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "WHITE BLOOD CELL COUNT":
            item.update(value="12.1", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- WBC 12.1(10.8)"
    # abnormal low -> lower limit (12575's WBC 3.2(4))
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "WHITE BLOOD CELL COUNT":
            item.update(value="3.2", flag="L")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- WBC 3.2(3.8)"
    # abnormal Hb -> Hb {val}(lower limit) (12801's Hb 11.3(11.7))
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "HEMOGLOBIN":
            item.update(value="11.3", flag="L")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- Hb 11.3(11.7)"
    # abnormal Plt -> Plt {val}(lower limit) (12575's Plt 124(150))
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "PLATELET COUNT":
            item.update(value="124", flag="L")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- Plt 124(140)"
    # an abnormal item without a parsable range has no parentheses
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "WHITE BLOOD CELL COUNT":
            item.update(value="12.1", flag="H", range="")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == \
        "11/2026- WBC 12.1"
    # an abnormal item with an empty value produces nothing
    data = json.loads(cbc_quest()["result"])
    for item in data:
        if item["itemName"] in ("RED BLOOD CELL COUNT", "HEMATOCRIT",
                                "RDW"):
            item.update(flag="N")
        if item["itemName"] == "WHITE BLOOD CELL COUNT":
            item.update(value="", flag="H")
    assert build_lab_summary(
        [row("CBC (INCLUDES DIFF/PLT)", json.dumps(data))]) == ""
    # the normal WBC / Hb / Plt of the fixture produce nothing
    # (covered by the RBC-only assertions above); LabCorp's layout
    # names the items WBC / Hemoglobin / Platelets / Hematocrit
    assert build_lab_summary([
        row("CBC With Differential/Platelet", result(
            ("WBC", "3.9", "L", "3.4-10.8"),
            ("RBC", "5.0", "", "4.14-5.80"),
            ("Hemoglobin", "12.0", "L", "13.0-17.7"),
            ("Hematocrit", "37.0", "L", "37.5-51.0"),
            ("MCV", "95", "", "79-97"),
            ("Platelets", "124", "L", "150-450")))
    ]) == ("11/2026- WBC 3.9(3.4), Hb 12.0(13), Plt 124(150), "
           "Hematocrit 37(37.5)")
    # the yellow notes' full chain: a LabCorp CBC with WBC / RBC / Hb
    # / MCV / Plt all abnormal (12575's 9/2026 review) plus a CMP
    # whose only abnormal item is the total bilirubin -> one token per
    # item, RBC / MCV first, then WBC / Hb / Plt, then the panel item
    assert build_lab_summary([
        row("CBC With Differential/Platelet", result(
            ("WBC", "3.2", "L", "3.4-10.8"),
            ("RBC", "3.8", "L", "4.14-5.80"),
            ("Hemoglobin", "13.2", "L", "13.5-17.7"),
            ("Hematocrit", "36.0", "", "37.5-51.0"),
            ("MCV", "107", "H", "79-97"),
            ("Platelets", "124", "L", "150-450")),
            result_date="2026-09-15"),
        row("CMP", result(
            ("Glucose, Serum", "93", "", "70-99"),
            ("BUN", "15", "", "6-20"),
            ("Creatinine", "0.9", "", "0.5-1.2"),
            ("eGFR", "88", "", "> OR = 60"),
            ("Albumin, Serum", "4.5", "", "3.4-5.4"),
            ("Bilirubin, Total", "1.5", "H", "0.0-1.2"),
            ("Alkaline Phosphatase, S", "70", "", "47-123"),
            ("AST (SGOT)", "25", "", "0-40"),
            ("ALT (SGPT)", "30", "", "0-44")),
            result_date="2026-09-15"),
    ]) == ("09/2026- RBC 3.8(4.14), MCV 107(97), WBC 3.2(3.4), "
           "Hb 13.2(13.5), Plt 124(150), bilirubin 1.5(1.2)")


# ----------------------------------------------------------------------
# Plt est
# ----------------------------------------------------------------------

def plt_est(value="DECREASED", flag="A", **kw):
    """The in-house platelet-estimation order: one qualitative item
    named after the order (`DECREASED` is the abnormal value, the
    reference `ADEQUATE`)."""
    return row(
        "PLATELET ESTIMATION",
        result(("PLATELET ESTIMATION", value, flag, "ADEQUATE")),
        **kw,
    )


def cbc_with_plt(value, flag, **kw):
    """A minimal LabCorp CBC row with the given Platelets item (the
    other items normal)."""
    return row(
        "CBC With Differential/Platelet",
        result(
            ("WBC", "4.6", "", "3.4-10.8"),
            ("RBC", "4.00", "", "3.77-5.28"),
            ("Hemoglobin", "12.4", "", "11.1-15.9"),
            ("Hematocrit", "37.6", "", "34.0-46.6"),
            ("MCV", "94", "", "79-97"),
            ("Platelets", value, flag, "150-450"),
        ),
        **kw,
    )


def test_plt_est():
    # abnormal estimate alone -> plt est decreased (14029's rows)
    assert build_lab_summary([plt_est()]) == "11/2026- plt est decreased"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("platelet estimation", plt_est()["result"])]) == \
        "11/2026- plt est decreased"
    # an unflagged DECREASED is reported too
    assert build_lab_summary([plt_est(flag="")]) == \
        "11/2026- plt est decreased"
    # a flagged value is written out as reported, lower-cased
    assert build_lab_summary(
        [plt_est(value="VERY DECREASED", flag="A")]) == \
        "11/2026- plt est very decreased"
    # normal (ADEQUATE) and pending (empty value) produce nothing
    assert build_lab_summary([plt_est(value="ADEQUATE", flag="N")]) == ""
    assert build_lab_summary([plt_est(value="", flag="")]) == ""
    # suppressed when the newest CBC already reported an abnormal Plt
    # (the measured count supersedes the estimate; 14029's sticky
    # writes only `Plt 50(140)`)
    assert build_lab_summary([
        plt_est(),
        cbc_with_plt("50", "L"),
    ]) == "11/2026- Plt 50(150)"
    # the row order does not matter: the newest row per category does
    assert build_lab_summary([
        cbc_with_plt("50", "L"),
        plt_est(),
    ]) == "11/2026- Plt 50(150)"
    # a CBC whose Plt is normal does not suppress the estimate
    assert build_lab_summary([
        plt_est(),
        cbc_with_plt("250", "N"),
    ]) == "11/2026- plt est decreased"
    # the newest CBC decides: a newer normal-Plt CBC lifts the
    # suppression even though the older CBC's Plt was flagged
    assert build_lab_summary([
        cbc_with_plt("250", ""),
        plt_est(),
        cbc_with_plt("50", "L"),
    ]) == "11/2026- plt est decreased"
    # a CBC whose Plt is flagged but empty yields no Plt token, so the
    # estimate is not suppressed
    assert build_lab_summary([
        plt_est(),
        cbc_with_plt("", "H"),
    ]) == "11/2026- plt est decreased"


# ----------------------------------------------------------------------
# TSH
# ----------------------------------------------------------------------

def test_tsh():
    # always emitted, normal or abnormal; {val:.1f}
    assert build_lab_summary([
        row("TSH W/REFLEX TO FT4", result(("TSH W/REFLEX TO FT4", "2.79", "N")))
    ]) == "11/2026- TSH 2.8"
    assert build_lab_summary([
        row("TSH reflex to T4F", result(("TSH", "2.460", "")))
    ]) == "11/2026- TSH 2.5"
    assert build_lab_summary([
        row("TSH reflex to T4F", result(("TSH", "9.5", "H")))
    ]) == "11/2026- TSH 9.5"
    # TSH+FREE T4 (Quest layout carrying a T4, FREE item): a normal T4
    # appends /T4 nl (17988's 0.78 / 1.4)
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "0.78", "N"),
                                  ("T4, FREE", "1.4", "N")))
    ]) == "11/2026- TSH 0.8/T4 nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("tsh+free t4", result(("TSH", "0.78", "N"),
                                  ("T4, FREE", "1.4", "N")))
    ]) == "11/2026- TSH 0.8/T4 nl"
    # abnormal T4 -> /T4 {val}
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "0.30", "L"),
                                  ("T4, FREE", "1.9", "H")))
    ]) == "11/2026- TSH 0.3/T4 1.9"
    # abnormal TSH with a normal T4 (subclinical) still shows /T4 nl
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "7.58", "H"),
                                  ("T4, FREE", "1.1", "N")))
    ]) == "11/2026- TSH 7.6/T4 nl"
    # unparseable value is written out raw
    assert build_lab_summary([
        row("TSH W/REFLEX TO FT4", result(("TSH W/REFLEX TO FT4", "pending", "")))
    ]) == "11/2026- TSH pending"
    # the `TSH rfx on abnormal to free T4` order (in-house / LabCorp): the reflexed
    # item is `T4,Free (Direct)` (20739-style 6.03 with a normal T4)
    assert build_lab_summary([
        row("TSH rfx on abnormal to free T4",
            result(("TSH", "6.030", "H"),
                   ("T4,Free (Direct)", "1.04", "", "0.82-1.77")))
    ]) == "11/2026- TSH 6.0/T4 nl"
    assert build_lab_summary([
        row("tsh rfx on abnormal to free t4", result(("TSH", "2.060", "")))
    ]) == "11/2026- TSH 2.1"
    # the standalone `TSH` orders (both vendors' single `TSH` item,
    # with or without a reference range): the value is emitted like
    # the reflex layouts
    assert build_lab_summary([
        row("TSH", result(("TSH", "2.1", "")))
    ]) == "11/2026- TSH 2.1"
    assert build_lab_summary([
        row("TSH", result(("TSH", "3.630", "", "0.450-4.500")))
    ]) == "11/2026- TSH 3.6"
    # LabCorp's thyroid cascade profile (a single `TSH` item plus an
    # interpretation note): 22473's 1.350 renders TSH 1.4, like the
    # yellow notes
    assert build_lab_summary([
        row("Thyroid Cascade Profile",
            result(("TSH", "1.350", "", "0.450-4.500")))
    ]) == "11/2026- TSH 1.4"
    # a TSH result without its own free-T4 item takes the newest
    # standalone `free t4` order's status as the /T4 suffix (15540's
    # 2.11 next to a normal 1.3)
    assert build_lab_summary([
        row("TSH", result(("TSH", "2.11", "N"))),
        row("Free T4", result(("T4, FREE", "1.3", "N", "0.8-1.8"))),
    ]) == "11/2026- TSH 2.1/T4 nl"
    # ... or, for an abnormal standalone free T4 (21462's 1.79 in
    # 0.82-1.77), the raw value
    assert build_lab_summary([
        row("TSH", result(("TSH", "2.690", "", "0.450-4.500"))),
        row("Free T4", result(("T4,Free(Direct)", "1.79", "H", "0.82-1.77"))),
    ]) == "11/2026- TSH 2.7/T4 1.79"
    # a TSH result with its own free-T4 item does not also take the
    # standalone row's T4 (that row stays a thyroid-cluster member,
    # rule 2a)
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "0.78", "N"),
                                  ("T4, FREE", "1.4", "N"))),
        row("Free T4", result(("T4, FREE", "1.1", "N", "0.8-1.8"))),
    ]) == "11/2026- TSH 0.8/T4 nl, T4 nl"
    # a result item that is not one of the vendors' free-T4 items
    # produces nothing
    assert build_lab_summary([
        row("Free T4", result(("Free T4", "1.2", "")))
    ]) == ""


# ----------------------------------------------------------------------
# thyroid cluster (T3 / T4 / TPO / TgAb / TSI)
# ----------------------------------------------------------------------

def test_thyroid_cluster():
    # 21963's LabCorp thyroid work-up: the TSH token carries its own
    # (high) dialysis T4 raw; the normal TPO / TgAb (one `Thyroid
    # Antibodies` order feeds both categories) and the TSI (<0.10 of
    # the 0.00-0.55 range) join one slash token in member order
    assert build_lab_summary([
        row("TSH+Free T4", result(
            ("TSH-ICMA", "0.23", ""),
            ("Free T4 by Dialysis/Mass Spec", "2.5", "H"))),
        row("Thyroid Antibodies", result(
            ("Thyroid Peroxidase (TPO) Ab", "10", "", "0-34"),
            ("Thyroglobulin Antibody", "<1.5", "", "0.0-1.4"))),
        row("Thyroid Stim Immunoglobulin",
            result(("Thyroid Stim Immunoglobulin", "<0.10", "", "0.00-0.55"))),
    ]) == "11/2026- TSH 0.2/T4 2.5, TPO/thyroglobulin/TSI nl"
    # 19725 (Quest): the normal standalone free T3 and TgAb form the
    # yellow notes' `T3/thyroglobulin nl` slash token next to the TSH
    # token
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "2.07", "N"),
                                  ("T4, FREE", "1.2", "N", "0.8-1.8"))),
        row("FREE T3", result(("T3, FREE", "2.9", "N", "2.3-4.2"))),
        row("THYROGLOBULIN ANTIBODIES",
            result(("THYROGLOBULIN ANTIBODIES", "<2", "N", "< or = 2"))),
    ]) == "11/2026- TSH 2.1/T4 nl, T3/thyroglobulin nl"
    # 20754 (an abnormal work-up): the normal TSI renders its `TSI nl`
    # first, then the abnormal members in member order -- the low free
    # T3 (1.6 in 2.3-4.2), the high TPO (166 in <9) and the high TgAb
    # (>1000 in < or = 2, the value written raw)
    assert build_lab_summary([
        row("TSH+FREE T4", result(("TSH", "4.89", "H"),
                                  ("T4, FREE", "0.4", "L", "0.8-1.8"))),
        row("FREE T3", result(("T3, FREE", "1.6", "L", "2.3-4.2"))),
        row("THYROID PEROXIDASE AND THYROGLOBULIN ANTIBODIES",
            result(("THYROGLOBULIN ANTIBODIES", ">1000", "H", "< or = 2"),
                   ("THYROID PEROXIDASE$ANTIBODIES", "166", "H", "<9"))),
        row("TSI (THYROID STIMULATING$IMMUNOGLOBULIN)",
            result(("TSI", "96", "", "<140"))),
    ]) == ("11/2026- TSH 4.9/T4 0.4, TSI nl, T3 1.6(2.3), "
           "TPO 166(9), thyroglobulin >1000(2)")
    # 20872 (pregnancy labs): the standalone TSH order's value picks
    # up the standalone free-T4 draw's status; the normal standalone
    # free T3 is a cluster member on its own
    assert build_lab_summary([
        row("TSH", result(("TSH", "0.63", "N"))),
        row("FREE T4", result(("T4, FREE", "1.0", "N", "0.8-1.8"))),
        row("FREE T3", result(("T3, FREE", "2.5", "N", "2.3-4.2"))),
    ]) == "11/2026- TSH 0.6/T4 nl, T3 nl"
    # 21834: a lone normal TSI
    assert build_lab_summary([
        row("Thyroid Stim Immunoglobulin",
            result(("Thyroid Stim Immunoglobulin", "<0.10", "", "0.00-0.55")))
    ]) == "11/2026- TSI nl"
    # ... and the % baseline TSI assay: a positive (210 in <140)
    # reports its own token
    assert build_lab_summary([
        row("TSI (THYROID STIMULATING$IMMUNOGLOBULIN)",
            result(("TSI", "210", "H", "<140")))
    ]) == "11/2026- TSI 210(140)"
    # a normal free T4 with no TSH row is a cluster member on its own
    assert build_lab_summary([
        row("Free T4", result(("T4, FREE", "1.1", "N", "0.8-1.8")))
    ]) == "11/2026- T4 nl"
    # ... abnormal (21462's 1.79 in 0.82-1.77)
    assert build_lab_summary([
        row("Free T4", result(("T4,Free(Direct)", "1.79", "H", "0.82-1.77")))
    ]) == "11/2026- T4 1.79(1.77)"
    # member order: the normal members slash-join T4 before T3
    assert build_lab_summary([
        row("Free T4", result(("T4, FREE", "1.1", "N", "0.8-1.8"))),
        row("FREE T3", result(("T3, FREE", "2.9", "N", "2.3-4.2"))),
    ]) == "11/2026- T4/T3 nl"
    # LabCorp's free-T3 layout
    assert build_lab_summary([
        row("Free T3, Serum",
            result(("Triiodothyronine,Free,Serum", "2.9", "", "2.0-4.4")))
    ]) == "11/2026- T3 nl"
    assert build_lab_summary([
        row("Free T3, Serum",
            result(("Triiodothyronine,Free,Serum", "1.5", "L", "2.0-4.4")))
    ]) == "11/2026- T3 1.5(2)"
    # LabCorp's standalone TPO order
    assert build_lab_summary([
        row("Thyroid Peroxidase (TPO) Ab",
            result(("Thyroid Peroxidase (TPO) Ab", "10", "", "0-34")))
    ]) == "11/2026- TPO nl"
    assert build_lab_summary([
        row("Thyroid Peroxidase (TPO) Ab",
            result(("Thyroid Peroxidase (TPO) Ab", "166", "H", "<9")))
    ]) == "11/2026- TPO 166(9)"
    # the standalone thyroglobulin-antibody orders (both vendors)
    assert build_lab_summary([
        row("Thyroglobulin Antibody",
            result(("Thyroglobulin Antibody", "<1.5", "", "0.0-1.4")))
    ]) == "11/2026- thyroglobulin nl"
    assert build_lab_summary([
        row("Thyroglobulin Antibodies",
            result(("THYROGLOBULIN ANTIBODIES", ">1000", "H", "< or = 2")))
    ]) == "11/2026- thyroglobulin >1000(2)"
    # the newest row decides: a newer normal TPO hides the older
    # positive one
    assert build_lab_summary([
        row("Thyroid Peroxidase (TPO) Ab",
            result(("Thyroid Peroxidase (TPO) Ab", "10", "", "0-34")),
            result_date="2026-11-07"),
        row("Thyroid Peroxidase (TPO) Ab",
            result(("Thyroid Peroxidase (TPO) Ab", "166", "H", "<9")),
            result_date="2026-10-01"),
    ]) == "11/2026- TPO nl"
    # a pending free T4 that a TSH token would have taken on produces
    # neither suffix nor member
    assert build_lab_summary([
        row("TSH", result(("TSH", "1.4", "N"))),
        row("Free T4", result(("T4, FREE", "", "N", "0.8-1.8"))),
    ]) == "11/2026- TSH 1.4"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("free t4", result(("T4, FREE", "1.1", "N", "0.8-1.8")))
    ]) == "11/2026- T4 nl"


# ----------------------------------------------------------------------
# FSH
# ----------------------------------------------------------------------

def test_fsh():
    # normal (17159's 5.6; the in-house order carries no range) -> FSH nl
    assert build_lab_summary([
        row("FSH, Serum", result(("FSH", "5.6", "")))
    ]) == "11/2026- FSH nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("fsh, serum", result(("FSH", "5.6", "N")))
    ]) == "11/2026- FSH nl"
    # abnormal high, range 2.5-10.2 -> FSH {val}(upper limit)
    assert build_lab_summary([
        row("FSH, Serum", result(("FSH", "12.3", "H", "2.5-10.2")))
    ]) == "11/2026- FSH 12.3(10.2)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("FSH, Serum", result(("FSH", "1.2", "L", "2.5-10.2")))
    ]) == "11/2026- FSH 1.2(2.5)"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([
        row("FSH, Serum", result(("FSH", "12.3", "H")))
    ]) == "11/2026- FSH 12.3"
    # the standalone `FSH` order name (same single-item layout)
    assert build_lab_summary([
        row("FSH", result(("FSH", "12.3", "N")))
    ]) == "11/2026- FSH nl"


# ----------------------------------------------------------------------
# A1c
# ----------------------------------------------------------------------

def test_a1c():
    # always emitted, normal or abnormal; trailing zeros stripped
    assert build_lab_summary([
        row("Hemoglobin A1c", result(("Hemoglobin A1c", "6.0", "H")))
    ]) == "11/2026- A1c 6"
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "7.1", "A")))
    ]) == "11/2026- A1c 7.1"
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.2", "N")))
    ]) == "11/2026- A1c 5.2"
    # the newest liver panel's glucose joins the token: Quest's
    # GLUCOSE item (22457's 86) and LabCorp's Glucose, Serum
    # (17159's 97), rendered like the A1c value
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.7", "H", "<5.7"))),
        row("CMP", result(("GLUCOSE", "86", "N", "65-99"),
                          ("AST", "34", "N", "10-30"),
                          ("ALT", "20", "N", "6-29"))),
    ]) == "11/2026- Glu 86/A1c 5.7"
    assert build_lab_summary([
        row("Hemoglobin A1c", result(("Hemoglobin A1c", "5.5", ""))),
        row("CMP", result(("Glucose, Serum", "97", ""), ("BUN", "20", ""))),
    ]) == "11/2026- Glu 97/A1c 5.5"
    # a high glucose renders plain, like the A1c value (14952's 101)
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.7", "H", "<5.7"))),
        cmp_quest(ast_flag="N", alt_flag="N"),
    ]) == "11/2026- Glu 101/A1c 5.7"
    # the hepatic function panels carry no glucose item -> plain A1c
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.5", "N"))),
        hep_quest(),
    ]) == "11/2026- A1c 5.5, AST/ALT 35/54(46)"
    # a CMP without an A1c row produces no glucose token of its own
    assert build_lab_summary([
        row("CMP", result(("GLUCOSE", "86", "N", "65-99")))
    ]) == ""
    # the in-house BMP (the CMP's items minus the liver ones): its
    # GLUCOSE joins the A1c token too
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.5", "N"))),
        row("BMP", result(("GLUCOSE", "92", "N", "65-99"),
                          ("UREA NITROGEN (BUN)", "8", "N", "7-25"),
                          ("CREATININE", "0.59", "N", "0.50-0.97")))
    ]) == "11/2026- Glu 92/A1c 5.5"
    # an unparseable glucose value is written out raw
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.5", "N"))),
        row("CMP", result(("GLUCOSE", "pending", "A"))),
    ]) == "11/2026- Glu pending/A1c 5.5"
    # the standalone glucose orders (rule 5a): emitted only when
    # abnormal (22457-style GLUCOSE 122 in 65-99)
    assert build_lab_summary([
        row("glucose", result(("GLUCOSE", "122", "H", "65-99")))
    ]) == "11/2026- Glu 122(99)"
    assert build_lab_summary([
        row("glucose, serum", result(("Glucose, Serum", "93", "", "70-99")))
    ]) == ""
    # name matching is case-insensitive; no parsable range -> plain
    assert build_lab_summary([
        row("GLUCOSE", result(("GLUCOSE", "101", "H")))
    ]) == "11/2026- Glu 101"
    # it renders after the A1c token (both can appear: different
    # draws)
    assert build_lab_summary([
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.7", "H", "<5.7"))),
        row("glucose", result(("GLUCOSE", "122", "H", "65-99")),
            result_date="2026-11-05", date="2026-10-19"),
        row("CMP", result(("GLUCOSE", "86", "N", "65-99"))),
    ]) == "11/2026- Glu 86/A1c 5.7, Glu 122(99)"


# ----------------------------------------------------------------------
# LDL (lipid panel)
# ----------------------------------------------------------------------

def lipid_labcorp(ldl_value="104", ldl_flag="H", **kw):
    return row(
        "Lipid Panel",
        result(
            ("Cholesterol, Total", "173", ""),
            ("Triglycerides", "111", ""),
            ("HDL Cholesterol", "51", ""),
            ("VLDL Cholesterol Cal", "18", ""),
            ("LDL Chol Calc (NIH)", ldl_value, ldl_flag),
        ),
        **kw,
    )


def test_ldl():
    # abnormal panel with the NIH LDL item, triglycerides normal -> LDL {val}
    assert build_lab_summary([lipid_labcorp()]) == "11/2026- LDL 104"
    # the panel (not just the LDL item) being abnormal is enough; high
    # triglycerides switch the token to the HDL/LDL/TG shorthand (no
    # reference range here -> no parentheses)
    p = lipid_labcorp(ldl_value="60", ldl_flag="")
    data = json.loads(p["result"])
    for item in data:
        if item["itemName"] == "Triglycerides":
            item.update(value="200", flag="H")
    assert build_lab_summary(
        [row("Lipid Panel", json.dumps(data))]) == "11/2026- 51/60/200"
    # high triglycerides with a reference range -> the upper limit in
    # parentheses (17159's 45/131/151, range 0-149)
    assert build_lab_summary([
        row("Lipid Panel", result(
            ("Cholesterol, Total", "202", "H", "100-199"),
            ("Triglycerides", "151", "H", "0-149"),
            ("HDL Cholesterol", "45", "", ">39"),
            ("VLDL Cholesterol Cal", "26", "", "5-40"),
            ("LDL Chol Calc (NIH)", "131", "H", "0-99")))
    ]) == "11/2026- 45/131/151(149)"
    # Quest's one-sided <150 range renders (150); the normal LDL item
    # still supplies the middle value
    assert build_lab_summary([
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "200", "H", "<150"),
            ("CHOLESTEROL, TOTAL", "180", "N"),
            ("HDL CHOLESTEROL", "45", "N", "> OR = 40"),
            ("LDL-CHOLESTEROL", "95", "N")))
    ]) == "11/2026- 45/95/200(150)"
    # normal panel -> the LDL value is still emitted
    assert build_lab_summary(
        [lipid_labcorp(ldl_value="60", ldl_flag="")]) == "11/2026- LDL 60"
    # Quest's LIPID PANEL names its calculated LDL item
    # LDL-CHOLESTEROL: the token is emitted for it too
    # a low HDL on a normal-triglyceride panel stands alone before
    # the LDL token (the yellow notes' `HDL 43(50)` rows); no range on
    # the HDL item -> no bound
    assert build_lab_summary([
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "66", "N"),
            ("CHOLESTEROL, TOTAL", "201", "H"),
            ("HDL CHOLESTEROL", "45", "L"),
            ("LDL-CHOLESTEROL", "140", "H"),
            ("CHOL/HDLC RATIO", "4.5", "N"),
            ("NON HDL CHOLESTEROL", "156", "H"),
        ))
    ]) == "11/2026- HDL 45, LDL 140"
    # ... with a parsable range the violated lower limit goes in
    # parentheses
    assert build_lab_summary([
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "66", "N"),
            ("CHOLESTEROL, TOTAL", "201", "H"),
            ("HDL CHOLESTEROL", "43", "L", "> OR = 50"),
            ("LDL-CHOLESTEROL", "103", "H")))
    ]) == "11/2026- HDL 43(50), LDL 103"
    # a low HDL on a high-triglyceride panel stays inside the
    # shorthand -- no standalone HDL line
    assert build_lab_summary([
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "200", "H", "<150"),
            ("HDL CHOLESTEROL", "35", "L", "> OR = 40"),
            ("LDL-CHOLESTEROL", "66", "N")))
    ]) == "11/2026- 35/66/200(150)"
    # other LDL-ish items are not the calculated LDL item: a panel that
    # is abnormal but carries no LDL Chol Calc (NIH) / LDL-CHOLESTEROL
    # item produces no token
    assert build_lab_summary([
        row("LIPID PANEL WITH RATIOS", result(
            ("CHOLESTEROL, TOTAL", "230", "H"),
            ("NON HDL CHOLESTEROL", "160", "H"),
            ("LDL/HDL RATIO", "3.2", ""),
        ))
    ]) == ""
    # ... and a normal Quest panel still emits the LDL value
    assert build_lab_summary([
        row("LIPID PANEL", result(
            ("CHOLESTEROL, TOTAL", "170", "N"),
            ("HDL CHOLESTEROL", "55", "N"),
            ("LDL-CHOLESTEROL", "90", "N"),
        ))
    ]) == "11/2026- LDL 90"
    # the reflex / ratio variants carry the same vendor
    # layouts: Quest's `LIPID PANEL WITH REFLEX TO DIRECT LDL` (the
    # direct LDL item carries no range) and LabCorp's `LIPID PANEL
    # WITH LDL/HDL RATIO`
    assert build_lab_summary([
        row("LIPID PANEL WITH REFLEX TO DIRECT LDL", result(
            ("CHOLESTEROL, TOTAL", "217", "H", "<200"),
            ("LDL-CHOLESTEROL", "140", "H"),
            ("NON HDL CHOLESTEROL", "164", "H", "<130"),
            ("TRIGLYCERIDES", "220", "H", "<150"),
            ("HDL CHOLESTEROL", "36", "L", "> OR = 50")))
    ]) == "11/2026- 36/140/220(150)"
    assert build_lab_summary([
        row("LIPID PANEL WITH LDL/HDL RATIO", result(
            ("Cholesterol, Total", "174", "", "100-199"),
            ("Triglycerides", "69", "", "0-149"),
            ("HDL Cholesterol", "69", "", ">39"),
            ("VLDL Cholesterol Cal", "11", "", "5-40"),
            ("LDL Chol Calc (NIH)", "94", "", "0-99"),
            ("LDL/HDL Ratio", "1.4", "", "0.0-3.2")))
    ]) == "11/2026- LDL 94"


# ----------------------------------------------------------------------
# Alb/Cr (microalbumin/creatinine ratio)
# ----------------------------------------------------------------------

def albc_quest(**kw):
    return row(
        "MICROALBUMIN, RANDOM URINE (W/CREATININE)",
        result(
            ("CREATININE, RANDOM URINE", "163", "N"),
            ("MICROALBUMIN", "1.3", "N"),
            ("MICROALBUMIN/CREATININE$RATIO, RANDOM URINE", "8", "N"),
        ),
        **kw,
    )


def albc_labcorp(ratio="16", ratio_flag="", **kw):
    return row(
        "Microalb/Creat Ratio, Randm Ur",
        result(
            ("Microalb/Creat Ratio", ratio, ratio_flag),
            ("Creatinine, Urine", "245.5", ""),
            ("Microalbumin, Urine", "39.9", ""),
        ),
        **kw,
    )


def test_albc():
    # normal (both vendors' layouts, ranges 0-29 / <30) -> Alb/Cr<30
    assert build_lab_summary([albc_quest()]) == "11/2026- Alb/Cr<30"
    assert build_lab_summary([albc_labcorp()]) == "11/2026- Alb/Cr<30"
    # below-the-reporting-limit ratio is normal too
    assert build_lab_summary([albc_labcorp(ratio="<7")]) == "11/2026- Alb/Cr<30"
    # abnormal -> Alb/Cr {val} (raw value of the ratio item)
    assert build_lab_summary([albc_labcorp(ratio="45", ratio_flag="H")]) == \
        "11/2026- Alb/Cr 45"
    assert build_lab_summary([
        row("MICROALBUMIN, RANDOM URINE (W/CREATININE)", result(
            ("CREATININE, RANDOM URINE", "163", "N"),
            ("MICROALBUMIN", "1.3", "N"),
            ("MICROALBUMIN/CREATININE$RATIO, RANDOM URINE", "35", "H"),
        ))
    ]) == "11/2026- Alb/Cr 35"
    # a result with no ratio item produces nothing
    assert build_lab_summary([
        row("Microalb/Creat Ratio, Randm Ur", result(
            ("Creatinine, Urine", "245.5", "")))
    ]) == ""


# ----------------------------------------------------------------------
# AST/ALT / protein (CMP / hepatic function panel)
# ----------------------------------------------------------------------

def cmp_quest(ast_value="42", ast_flag="H", ast_range="10-35",
              alt_value="62", alt_flag="H", alt_range="9-46",
              protein_value="7.4", protein_flag="N",
              protein_range="6.1-8.1", **kw):
    """The in-house CMP order with Quest items (14952's layout); the
    glucose is high (101 in 65-99) and everything else is normal
    unless the AST / ALT / protein are overridden."""
    return row(
        "CMP",
        result(
            ("GLUCOSE", "101", "H", "65-99"),
            ("UREA NITROGEN (BUN)", "22", "N", "7-25"),
            ("CREATININE", "1.03", "N", "0.70-1.35"),
            ("SODIUM", "139", "N", "135-146"),
            ("POTASSIUM", "4.4", "N", "3.5-5.3"),
            ("CHLORIDE", "103", "N", "98-110"),
            ("CARBON DIOXIDE", "29", "N", "20-32"),
            ("CALCIUM", "9.4", "N", "8.6-10.3"),
            ("PROTEIN, TOTAL", protein_value, protein_flag, protein_range),
            ("ALBUMIN", "4.6", "N", "3.6-5.1"),
            ("BILIRUBIN, TOTAL", "0.6", "N", "0.2-1.2"),
            ("ALKALINE PHOSPHATASE", "48", "N", "35-144"),
            ("AST", ast_value, ast_flag, ast_range),
            ("ALT", alt_value, alt_flag, alt_range),
            ("EGFR", "83", "N", "> OR = 60"),
        ),
        **kw,
    )


def test_astalt():
    # both high, in-house CMP (14952's 42 in 10-35 / 62 in 9-46) ->
    # AST/ALT {ast}(upper limit)/{alt}(upper limit)
    assert build_lab_summary([cmp_quest()]) == \
        "11/2026- Glu 101(99), AST/ALT 42(35)/62(46)"
    # name matching is case-insensitive
    assert build_lab_summary([row("cmp", cmp_quest()["result"])]) == \
        "11/2026- Glu 101(99), AST/ALT 42(35)/62(46)"
    # a normal AST / ALT with the fixture's high glucose (no A1c row):
    # the glucose adds its own token beside the AST/ALT one
    assert build_lab_summary([
        cmp_quest(ast_value="28", ast_flag="N",
                  alt_value="30", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99)"
    # Quest's HEPATIC FUNCTION PANEL: only the ALT is high (12885's 54
    # in 9-46); the normal AST (35) is written plain
    assert build_lab_summary([hep_quest()]) == "11/2026- AST/ALT 35/54(46)"
    # LabCorp's layout names the items AST (SGOT) / ALT (SGPT)
    assert build_lab_summary([
        row("Hepatic Function Panel (7)", result(
            ("Protein, Total, Serum", "6.2", "", "6.0-8.5"),
            ("Albumin, Serum", "4.1", "", "3.8-4.8"),
            ("Bilirubin, Total", "0.5", "", "0.0-1.2"),
            ("Alkaline Phosphatase, S", "76", "", "47-123"),
            ("AST (SGOT)", "19", "", "0-40"),
            ("ALT (SGPT)", "60", "H", "0-44")))
    ]) == "11/2026- AST/ALT 19/60(44)"
    # low values are not higher: no AST/ALT token (the CMP's high
    # glucose still emits its own)
    assert build_lab_summary(
        [hep_quest(alt_value="8", alt_flag="L")]) == ""
    assert build_lab_summary([
        cmp_quest(ast_value="8", ast_flag="L",
                  alt_value="10", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99)"
    # an A flag counts as high only when the value parses above the
    # range's upper limit
    assert build_lab_summary([
        cmp_quest(ast_value="45", ast_flag="A",
                  alt_value="30", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99), AST/ALT 45(35)/30"
    assert build_lab_summary([
        cmp_quest(ast_value="30", ast_flag="A",
                  alt_value="30", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99)"
    # Quest's multi-letter `HH` flag counts as high (read by its last
    # letter, like `_bound_for`), `LL` as low
    assert build_lab_summary([
        cmp_quest(ast_value="42", ast_flag="HH",
                  alt_value="30", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99), AST/ALT 42(35)/30"
    assert build_lab_summary([
        cmp_quest(ast_value="8", ast_flag="LL",
                  alt_value="10", alt_flag="N", alt_range="9-46")
    ]) == "11/2026- Glu 101(99)"
    # a high value without a parsable upper limit has no parentheses
    assert build_lab_summary([cmp_quest(alt_range="")]) == \
        "11/2026- Glu 101(99), AST/ALT 42(35)/62"
    # an unparseable high value is written out raw (the bound still
    # comes from the range)
    assert build_lab_summary(
        [cmp_quest(alt_value="pending", alt_flag="H")]) == \
        "11/2026- Glu 101(99), AST/ALT 42(35)/pending(46)"
    # a panel with only the ALT item emits the high ALT alone
    assert build_lab_summary([
        row("HEPATIC FUNCTION PANEL", result(("ALT", "54", "H", "9-46")))
    ]) == "11/2026- ALT 54(46)"
    # ... and a normal ALT item alone produces nothing
    assert build_lab_summary([
        row("HEPATIC FUNCTION PANEL", result(("ALT", "38", "N", "9-46")))
    ]) == ""
    # a panel with only the AST item emits the high AST alone
    assert build_lab_summary([
        row("Hepatic Function Panel (7)",
            result(("AST (SGOT)", "42", "H", "0-40")))
    ]) == "11/2026- AST 42(40)"

    # high protein (22457's 8.4 in 6.1-8.1, alongside the high AST /
    # ALT) -> its own token right after the AST/ALT token
    assert build_lab_summary([
        cmp_quest(ast_value="34", ast_range="10-30",
                  alt_value="66", alt_range="6-29",
                  protein_value="8.4", protein_flag="H")
    ]) == "11/2026- Glu 101(99), AST/ALT 34(30)/66(29), protein 8.4(8.1)"
    # a normal protein alongside a high AST/ALT produces no token
    assert build_lab_summary([cmp_quest()]) == \
        "11/2026- Glu 101(99), AST/ALT 42(35)/62(46)"
    # a high protein with normal AST / ALT -> the token beside the
    # glucose token
    assert build_lab_summary([
        cmp_quest(ast_value="28", ast_flag="N",
                  alt_value="30", alt_flag="N", alt_range="9-46",
                  protein_value="8.4", protein_flag="H")
    ]) == "11/2026- Glu 101(99), protein 8.4(8.1)"
    # a low protein is not high: only the glucose token is emitted
    assert build_lab_summary([
        cmp_quest(ast_value="28", ast_flag="N",
                  alt_value="30", alt_flag="N", alt_range="9-46",
                  protein_value="5.5", protein_flag="L")
    ]) == "11/2026- Glu 101(99)"
    # a high protein without a parsable upper limit has no parentheses
    assert build_lab_summary([
        cmp_quest(ast_value="28", ast_flag="N",
                  alt_value="30", alt_flag="N", alt_range="9-46",
                  protein_value="8.4", protein_flag="H", protein_range="")
    ]) == "11/2026- Glu 101(99), protein 8.4"
    # LabCorp's Protein, Total, Serum item name counts too
    assert build_lab_summary([
        row("Hepatic Function Panel (7)", result(
            ("Protein, Total, Serum", "9.0", "H", "6.0-8.5"),
            ("AST (SGOT)", "19", "", "0-40"),
            ("ALT (SGPT)", "30", "", "0-44")))
    ]) == "11/2026- protein 9.0(8.5)"
    # hep_quest's normal protein (7.8) produces nothing
    assert build_lab_summary([hep_quest()]) == "11/2026- AST/ALT 35/54(46)"

    # A CMP with normal AST / ALT / protein (the cmp_quest fixture's
    # high AST / ALT overrides switched off), for the single-item
    # tests below; the fixture's high glucose (no A1c row) contributes
    # its own `Glu 101(99)` token to each result below
    def cmp_normal():
        return cmp_quest(ast_value="28", ast_flag="N",
                         alt_value="30", alt_flag="N", alt_range="9-46")

    # BUN: abnormal high -> BUN {val}(upper limit), after the AST/ALT
    # and protein tokens
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "UREA NITROGEN (BUN)":
            item.update(value="37", flag="H")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), BUN 37(25)"

    # Cr / CrCl: both abnormal -> one combined token `Cr/CrCl
    # {cr}/{crcl}({bound})`, the trailing bound CrCl's (the 60 floor
    # of the one-sided `> OR = 60` range via the `L` flag); Cr the raw
    # value, CrCl's trailing zeros stripped
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "CREATININE":
            item.update(value="1.3", flag="H")
        if item["itemName"] == "EGFR":
            item.update(value="57", flag="L")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), Cr/CrCl 1.3/57(60)"
    # only Cr abnormal -> Cr {val}(upper limit)
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "CREATININE":
            item.update(value="1.39", flag="H")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), Cr 1.39(1.35)"
    # only eGFR abnormal -> CrCl {val}(lower limit)
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "EGFR":
            item.update(value="57", flag="L")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), CrCl 57(60)"
    # an abnormal Cr without a parsable range has no parentheses
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "CREATININE":
            item.update(value="1.3", flag="H", range="")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), Cr 1.3"
    # the combined token falls back to Cr's bound when CrCl's range is
    # not parsable
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "CREATININE":
            item.update(value="1.3", flag="H")
        if item["itemName"] == "EGFR":
            item.update(value="57", flag="L", range="")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99), Cr/CrCl 1.3/57(1.35)"
    # an abnormal item with an empty value counts as normal (only the
    # fixture's high glucose remains)
    data = json.loads(cmp_normal()["result"])
    for item in data:
        if item["itemName"] == "EGFR":
            item.update(value="", flag="L")
    assert build_lab_summary(
        [row("CMP", json.dumps(data),
             **{k: v for k, v in cmp_normal().items() if k not in ("name", "result")})
    ]) == "11/2026- Glu 101(99)"
    # LabCorp spells the items BUN / Creatinine / eGFR; the one-sided
    # `> OR = 60` eGFR range yields the 60 floor
    assert build_lab_summary([
        row("CMP", result(
            ("Glucose, Serum", "93", "", "70-99"),
            ("BUN", "40", "H", "6-20"),
            ("Creatinine", "1.5", "H", "0.5-1.2"),
            ("eGFR", "47", "L", "> OR = 60"),
            ("Albumin, Serum", "3.5", "L", "3.4-5.4"),
            ("Bilirubin, Total", "1.3", "H", "0.0-1.2"),
            ("Alkaline Phosphatase, S", "146", "H", "47-123"),
            ("AST (SGOT)", "25", "", "0-40"),
            ("ALT (SGPT)", "30", "", "0-44")))
    ]) == ("11/2026- BUN 40(20), Cr/CrCl 1.5/47(60), "
           "bilirubin 1.3(1.2), AP 146(123), albumin 3.5(3.4)")
    # the panel's BILIRUBIN, DIRECT / INDIRECT items are not the
    # bilirubin item (hep_quest's flagged direct bilirubin alone
    # produces nothing)
    data = json.loads(hep_quest()["result"])
    for item in data:
        if item["itemName"] == "ALT":
            item.update(value="30", flag="N")
        if item["itemName"] == "BILIRUBIN, DIRECT":
            item.update(value="0.3", flag="H")
    assert build_lab_summary(
        [row("HEPATIC FUNCTION PANEL", json.dumps(data),
             **{k: v for k, v in hep_quest().items() if k not in ("name", "result")})
    ]) == ""
    # the in-house BMP (the CMP's items minus the liver ones): an
    # abnormal electrolyte reports its own token
    assert build_lab_summary([
        row("BMP", result(
            ("GLUCOSE", "92", "N", "65-99"),
            ("UREA NITROGEN (BUN)", "8", "N", "7-25"),
            ("CREATININE", "0.59", "N", "0.50-0.97"),
            ("SODIUM", "138", "N", "135-146"),
            ("POTASSIUM", "6.1", "H", "3.5-5.3"),
            ("CHLORIDE", "106", "N", "98-110"),
            ("CARBON DIOXIDE", "25", "N", "20-32"),
            ("CALCIUM", "9.1", "N", "8.6-10.2"),
            ("EGFR", "123", "N", "> OR = 60")))
    ]) == "11/2026- K 6.1(5.3)"
    # ... and an all-normal BMP (no liver items at all) produces
    # nothing
    assert build_lab_summary([
        row("bmp", result(
            ("GLUCOSE", "92", "N", "65-99"),
            ("UREA NITROGEN (BUN)", "8", "N", "7-25"),
            ("CREATININE", "0.59", "N", "0.50-0.97"),
            ("SODIUM", "138", "N", "135-146"),
            ("POTASSIUM", "4.0", "N", "3.5-5.3"),
            ("CHLORIDE", "106", "N", "98-110"),
            ("CARBON DIOXIDE", "25", "N", "20-32"),
            ("CALCIUM", "9.1", "N", "8.6-10.2"),
            ("EGFR", "123", "N", "> OR = 60")))
    ]) == ""

# ----------------------------------------------------------------------
# GGT (standalone order; rule 30a)
# ----------------------------------------------------------------------

def test_ggt():
    # normal -> nothing
    assert build_lab_summary([
        row("ggt", result(("GGT", "42", "N", "0-60")))
    ]) == ""
    # abnormal high -> GGT {val}(upper limit) (the real 85 in 0-60)
    assert build_lab_summary([
        row("ggt", result(("GGT", "85", "H", "0-60")))
    ]) == "11/2026- GGT 85(60)"
    # name matching is case-insensitive; no parsable range -> plain
    assert build_lab_summary([
        row("GGT", result(("GGT", "124", "H")))
    ]) == "11/2026- GGT 124"
    # it renders right after the liver panel's tokens
    assert build_lab_summary([
        hep_quest(),
        row("ggt", result(("GGT", "85", "H", "0-60")),
            result_date="2026-11-05", date="2026-10-19"),
    ]) == "11/2026- AST/ALT 35/54(46), GGT 85(60)"


# ----------------------------------------------------------------------
# CK (creatine kinase)
# ----------------------------------------------------------------------

def ck_inhouse(value="55", flag="N", rng="20-239", **kw):
    """The in-house `CREATINE KINASE, TOTAL` order (Quest layout):
    the single item is named after the order."""
    return row("CREATINE KINASE, TOTAL",
               result(("CREATINE KINASE, TOTAL", value, flag, rng, "",
                       "U/L")),
               **kw)


def ck_labcorp(value="122", flag="", rng="41-331", **kw):
    """LabCorp's `Creatine Kinase, Total,Serum` order: the single
    item's name omits the order's space before `Serum`."""
    return row("Creatine Kinase, Total,Serum",
               result(("Creatine Kinase,Total,Serum", value, flag, rng,
                       "", "U/L")),
               **kw)


def test_ck():
    # normal -> CK nl (both vendors' layouts)
    assert build_lab_summary([ck_inhouse()]) == "11/2026- CK nl"
    assert build_lab_summary([ck_labcorp()]) == "11/2026- CK nl"
    # abnormal high -> CK {val}(upper limit) (359374's 388 in 26-366)
    assert build_lab_summary(
        [ck_inhouse("388", "H", "26-366")]) == "11/2026- CK 388(366)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("creatine kinase, total", ck_inhouse()["result"])
    ]) == "11/2026- CK nl"
    # no parsable range -> plain value
    assert build_lab_summary(
        [ck_inhouse("124", "H", "")]) == "11/2026- CK 124"
    # the newest row decides: a newer normal row hides the older
    # abnormal one
    assert build_lab_summary([
        ck_inhouse("55", "N"),
        ck_inhouse("388", "H", "26-366", result_date="2026-09-17"),
    ]) == "11/2026- CK nl"
    # it renders right after the GGT token
    assert build_lab_summary([
        hep_quest(),
        row("ggt", result(("GGT", "85", "H", "0-60")),
            result_date="2026-11-05", date="2026-10-19"),
        ck_inhouse("388", "H", "26-366",
                   result_date="2026-11-05", date="2026-10-19"),
    ]) == "11/2026- AST/ALT 35/54(46), GGT 85(60), CK 388(366)"


def hep_quest(alt_value="54", alt_flag="H", alt_range="9-46", **kw):
    """The full Quest HEPATIC FUNCTION PANEL layout: the AST (35,
    range 10-35) is normal unless overridden via a row copy, and the
    ALT is overridden by the arguments."""
    return row(
        "HEPATIC FUNCTION PANEL",
        result(
            ("PROTEIN, TOTAL", "7.8", "N", "6.1-8.1"),
            ("ALBUMIN", "4.8", "N", "3.6-5.1"),
            ("GLOBULIN", "3.0", "N", "1.9-3.7"),
            ("ALBUMIN/GLOBULIN RATIO", "1.6", "N", "1.0-2.5"),
            ("BILIRUBIN, TOTAL", "0.7", "N", "0.2-1.2"),
            ("BILIRUBIN, DIRECT", "0.2", "N", "< OR = 0.2"),
            ("BILIRUBIN, INDIRECT", "0.5", "N", "0.2-1.2"),
            ("ALKALINE PHOSPHATASE", "103", "N", "35-144"),
            ("AST", "35", "N", "10-35"),
            ("ALT", alt_value, alt_flag, alt_range),
        ),
        **kw,
    )


# ----------------------------------------------------------------------
# Lipoprotein (a)
# ----------------------------------------------------------------------

def cardio_iq(tg="132", tg_flag="", hdl="74", ldl="101", ldl_flag="H",
              lpa="28", lpa_flag="", lpa_rng="<75",
              apob="90", apob_flag="H", **kw):
    """The in-house CARDIO IQ advanced lipid panel row (Quest's
    layout, all 14 items in report order); the defaults are 20912's
    10/2026 result."""
    return row(
        "lipid _ CARDIO IQ(R) ADVANCED LIPID PANEL",
        result(
            ("TRIGLYCERIDES", tg, tg_flag, "<150"),
            ("CHOLESTEROL, TOTAL", "198", "", "<200"),
            ("HDL CHOLESTEROL", hdl, "", ">49"),
            ("LDL-CHOLESTEROL", ldl, ldl_flag, "<100"),
            ("CHOL/HDLC RATIO", "2.7", "", "<5.0"),
            ("NON HDL CHOLESTEROL", "124", "", "<130"),
            ("LIPOPROTEIN (a)", lpa, lpa_flag, lpa_rng),
            ("APOLIPOPROTEIN B", apob, apob_flag, "<90"),
            ("LDL PARTICLE NUMBER", "679", "", "<1138"),
            ("LDL PEAK SIZE", "217.1", "L", ">222.9"),
            ("LDL PATTERN", "B", "A", "A"),
            ("HDL LARGE", "5003", "L", ">6729"),
            ("LDL SMALL", "142", "H", "<142"),
            ("LDL MEDIUM", "161", "", "<215"),
        ),
        **kw,
    )


def test_lpa():
    assert build_lab_summary([
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "22.8", "")))
    ]) == "11/2026- LpA nl"
    assert build_lab_summary([
        row("LIPOPROTEIN (a)", result(("Lipoprotein (a)", "53.1", "")))
    ]) == "11/2026- LpA nl"
    # abnormal, one-sided range <75.0 -> LpA {val}(upper limit), the
    # value rendered as an integer (17159's 227.3 -> 227)
    assert build_lab_summary([
        row("Lipoprotein (a)",
            result(("Lipoprotein (a)", "227.3", "H", "<75.0")))
    ]) == "11/2026- LpA 227(75)"
    # the value rounds to the nearest integer
    assert build_lab_summary([
        row("Lipoprotein (a)",
            result(("Lipoprotein (a)", "227.8", "H", "<75.0")))
    ]) == "11/2026- LpA 228(75)"
    # abnormal, two-sided range -> upper limit
    assert build_lab_summary([
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "120.0", "H", "0-75")))
    ]) == "11/2026- LpA 120(75)"
    # abnormal without a parsable range -> plain value (22457's 97)
    assert build_lab_summary([
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "120.0", "H")))
    ]) == "11/2026- LpA 120"
    # an unparseable value is written out raw
    assert build_lab_summary([
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "pending", "H")))
    ]) == "11/2026- LpA pending"
    # the in-house CARDIO IQ advanced lipid panel row feeds this
    # category too -- its LpA item is mid-list, not the row's first
    # (20912's panel; the yellow notes write it `LDL 101, LpA nl,
    # ApoB 90(<90)`)
    assert build_lab_summary([cardio_iq()]) == \
        "11/2026- LDL 101, LpA nl, ApoB 90(90)"
    # a high-TG CARDIO IQ panel (21910's 34/119/184) renders the
    # shorthand instead
    assert build_lab_summary([
        cardio_iq(tg="184", tg_flag="H", hdl="34", ldl="119", apob="109")
    ]) == "11/2026- 34/119/184(150), LpA nl, ApoB 109(90)"
    # an abnormal mid-list LpA item is found too (value rendered as
    # an integer, like the standalone order's)
    assert build_lab_summary([cardio_iq(lpa="227.3", lpa_flag="H")]) == \
        "11/2026- LDL 101, LpA 227(75), ApoB 90(90)"


# ----------------------------------------------------------------------
# Apolipoprotein B
# ----------------------------------------------------------------------

def test_apob():
    # normal -> ApoB nl
    assert build_lab_summary([
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "71", "N", "<90")))
    ]) == "11/2026- ApoB nl"
    # the all-caps in-house spelling matches too
    assert build_lab_summary([
        row("lipid_ APOLIPOPROTEIN B",
            result(("Apolipoprotein B", "71", "N", "<90")))
    ]) == "11/2026- ApoB nl"
    # abnormal, one-sided range <90 -> ApoB {val}(upper limit)
    # (17159's 102)
    assert build_lab_summary([
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "102", "H", "<90")))
    ]) == "11/2026- ApoB 102(90)"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "102", "H")))
    ]) == "11/2026- ApoB 102"
    # the CARDIO IQ panel row's mid-list item is reported too
    # (20912's ApoB 90 flagged on its <90 range)
    assert build_lab_summary([cardio_iq()]) == \
        "11/2026- LDL 101, LpA nl, ApoB 90(90)"
    # the in-house `Lipid Panel+ApoB` order (LabCorp's layout) feeds
    # the lipid and ApoB categories from one row (13817's panel: LDL
    # 166 flagged on its 0-99 range, ApoB 124 on its <90 range)
    assert build_lab_summary([
        row("Lipid Panel+ApoB",
            result(("Cholesterol, Total", "246", "H", "100-199"),
                  ("Triglycerides", "140", "", "0-149"),
                  ("HDL-C", "55", "", ">39"),
                  ("Non-HDL Cholesterol", "191", "H", "0-129"),
                  ("LDL-C (NIH Calc)", "166", "H", "0-99"),
                  ("Apolipoprotein B", "124", "H", "<90")))
    ]) == "11/2026- LDL 166, ApoB 124(90)"
    # a high-TG `Lipid Panel+ApoB` panel (22391's 87/91/178) renders
    # the shorthand
    assert build_lab_summary([
        row("Lipid Panel+ApoB",
            result(("Cholesterol, Total", "207", "H", "100-199"),
                  ("Triglycerides", "178", "H", "0-149"),
                  ("HDL-C", "87", "", ">39"),
                  ("Non-HDL Cholesterol", "120", "", "0-129"),
                  ("LDL-C (NIH Calc)", "91", "H", "0-99"),
                  ("Apolipoprotein B", "77", "", "<90")))
    ]) == "11/2026- 87/91/178(149), ApoB nl"


# ----------------------------------------------------------------------
# CT CAC (CT cardiac scoring; rule 9a)
# ----------------------------------------------------------------------

def ct_cac(notes, name="CT CARDIAC SCORING", **kw):
    """A CT cardiac-scoring row: the result JSON is a one-entry array
    whose `notes` field is the radiology report (rule 9a)."""
    return row(name, json.dumps([{"notes": notes}]), **kw)


def ct_classic(score="24", pctl="75th percentile",
               lm="0", lad="0", cx="0", rca="0",
               aorta="Nondilated ascending aorta.",
               pericardium="Unremarkable.",
               other="No significant extracardiac findings."):
    """The classic layout's report (the `CT CARDIAC SCORING` order's):
    score / percentile lines, the spelled-out vessel lines, the
    `Pericardium` / `Aorta` / `Other Findings` sections, an
    `IMPRESSION` (which the summary does not consult)."""
    return f"""FINDINGS:
Total Agatston CAC score: {score}
Age/sex adjusted CAC score percentile: {pctl}
Left main: {lm}
Left anterior descending: {lad}
Circumflex: {cx}
Right Coronary: {rca}

Pericardium: {pericardium}
Aorta: {aorta}
Other Findings: {other}

IMPRESSION:
Total Agatston calcium score {score}."""


def ct_plus(score="92", pctl="25", lm="0", lad="0", lcx="0", rca="1",
            aorta="Nondilated ascending aorta.",
            other="No significant extracardiac findings identified."):
    """The Plus layout's report (the AI-enhanced `Cardiac Calcium
    Score Plus` order's): a sentence-style score line, a bare-number
    percentile, the `LM` / `LAD` / `LCX` / `RCA/PDA` vessel lines,
    an all-caps `OTHER FINDINGS` section."""
    return f"""FINDINGS:

The total Agatston CAC score is {score}.
Age/sex adjusted CAC score percentile:  {pctl}

Vessel-level Agatston CAC scoring:
LM: {lm}
LAD: {lad}
LCX: {lcx}
RCA/PDA: {rca}

EXTRA-CORONARY CALCIFICATION:
No calcification of the aortic valve leaflets.

PERICARDIUM:  Unremarkable.

Aorta: {aorta}

Pulmonary arteries: Nondilated main pulmonary artery.

OTHER FINDINGS:  {other}

IMPRESSION:

1.  No calcified coronary plaque."""


def test_cac_score():
    # the classic layout: the FINDINGS score line + the percentile's
    # shorthand (13933's `75th percentile` -> `75%`)
    assert build_lab_summary([ct_cac(ct_classic())]) == \
        "11/2026- CAC=24; 75%"
    # the percentile's spellings: `Less than 30th percentile` ->
    # `<30%`, `Greater than 90th ...` -> `>90%`, the `0-25th` band ->
    # `<25%`, the other bands kept
    assert build_lab_summary([
        ct_cac(ct_classic(score="0", pctl="Less than 30th percentile"))
    ]) == "11/2026- CAC=0; <30%"
    assert build_lab_summary([
        ct_cac(ct_classic(pctl="Greater than 90th percentile"))
    ]) == "11/2026- CAC=24; >90%"
    assert build_lab_summary([
        ct_cac(ct_classic(pctl="0-25th percentile."))
    ]) == "11/2026- CAC=24; <25%"
    assert build_lab_summary([
        ct_cac(ct_classic(pctl="25-50th percentile."))
    ]) == "11/2026- CAC=24; 25-50%"
    # bare numbers (the `90th` / `90` / `90.` / `90%` spellings) all
    # render `90%`
    for pctl in ("90th", "90", "90.", "90%"):
        assert build_lab_summary([ct_cac(ct_classic(pctl=pctl))]) == \
            "11/2026- CAC=24; 90%"
    # the Plus layout: sentence-style score line, bare-number
    # percentile (19497's 92 / 25)
    assert build_lab_summary([ct_cac(ct_plus())]) == \
        "11/2026- CAC=92; 25%"
    # a report with no parsable percentile renders the score alone
    assert build_lab_summary([ct_cac(ct_classic(pctl=""))]) == \
        "11/2026- CAC=24"
    # a fractional score keeps its decimal (22353's 1.5)
    assert build_lab_summary([ct_cac(ct_classic(score="1.5"))]) == \
        "11/2026- CAC=1.5; 75%"


def test_cac_aorta():
    # a normal aorta produces nothing (14455's `Measures 4.3 cm ...`
    # sentence names no finding either, like the nondilated aortas')
    assert build_lab_summary([ct_cac(ct_classic())]) == \
        "11/2026- CAC=24; 75%"
    # 19710's ectasia, written with the `measuring` verb dropped and
    # the trailing period stripped
    assert build_lab_summary([
        ct_cac(ct_classic(score="0", pctl="Less than 30th percentile",
                          aorta="Ascending aortic ectasia measuring 3.6 cm."))
    ]) == "11/2026- CAC=0; <30%, Ascending aortic ectasia 3.6 cm"
    # a section that opens `Nondilated` reports only its abnormal
    # sentence (19506's report)
    assert build_lab_summary([
        ct_cac(ct_classic(aorta=(
            "Nondilated ascending aorta. "
            "Ascending aortic ectasia measuring 3.7 cm.")))
    ]) == "11/2026- CAC=24; 75%, Ascending aortic ectasia 3.7 cm"
    # `without aneurysm` text is not a finding
    assert build_lab_summary([
        ct_cac(ct_classic(aorta=(
            "Aortic atherosclerotic calcifications are present without "
            "aneurysm in the visualized segments.")))
    ]) == "11/2026- CAC=24; 75%"


def test_cac_vessels():
    # 21634's vessels: only the RCA's 97 reads as a severe stenosis
    # percentage (the LAD's 165 is not one); the other findings'
    # mediastinal calcifications are not reported
    assert build_lab_summary([
        ct_cac(ct_classic(score="343", pctl="90th", lm="74", lad="165",
                          cx="7", rca="97",
                          other=("A few nonspecific calcifications in the "
                                 "anterior mediastinum.")))
    ]) == "11/2026- CAC=343; 90%, RCA 97%"
    # fractional vessel scores are not percentages
    assert build_lab_summary([ct_cac(ct_classic(lm="96.80"))]) == \
        "11/2026- CAC=24; 75%"
    # the Plus layout's vessel lines (19497's LAD 91)
    assert build_lab_summary([ct_cac(ct_plus(lad="91"))]) == \
        "11/2026- CAC=92; 25%, LAD 91%"


def test_cac_nodules():
    # 18759's two nodules -> the `x2` shorthand
    assert build_lab_summary([
        ct_cac(ct_classic(score="274", pctl="55th",
                          other="Two lower lobe pulmonary nodules "
                                "measuring 4 mm."))
    ]) == "11/2026- CAC=274; 55%, lung nodules x2 4 mm"
    # 21743's single nodule
    assert build_lab_summary([
        ct_cac(ct_classic(score="0", pctl="Less than 30th percentile",
                          other="Left upper lobe 3 mm pulmonary nodule."))
    ]) == "11/2026- CAC=0; <30%, lung nodule 3 mm"
    # 21462's: a leading `2 mm` is the size, not a count
    assert build_lab_summary([
        ct_cac(ct_classic(score="23", pctl="70th percentile",
                          other=("2 mm left lower lobe pulmonary nodule, "
                                 "unchanged from prior CT.")))
    ]) == "11/2026- CAC=23; 70%, lung nodule 2 mm"
    # non-nodule other findings produce nothing
    assert build_lab_summary([
        ct_cac(ct_classic(other=("A few nonspecific calcifications in "
                                 "the anterior mediastinum.")))
    ]) == "11/2026- CAC=24; 75%"
    # the Plus layout's `nodular groundglass opacities` are not
    # nodules (19497's report)
    assert build_lab_summary([
        ct_cac(ct_plus(other=("There are new abnormality nodular "
                              "groundglass opacities in the lower "
                              "lobes.")))
    ]) == "11/2026- CAC=92; 25%"


def test_cac_order_and_date():
    # the CAC tokens follow the lipids (rule 9a, between the ApoB of
    # rule 9 and the CBC of rule 10)
    assert build_lab_summary([
        ct_cac(ct_classic()),
        ua_labcorp(),
    ]) == "11/2026- UA nl, CAC=24; 75%"
    assert build_lab_summary([
        ct_cac(ct_classic()),
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "71", "N", "<90"))),
    ]) == "11/2026- ApoB nl, CAC=24; 75%"
    # a CAC-only patient: the leading date is the CAC row's
    assert build_lab_summary([
        ct_cac(ct_classic(), result_date="2026-09-05", date="2026-08-24")
    ]) == "09/2026- CAC=24; 75%"
    # a CAC row with no report text contributes nothing (like the
    # other imaging rows); it does not set the leading date either
    assert build_lab_summary([ct_cac("")]) == ""
    assert build_lab_summary([
        ct_cac("", result_date="2026-09-05"),
        ua_labcorp(),
    ]) == "11/2026- UA nl"
    # the newest report wins, like the other categories
    assert build_lab_summary([
        ct_cac(ct_classic(score="0", pctl=""), result_date="2026-11-07"),
        ct_cac(ct_classic(), result_date="2026-09-05"),
    ]) == "11/2026- CAC=0"


# ----------------------------------------------------------------------
# Mammo (mammogram; rule 9b)
# ----------------------------------------------------------------------

def mammo(notes, name="Mammo SCREENING MAMMO W/3D TOMOSYNTHESIS", **kw):
    """A mammogram row: the result JSON is a one-entry array whose
    `notes` field is the radiology report (rule 9b)."""
    return row(name, json.dumps([{"notes": notes}]), **kw)


def mammo_report(birads, impression):
    """A mammogram report: the exam's standard sections, the
    `IMPRESSION` and the `BI-RADS {n}` assessment line (rule 9b)."""
    return f"""Exam # 4985377 - November 6 2026 - MAMMO -

INDICATION:  Asymptomatic screening.

TECHNIQUE:  Standard 3D tomosynthesis images were obtained of the bilateral breasts in both the CC and MLO projections.

BREAST DENSITY:  The breasts are heterogeneously dense, which may obscure small masses.

FINDINGS:  No breast arterial calcifications (BAC) are noted.

IMPRESSION:

{impression}

Lifetime breast cancer risk according to Tyrer-Cuzick v8 breast cancer risk assessment tool: 6.3%

BI-RADS {birads}.

In compliance with MQSA regulations and ACR guidelines, a letter stating the findings of this exam is being sent to your patient.
"""


def test_mammo():
    # BI-RADS 1 / 2 are normal (1 / 2's `No evidence of malignancy`
    # impression is not reported)
    assert build_lab_summary([
        mammo(mammo_report("1 - NEGATIVE", "No evidence of malignancy."))
    ]) == "11/2026- Mammo nl"
    assert build_lab_summary([
        mammo(mammo_report("2 - BENIGN", "No evidence of malignancy."))
    ]) == "11/2026- Mammo nl"
    # a probably-benign exam reports the impression's finding sentences
    # in full, the way the yellow notes write them (the raw BI-RADS
    # number is never reported); the `No ...` negative statement and
    # the lifetime-risk line are dropped (21643's report)
    assert build_lab_summary([
        mammo(mammo_report("3 - PROBABLY BENIGN", (
            "1.  Probably benign right breast mass, which may reflect "
            "a fibroadenoma.\n2.  No sonographic abnormality in the "
            "left breast.\n\nSix month follow-up ultrasound is "
            "recommended.")))
    ]) == ("11/2026- Mammo: Probably benign right breast mass, which "
           "may reflect a fibroadenoma. Six month follow-up ultrasound "
           "is recommended")
    # a suspicious exam (19482's report): the outside-comparison
    # addendum line and the patient-discussion boilerplate are dropped
    assert build_lab_summary([
        mammo(mammo_report("4 - SUSPICIOUS ABNORMALITY", (
            "1.  Right breast, mass seen on screening mammography, "
            "correlates to a 9:00 position mass, which requires "
            "ultrasound-guided tissue sampling for definitive "
            "diagnosis.\n2.  Should patient's prior outside "
            "mammography become available to our facility, comparison "
            "will be made with an addendum to follow accordingly.\n\n"
            "Ultrasound guided biopsy is recommended. This was "
            "discussed with the patient at the time of the exam.")))
    ]) == ("11/2026- Mammo: Right breast, mass seen on screening "
           "mammography, correlates to a 9:00 position mass, which "
           "requires ultrasound-guided tissue sampling for definitive "
           "diagnosis. Ultrasound guided biopsy is recommended")
    # 0's incomplete exam is not normal (22120's report): the finding
    # and the comparison / recall recommendation
    assert build_lab_summary([
        mammo(mammo_report("0 - INCOMPLETE", (
            "1.  Right breast architectural distortion.\n\nComparison "
            "with prior imaging is needed. If no priors are available "
            "or the finding is new, diagnostic right mammogram with "
            "spot compression and ML views are recommended with US if "
            "needed.")))
    ]) == ("11/2026- Mammo: Right breast architectural distortion. "
           "Comparison with prior imaging is needed. If no priors are "
           "available or the finding is new, diagnostic right "
           "mammogram with spot compression and ML views are "
           "recommended with US if needed")
    # a `No ...` sentence that still names a finding is kept (16389's
    # stable-probably-benign-mass follow-ups)
    assert build_lab_summary([
        mammo(mammo_report("3 - PROBABLY BENIGN", (
            "1.  No suspicious change in probably benign left breast "
            "9:00 N3 mass.\n2.  No mammographic or sonographic "
            "evidence of malignancy in the right breast\n\n12 month "
            "follow-up mammogram and ultrasound is recommended.")))
    ]) == ("11/2026- Mammo: No suspicious change in probably benign "
           "left breast 9:00 N3 mass. 12 month follow-up mammogram "
           "and ultrasound is recommended")
    # the Mammogram-Plus-Heart dense-tissue counseling block is
    # boilerplate (19482's recall)
    assert build_lab_summary([
        mammo(mammo_report("0 - INCOMPLETE", (
            "1.  Mass identified at 11 o'clock in the right breast.\n\n"
            "Comparison with prior imaging is needed.\n\nBilateral "
            "whole breast ultrasound (ABVS or handheld) is recommended "
            "at the time of diagnostic imaging: Increased breast "
            "density (C or D) is associated with increased risk of "
            "breast cancer and can also mask cancers on mammography.\n"
            "\nAdding screening ultrasound reduces interval cancer "
            "rates in women with dense tissue.")))
    ]) == ("11/2026- Mammo: Mass identified at 11 o'clock in the "
           "right breast. Comparison with prior imaging is needed")
    # a mammo-named row whose report is another exam (19252's bone
    # density) carries no BI-RADS line -> nothing
    assert build_lab_summary([
        mammo("Exam # 52328045 - BONE DENSITY. INDICATION: Osteopenia.\n"
              "IMPRESSION:  T-score -1.8, osteopenia.")
    ]) == ""
    # the vendor's `MG` prefix is the same category
    assert build_lab_summary([
        mammo(mammo_report("1 - NEGATIVE", "No evidence of malignancy."),
              name="MG - Screening Mammo Bilat with Tomo plus Heart")
    ]) == "11/2026- Mammo nl"


def test_mammo_order_and_date():
    # the Mammo token follows the CAC tokens (rule 9b, after the CT
    # CAC of rule 9a and before the CBC of rule 10)
    assert build_lab_summary([
        ct_cac(ct_classic()),
        mammo(mammo_report("1 - NEGATIVE", "No evidence of malignancy.")),
        ua_labcorp(),
    ]) == "11/2026- UA nl, CAC=24; 75%, Mammo nl"
    # a mammo-only patient: the leading date is the mammo row's
    assert build_lab_summary([
        mammo(mammo_report("1 - NEGATIVE", "No evidence of malignancy."),
              result_date="2026-09-05", date="2026-08-24")
    ]) == "09/2026- Mammo nl"
    # a mammo row with no report text contributes nothing (like the
    # other imaging rows); it does not set the leading date either
    assert build_lab_summary([mammo("")]) == ""
    assert build_lab_summary([
        mammo("", result_date="2026-09-05"),
        ua_labcorp(),
    ]) == "11/2026- UA nl"
    # the newest report wins, like the other categories
    assert build_lab_summary([
        mammo(mammo_report("1 - NEGATIVE", "No evidence of malignancy."),
              result_date="2026-11-07"),
        mammo(mammo_report("3 - PROBABLY BENIGN",
                           "1.  Probably benign right breast mass."),
              result_date="2026-09-05"),
    ]) == "11/2026- Mammo nl"


# ----------------------------------------------------------------------
# US (ultrasound; rule 9c)
# ----------------------------------------------------------------------

def us(notes, name="US ABDOMEN LIMITED", **kw):
    """An ultrasound row: the result JSON is a one-entry array whose
    `notes` field is the radiology report (rule 9c)."""
    return row(name, json.dumps([{"notes": notes}]), **kw)


def us_report(impression, head="IMPRESSION:"):
    """An ultrasound report: the exam's standard sections, the
    `IMPRESSION` (or the Plus breast reports' `ASSESSMENT/MANAGEMENT`),
    and the signed-by / letter tail (rule 9c)."""
    return f"""Exam # 44S273402 - November 16 2026 - ABDOMEN LIMITED -
Exam Performed at SimonMed Northern CA San Mateo

INDICATION:  Gallbladder disease.

TECHNIQUE:  Grayscale imaging was performed of the right upper abdominal quadrant.

FINDINGS:

Liver: The liver is within normal limits.

{head}

{impression}
ELECTRONICALLY SIGNED BY : Provider (Arafat, Omar) on

Thank you for your kind referral. If you need further assistance, please contact our Radiologist Hotline at 855-RAD-TALK or 855-723-8255.
----------------------------------------------------------------------
Electronically Signed by: Arafat, Omar
"""


def test_us():
    # an unremarkable exam is normal (the yellow notes' `us abd nml`)
    assert build_lab_summary([
        us(us_report("Unremarkable exam"))
    ]) == "11/2026- US abd nl"
    # the negative statements (`No ...` / `unremarkable` / `within
    # normal limits`) are not findings
    assert build_lab_summary([
        us(us_report("1.  No gallstone seen."))
    ]) == "11/2026- US abd nl"
    # the `No ...` sentence still names a finding (a stone, a
    # followed-up mass): the `Non obstructing ... calculus` finding
    # next to the `unremarkable` statements (18822's report)
    assert build_lab_summary([
        us(us_report(
            "1.  Non obstructing left renal calculus.\n"
            "2.  Right kidney and urinary bladder appear unremarkable."),
            name="US RENAL")
    ]) == "11/2026- US renal: Non obstructing left renal calculus"
    # several items: the finding items are reported, the negative /
    # `Otherwise normal` ones are not (22285's report)
    assert build_lab_summary([
        us(us_report(
            "1.  Cholelithiasis without evidence of acute cholecystitis\n"
            "2.  Hepatic steatosis and punctate hepatic cysts which "
            "requires no follow-up\n"
            "3.  Otherwise normal ultrasound"))
    ]) == ("11/2026- US abd: Cholelithiasis without evidence of acute "
           "cholecystitis. Hepatic steatosis and punctate hepatic "
           "cysts which requires no follow-up")
    # a `Normal ...` sentence that names a finding (a fatty liver)
    assert build_lab_summary([
        us(us_report("1.  Normal sized mildly fatty liver."))
    ]) == "11/2026- US abd: Normal sized mildly fatty liver"
    # a line-wrapped sentence stays one `nl` statement (the carotid
    # reports' `... stenosis on either / side.`)
    assert build_lab_summary([
        us(us_report(
            "No hemodynamically significant internal carotid artery "
            "(ICA) stenosis on either\nside.\nNormal antegrade "
            "vertebral arterial flow bilaterally."), name="US CAROTID")
    ]) == "11/2026- US carotid nl"
    # the AAA screening's `No ...` statement (21463's report)
    assert build_lab_summary([
        us(us_report("No abdominal aortic aneurysm."),
            name="US AAA Screening (Medicare)")
    ]) == "11/2026- US AAA nl"
    # the liver-fat grading-scale block, the `LI-RADS` assessment
    # line and the `... obscured` limitation sentence are boilerplate,
    # not findings (19506's report)
    assert build_lab_summary([
        us(us_report(
            "Current 12 cm liver length versus 9.6 cm length, on the "
            "most recent prior abdominal study. The liver parenchyma "
            "normal appearance currently, not significantly echogenic. "
            "No liver mass. No adjacent ascites. 8.6% mild increased "
            "estimated hepatocyte fat content, compatible with mild "
            "hepatic steatosis, grade 1. The pancreas distal body, "
            "tail and head are obscured.\n\n"
            "Liver fat is graded from 0 to 3 based on hepatocyte "
            "fat content. The liver is fatty when more than 5% of "
            "hepatocytes contain fat. Grade 1 (mild) = 5-33%\n"
            "Li-rads VIS-A, US-1."))
    ]) == ("11/2026- US abd: Current 12 cm liver length versus 9.6 "
           "cm length, on the most recent prior abdominal study. The "
           "liver parenchyma normal appearance currently, not "
           "significantly echogenic. No adjacent ascites. 8.6% mild "
           "increased estimated hepatocyte fat content, compatible "
           "with mild hepatic steatosis, grade 1")
    # the ACR TI-RADS guideline block and the Koios disclaimer trail
    # the thyroid reports' impression and are not findings: a normal
    # exam (351506's report) and an abnormal one (379345's report)
    tirads_block = (
        "\n\nAmerican College of Radiology TI-RADS (TR) Categories and "
        "Recommendations: TR1: 0 points, Benign, No FNA\n"
        "TR4: 4-6 points, Moderately Suspicious, FNA if 1.5 cm+, "
        "Follow if 1 cm+\n\nFollow-up ultrasound guidelines:\n"
        "TR4: At 1, 2, 3 and 5 years, if no growth or change in "
        "TI-RADS level\nIf change but below threshold for FNA, repeat "
        "in one year.\n\nSource: ACR Thyroid Imaging, Reporting and "
        "Data System (TI-RADS): White Paper of the ACR TI-RADS "
        "Committee. Tesler et al., J Am Coll Radiol 2017;14:587-595.\n\n"
        "DISCLAIMER:  The Koios AI Adapter is utilized as a "
        "decision-support tool. The final interpretation, impression, "
        "and recommendations are at the discretion of the "
        "radiologist's judgment and application of TI RADS guidelines, "
        "as indicated.")
    assert build_lab_summary([
        us(us_report("No thyroid nodules meet criteria for FNA or "
                     "follow-up." + tirads_block),
            name="US - Plus Thyroid")
    ]) == "11/2026- US thyroid nl"
    assert build_lab_summary([
        us(us_report(
            "1.  Left mid thyroid nodule measuring 1.4 cm, moderately "
            "suspicious (TI-RADS 4); follow-up recommended at 1, 2, 3, "
            "5 years.\n2.  Right mid thyroid nodule measuring 0.6 cm, "
            "not suspicious (TI-RADS 2); no follow-up recommended."
            + tirads_block), name="US - Plus Thyroid")
    ]) == ("11/2026- US thyroid: Left mid thyroid nodule measuring "
           "1.4 cm, moderately suspicious (TI-RADS 4); follow-up "
           "recommended at 1, 2, 3, 5 years. Right mid thyroid nodule "
           "measuring 0.6 cm, not suspicious (TI-RADS 2); no "
           "follow-up recommended")
    # the liver-elastography order's label (13027's report): the
    # WFUMB guideline table trails the impression
    assert build_lab_summary([
        us(us_report("No abnormalities detected in the liver.\n\n"
                     "World Federation of Ultrasound in Medicine and "
                     "Biology (WFUMB) Vendor-Neutral Guidelines on "
                     "Liver Ultrasound Elastography using ARFI-SWE "
                     "Techniques (rule of four)\n"
                     "</=5 kPa (1.3 m/sec)            High probability "
                     "of being normal\n"
                     ">13 kPa (2.1 m/sec)             Rules in cACLD"),
            name="US Abdomen Complete with Liver Elastography")
    ]) == "11/2026- US abd w/ liver elastography nl"
    # a breast report with a `BI-RADS {n}` line is like the mammo's
    # (rule 9b): 1-2 -> `US breast nl`, else the findings (369461's
    # report); the lifetime-risk line, the assessment line and the
    # `No evidence ...` statement are not findings
    assert build_lab_summary([
        us("No evidence of malignancy.\n\nAnnual routine bilateral "
           "screening mammogram is recommended.\n\nLifetime breast "
           "cancer risk according to Tyrer-Cuzick v8 breast cancer "
           "risk assessment tool: 5.2%\n\nBI-RADS 1 - NEGATIVE.",
           name="US BREAST BILATERAL COMPLETE")
    ]) == "11/2026- US breast nl"
    assert build_lab_summary([
        us(
            "1.  No sonographic evidence of right breast malignancy.\n"
            "2.  Left breast 6:00 position 1.5 cm mass requires "
            "six-month follow-up surveillance ultrasound to ensure "
            "stability and confirm benignity.\n\nSix month follow-up "
            "left breast ultrasound is recommended and if needed "
            "diagnostic mammography.\n\nLifetime breast cancer risk "
            "according to Tyrer-Cuzick v8 breast cancer risk "
            "assessment tool: 13.4%\n\nBI-RADS 3 - PROBABLY BENIGN.",
            name="US BREAST BILATERAL COMPLETE")
    ]) == ("11/2026- US breast: Left breast 6:00 position 1.5 cm mass "
           "requires six-month follow-up surveillance ultrasound to "
           "ensure stability and confirm benignity. Six month "
           "follow-up left breast ultrasound is recommended and if "
           "needed diagnostic mammography")
    # the Plus breast reports' `ASSESSMENT/MANAGEMENT` head and the
    # dense-tissue counseling block (14269's report)
    assert build_lab_summary([
        us(us_report("Probably benign mass, likely a cyst cluster at 12 "
                    "o'clock, stable.\n\nDiagnostic bilateral mammogram is "
                    "recommended in 6 months with targeted left breast "
                    "ultrasound.  Bilateral whole breast ultrasound (ABVS or "
                    "handheld) is recommended at the time of diagnostic "
                    "imaging: Increased breast density (C  or D) is associated "
                    "with increased risk of breast cancer and can also mask "
                    "cancers on mammography. Adding screening ultrasound "
                    "reduces interval cancer rates in women with dense tissue.\n\n"
                    "Lifetime breast cancer risk according to Tyrer-Cuzick v8 "
                    "breast cancer risk assessment tool: 7.8%\n\n"
                    "BI-RADS 3 - PROBABLY BENIGN.",
                    head="ASSESSMENT/MANAGEMENT:"),
           name="US BREAST BILATERAL COMPLETE")
    ]) == ("11/2026- US breast: Probably benign mass, likely a cyst "
           "cluster at 12 o'clock, stable. Diagnostic bilateral "
           "mammogram is recommended in 6 months with targeted left "
           "breast ultrasound")


def test_us_order_and_date():
    # the US tokens follow the mammo token (rule 9c, after the CT CAC
    # of rule 9a and the mammo of rule 9b and before the CBC of rule
    # 10); the region labels are in the fixed order, the newest row
    # per label is that region's row
    assert build_lab_summary([
        us(us_report("Unremarkable exam"), result_date="2026-11-05"),
        us("No evidence of malignancy.\nBI-RADS 1 - NEGATIVE.",
           name="US BREAST BILATERAL COMPLETE", result_date="2026-11-04"),
        ua_labcorp(),
    ]) == "11/2026- UA nl, US abd nl, US breast nl"
    assert build_lab_summary([
        us(us_report("No thyroid nodules meet criteria for FNA."),
            name="US THYROID", result_date="2026-11-07"),
        us(us_report("Unremarkable exam"),
            name="US ABDOMEN LIMITED", result_date="2026-09-05"),
    ]) == "11/2026- US abd nl, US thyroid nl"
    # a US-only patient: the leading date is the US row's
    assert build_lab_summary([
        us(us_report("Unremarkable exam"),
           result_date="2026-09-05", date="2026-08-24")
    ]) == "09/2026- US abd nl"
    # a US row with no report text contributes nothing (like the
    # other imaging rows); it does not set the leading date either
    assert build_lab_summary([us("")]) == ""
    assert build_lab_summary([
        us("", result_date="2026-09-05"),
        ua_labcorp(),
    ]) == "11/2026- UA nl"
    # the `refer to ... report` deferral reports (a limited exam that
    # defers to the mammogram) carry no US finding of their own:
    # alone, they produce nothing...
    assert build_lab_summary([
        us("Exam # 49038954 - February 5 2026 - BREAST BILATERAL "
           "COMPLETE -\nExam Performed at SimonMed Northern CA San "
           "Mateo\n\nRefer to diagnostic mammogram report for "
           "ultrasound findings.\n\nIn compliance with MQSA "
           "regulations and ACR guidelines, a letter stating the "
           "findings of this exam is being sent to your patient.",
           name="US BREAST BILATERAL COMPLETE")
    ]) == ""
    # ...and a deferral does not stand in for the region's newest
    # result: the newest exam with a report of its own is that
    # region's row
    assert build_lab_summary([
        us("Refer to diagnostic mammogram report for ultrasound "
           "findings.", name="US BREAST BILATERAL COMPLETE",
           result_date="2026-11-03"),
        us("No evidence of malignancy.\nBI-RADS 1 - NEGATIVE.",
           name="US BREAST BILATERAL COMPLETE", result_date="2026-09-08"),
    ]) == "09/2026- US breast nl"


# ----------------------------------------------------------------------
# BONE DENSITY (DEXA; rule 9d)
# ----------------------------------------------------------------------

def bmd(notes, name="BONE DENSITY", **kw):
    """A bone-density row: the result JSON is a one-entry array whose
    `notes` field is the DEXA report (rule 9d)."""
    return row(name, json.dumps([{"notes": notes}]), **kw)


def bmd_report(impression, lumbar="-0.6", femur="-0.9", hip="-0.8",
               head="FINDINGS:"):
    """A SimonMed bone-density report: the `FINDINGS` site blocks
    (the lumbar spine, the left femoral neck, the left total hip)
    and the boilerplate `IMPRESSION` / `RELATED INFORMATION`
    sections (rule 9d)."""
    return f"""Exam # 53281049 - November 2 2026 - BONE DENSITY -
Exam Performed at SimonMed Northern CA Daly City

INDICATION:  Osteoporosis screening Z13.820.

COMPARISON:  4/15/2024

TECHNIQUE:  Bone mineral density was evaluated.

{head}

Lumbar Spine (L1-L4):
BMD:  1.123 g/cm2
T-Score:  {lumbar}
Z-Score:  1.1

Left Femoral Neck:
BMD:  0.733 g/cm2
T-Score:  {femur}
Z-Score:  -0.7

Left Total Hip:
BMD:  0.888 g/cm2
T-Score:  {hip}
Z-Score:  0.3

IMPRESSION:

{impression}

RELATED INFORMATION:

1.  The T-score is relative to peak bone mass in early adulthood, while the Z-score is relative to individuals of the same age and sex.

2.  The International Society for Clinical Densitometry recommends categorizing the patient according to the lowest T-score from the total L-spine, total hip, and femoral neck, utilizing the following World Health Organization criteria:

Normal range:   T-score of -1.0 or above
Low bone mass:   T-score of less than -1.0 but greater than -2.5
Osteoporosis:   T-score of -2.5 or below
"""


def test_bmd():
    # every site above the WHO -1.0 cutoff is normal (the yellow
    # notes' `Bone density nml`)
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of normal."))
    ]) == "11/2026- Bone density nl"
    # the lowest T-score's site and value, as on the report (the
    # yellow notes' `Femur -1.9`); the higher abnormal sites are not
    # named (15629's report)
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of low bone mass in "
            "the left femoral neck, and normal bone mass in the left "
            "total hip and L1-L4.",
            lumbar="-1.5", femur="-1.9", hip="-1.4"))
    ]) == "11/2026- Bone density femur -1.9"
    # the total hip is the lowest site (12606's `hip -3.1`)
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of osteoporosis in "
            "L1-L4 and the left hip.",
            lumbar="-2.5", femur="-2.2", hip="-3.1"))
    ]) == "11/2026- Bone density hip -3.1"
    # the lumbar spine is the lowest site (17512's `lumbar spine
    # -2.1`)
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of low bone mass in "
            "L1-L4, and normal bone mass in the left femoral neck "
            "and the left total hip.",
            lumbar="-2.1", femur="-0.8", hip="-0.6"))
    ]) == "11/2026- Bone density lumbar -2.1"
    # a T-score of exactly -1.0 is reported, not `nl` (22322's
    # `Femur -1.0`)
    assert build_lab_summary([
        bmd(bmd_report("1.  Normal bone mass in the left total hip "
                       "and L1-L4.", lumbar="2.1", femur="-1.0",
                       hip="-0.2"))
    ]) == "11/2026- Bone density femur -1"
    # the `Left/Right` layout's double T-score values count the lower
    # one (22120's report: the right hip's -2.1 is the study's
    # lowest)
    assert build_lab_summary([
        bmd("Exam # 44S267905 - May 6 2026 - BONE DENSITY -\n"
            "FINDINGS:\n\n"
            "Lumbar Spine (L1-L4):\n"
            "T-Score:  -1.4\n\n"
            "Left/Right Femoral Neck:\n"
            "T-Score:  -1.4 -1.9\n\n"
            "Left/Right Total Hip:\n"
            "T-Score:  -1.3 -2.1\n\n"
            "IMPRESSION:\n\n"
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of low bone mass in "
            "L1-L4, the left hip, and the right hip.\n")
    ]) == "11/2026- Bone density hip -2.1"
    # a `Not reported` site is skipped (327473's limited-view hip)
    assert build_lab_summary([
        bmd("Exam # 44S244870 - January 19 2026 - BONE DENSITY -\n"
            "FINDINGS:\n\n"
            "Lumbar Spine (L1-L2):\n"
            "T-Score:  -0.5\n\n"
            "Left Femoral Neck:\n"
            "T-Score:  -2.0\n\n"
            "Left Total Hip:\n"
            "T-Score: Not reported\n\n"
            "IMPRESSION:\n\n"
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of low bone mass in "
            "the left femoral neck and normal bone mass in L1-L4.\n")
    ]) == "11/2026- Bone density femur -2"
    # the old dictation layout (15459's report): the indented
    # all-caps head, the single lumbar-spine site, its `WHO
    # CLASSIFICATION` line, and the `Low bone mass (Osteopenia):`
    # boilerplate
    assert build_lab_summary([
        bmd("Exam # 52767936 - November 4 2026 - BONE DENSITY -\n"
            " DEXA\n\n"
            " FINDINGS:\n\n"
            " LUMBAR SPINE (L1-L4):\n\n"
            " BMD: 0.862 g/cm2\n\n"
            " T-Score: -2.7\n\n"
            " Z-Score: -1.5\n\n"
            " WHO CLASSIFICATION: Osteoporosis\n\n"
            " IMPRESSION:\n\n"
            " Osteoporosis: Classification based on World Health "
            "Organization (WHO) criteria.\n\n"
            " RELATED INFORMATION:\n\n"
            " 2.  The International Society for Clinical Densitometry "
            "recommends categorizing the patient according to the "
            "lowest T-score from the total L-spine, total hip, and "
            "femoral neck, utilizing the following World Health "
            "Organization criteria:\n\n"
            " Normal range:   T-score of -1.0 or above\n\n"
            " Low bone mass (Osteopenia):   T-score of less than "
            "-1.0 but greater than -2.5\n\n"
            " Osteoporosis:   T-score of -2.5 or below\n")
    ]) == "11/2026- Bone density lumbar -2.7"
    # the `W/TBS` order name (the same exam, a `Trabecular Bone
    # Score` line on the lumbar site that is not a T-score)
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  Based on World Health Organization (WHO) criteria, "
            "this patient falls within the range of osteoporosis in "
            "L1-L4 and the left hip.",
            lumbar="-2.8", femur="-2.9", hip="-2.8"),
            name="BD - BONE DENSITY W/TBS")
    ]) == "11/2026- Bone density femur -2.9"
    # another exam's report attached to a bone density row names no
    # T-score: nothing (15870's row carries a mammogram report)
    assert build_lab_summary([
        bmd("Exam # 3334984 - September 25 2026 - SCREENING MAMMO, "
            "BIL W/3D TOMOSYNTHESIS -\n\n"
            "FINDINGS:  No breast arterial calcifications (BAC) are "
            "noted.\n\n"
            "IMPRESSION:\n\n"
            "No evidence of malignancy.\n\n"
            "BI-RADS 1 - NEGATIVE.\n")
    ]) == ""
    # ...and it does not stand in for the newest report with a
    # T-score of its own: the older real report is the row (its
    # result date leads)
    assert build_lab_summary([
        bmd("Exam # 3334984 - BONE DENSITY row carrying a mammogram "
            "report.\n\nIMPRESSION:\n\nNo evidence of malignancy.\n\n"
            "BI-RADS 1 - NEGATIVE.\n", result_date="2026-11-04"),
        bmd(bmd_report(
            "1.  This patient falls within the range of low bone "
            "mass in the left femoral neck.", lumbar="-0.5",
            femur="-1.9", hip="-1.4"),
            result_date="2026-09-05", date="2026-08-24"),
    ]) == "09/2026- Bone density femur -1.9"
    # a pending / empty bone density row produces nothing (like the
    # other imaging rows); it does not set the leading date either
    assert build_lab_summary([bmd("")]) == ""
    assert build_lab_summary([
        bmd("", result_date="2026-09-05"),
        ua_labcorp(),
    ]) == "11/2026- UA nl"


def test_bmd_order_and_date():
    # the Bone density token follows the US tokens (rule 9d, after
    # the CT CAC of rule 9a, the mammo of rule 9b and the US of rule
    # 9c and before the CBC of rule 10)
    assert build_lab_summary([
        ct_cac(ct_classic()),
        us(us_report("Unremarkable exam")),
        bmd(bmd_report(
            "1.  This patient falls within the range of low bone "
            "mass in the left femoral neck.", lumbar="-0.6",
            femur="-1.9", hip="-0.8")),
        cbc_quest(),
    ]) == ("11/2026- CAC=24; 75%, US abd nl, Bone density femur "
           "-1.9, RBC 5.4(5.1), Hematocrit 46.8(46)")
    # a bone-density-only patient: the leading date is the row's
    assert build_lab_summary([
        bmd(bmd_report(
            "1.  This patient falls within the range of normal."),
            result_date="2026-09-05", date="2026-08-24")
    ]) == "09/2026- Bone density nl"
    # the newest report with a T-score wins, like the other imaging
    # categories
    assert build_lab_summary([
        bmd(bmd_report("1.  Normal.", lumbar="1.0", femur="-0.5",
                       hip="-0.4"),
            result_date="2026-11-07"),
        bmd(bmd_report("1.  Low bone mass in the left femoral neck.",
                       lumbar="-0.6", femur="-2.8", hip="-2.4"),
            result_date="2026-09-05"),
    ]) == "11/2026- Bone density nl"


# ----------------------------------------------------------------------
# CT chest / head / abdomen
# ----------------------------------------------------------------------

def ct(notes, name="CT CHEST W/O CONTRAST", **kw):
    """A CT scan row: the result JSON is a one-entry array whose
    `notes` field is the radiology report (rule 9e)."""
    return row(name, json.dumps([{"notes": notes}]), **kw)


def ct_report(impression, head="IMPRESSION:"):
    """A CT report: the exam's standard sections, the `IMPRESSION`
    (or `CONCLUSION` / `ASSESSMENT`), and the signed-by / letter tail
    (rule 9e)."""
    return f"""Exam # 44S276666 - November 9 2026 - CHEST WITHOUT CONTRAST -
Exam Performed at SimonMed Northern CA Castro Valley

INDICATION:  Cough.

TECHNIQUE:  Scans were obtained through the thorax without IV contrast.

RADIATION DOSE: CTDI volume 6.67 mGy; total DLP 232.66 mGy-cm.

FINDINGS:

{head}

{impression}
ELECTRONICALLY SIGNED BY : Provider (Trinh, Angela) on

Thank you for your kind referral. If you need further assistance, please contact our Radiologist Hotline at 855-RAD-TALK or 855-723-8255.
----------------------------------------------------------------------
Electronically Signed by: Trinh, Angela
"""


def test_ct():
    # an unremarkable exam is normal (22353's report; the yellow
    # notes' `CT chest nl`)
    assert build_lab_summary([
        ct(ct_report(
            "Unremarkable CT of the chest. No suspicious pulmonary "
            "nodules."))
    ]) == "11/2026- CT chest nl"
    # a normal head CT: the `No ...` negative statements (the `No A,
    # B or C` absent-finding list included) are not findings
    # (20721's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. No acute intracranial finding. No hemorrhage, mass "
            "or large infarct identified."),
            name="CT HEAD W/O CONTRAST")
    ]) == "11/2026- CT head nl"
    # the region label is shortened from the order name (an
    # abdomen-and-pelvis order's label is `abd/pelvic`)
    assert build_lab_summary([
        ct(ct_report("Unremarkable CT of the abdomen and pelvis."),
           name="CT ABDOMEN AND PELVIS W/O CONT")
    ]) == "11/2026- CT abd/pelvic nl"
    assert build_lab_summary([
        ct(ct_report("Unremarkable CT of the abdomen."),
           name="CT ABDOMEN  W & W/O CONTRAST")
    ]) == "11/2026- CT abd nl"
    # several items: the finding items are reported, the negative /
    # `No ...` ones are not (21834's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. Mild left sylvian fissure widening suggesting "
            "localized brain atrophy from a remote event.\n"
            "2. No acute or focal brain parenchymal pathology.\n"
            "3. Maxillary sinus retention cysts larger on the "
            "right."), name="CT HEAD W/O CONTRAST")
    ]) == ("11/2026- CT head: Mild left sylvian fissure widening "
           "suggesting localized brain atrophy from a remote event. "
           "Maxillary sinus retention cysts larger on the right")
    # the `without aneurysm` modifier stays with its finding, and the
    # `in keeping with Fleischner Society guidelines` tail is cut
    # (20612's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. No acute process is identified in the thorax.\n"
            "2. Scattered groundglass and solid nodules are "
            "described, the largest being a groundglass nodule "
            "measuring 9 mm. A successful month follow-up CT chest "
            "without contrast is recommended in keeping with "
            "Fleischner Society guidelines.\n"
            "3. Post surgical change of the ascending aorta without "
            "aneurysm"))
    ]) == ("11/2026- CT chest: Scattered groundglass and solid "
           "nodules are described, the largest being a groundglass "
           "nodule measuring 9 mm. A successful month follow-up CT "
           "chest without contrast is recommended. Post surgical "
           "change of the ascending aorta without aneurysm")
    # a guideline citation mid-sentence truncates the finding, and
    # the `DISCLAIMER` head ends the impression (19851's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. Numerous new bilateral pulmonary micronodules "
            "measuring less than 3 mm; 2017 ACR Fleischner Society "
            "recommendations (MacMahon, et al. Radiology 2017; 284 "
            "(1): 228-43) suggest the following: For patients with "
            "low risk of lung cancer, no need for further follow-up. "
            "If unchanged, no further follow-up is necessary.\n"
            "2. A stable nodule in the anterior mediastinum is "
            "probably a benign lymph node or possibly a small "
            "thymoma.\n"
            "3. No other significant findings.\n"
            "DISCLAIMER: AI lung nodule detection was utilized on "
            "this study."))
    ]) == ("11/2026- CT chest: Numerous new bilateral pulmonary "
           "micronodules measuring less than 3 mm. A stable nodule "
           "in the anterior mediastinum is probably a benign lymph "
           "node or possibly a small thymoma")
    # the Fleischner / ACR-White-Paper citations and their
    # recommendation text, the LDCT-screening counseling block, and
    # the `advised to consult` line are not findings (22323's
    # report)
    assert build_lab_summary([
        ct(ct_report(
            "1. No nodules requiring follow-up per Fleischner "
            "Society recommendations.\n"
            "2. Right lower paratracheal lymph node (4R) measuring "
            "1.0 cm in short axis. Per ACR White Paper recommendations "
            "(Munden, et al. J Am Coll Radiol 2018;15(8):1087-1096): "
            "No further evaluation required.\n"
            "3. Mild centrilobular emphysema. Pulmonary emphysema on "
            "CT is an independent risk factor for lung cancer. "
            "Consider enrollment in a low-dose CT (LDCT) lung cancer "
            "screening program if the patient meets eligibility "
            "criteria; today's CT may serve as a baseline for future "
            "screening. Note: Recommendation applies unless the "
            "patient has a history of lung cancer.\n"
            "4. Incidental coronary artery calcification is present, "
            "qualitatively assessed as mild. The patient is advised "
            "to consult with their primary care physician for a "
            "comprehensive cardiovascular risk assessment."))
    ]) == ("11/2026- CT chest: Right lower paratracheal lymph node "
           "(4R) measuring 1.0 cm in short axis. Mild centrilobular "
           "emphysema. Incidental coronary artery calcification is "
           "present, qualitatively assessed as mild")
    # the `FLEISCHNER SOCIETY FOLLOW-UP GUIDELINES` head and its
    # nodule-size table end the impression; the signature-name line
    # and the `as per Fleischner's guidelines` tail are not findings
    # (22068's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. Multiple small ground glass nodules measuring 4-7 mm "
            "in both upper lobes. Follow-up after 3-6 months is "
            "suggested as per Fleischner's guidelines.\n"
            "2. Other chronic and ancillary findings as described "
            "above.\n"
            "FLEISCHNER SOCIETY FOLLOW-UP GUIDELINES FOR NEWLY "
            "DETECTED INDETERMINATE NODULES\n"
            "Solid nodules\n"
            "Single solid nodule less than6 mm (less than100 mm3)\n"
            "Low-risk patients: No routine follow-up required.\n"
            "ZINN WILLIAM"))
    ]) == ("11/2026- CT chest: Multiple small ground glass nodules "
           "measuring 4-7 mm in both upper lobes. Follow-up after "
           "3-6 months is suggested")
    # the template's empty all-caps header line (`MIPS:`) and the
    # `No follow-up ...` tail are not findings (21302's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. No obvious cause for hematuria is identified.\n"
            "2. A 7 mm nodule is noted in the left adrenal gland.  No "
            "follow-up is required.\n"
            "3. Mild dilatation of the left pelvicalyceal system.\n"
            "4. Enlarged uterus.\n"
            "5. Mild thickening of the urinary bladder wall.\n"
            "6. Small fat-containing umbilical hernia.\n"
            "7. Plate atelectasis and ground-glass haziness in both "
            "lung bases.\n"
            "8. Chronic and ancillary finding as described.\n"
            "MIPS:\n"
            "No follow-up imaging recommended of adrenal lesion as "
            "incidental adrenal lesions without significant features "
            "are likely benign."),
           name="CT ABDOMEN AND PELVIS W/O CONT")
    ]) == ("11/2026- CT abd/pelvic: A 7 mm nodule is noted in the left "
           "adrenal gland. Mild dilatation of the left pelvicalyceal "
           "system. Enlarged uterus. Mild thickening of the urinary "
           "bladder wall. Small fat-containing umbilical hernia. Plate "
           "atelectasis and ground-glass haziness in both lung bases")
    # the LUNG-RADS category table trailing the `Recommended follow-up`
    # head (and the repeated exam-head block) is not a finding
    # (356460's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. Bilateral upper lobe interstitial thickening and "
            "reticular opacities, predominantly on the right.\n"
            "2. Three left upper lobe fibronodular or solid nodular "
            "densities, measuring up to 7 mm.\n"
            "LUNG RADS:  LUNG-RADS 3 (probably benign).  Recommend "
            "follow-up low-dose CT chest in 6 months.\n"
            "Recommended follow-up\n"
            "Category 0:\n"
            "Comparison with prior studies before assignment of "
            "Lung-RADS classification.\n"
            "Category 3:\n"
            "6-month follow-up with LDCT.\n"
            "Category 4B and 4X:\n"
            "Chest CT with or without contrast, as appropriate.\n"
            "(version 1.1 edition)\n"
            "CLINICAL INDICATION:  Encounter for screening.\n"
            "CONTRAST USED:  None.\n"
            "Multiplanar reconstructions were obtained.\n"
            "Highest CTDI: 15.24 mGy."))
    ]) == ("11/2026- CT chest: Bilateral upper lobe interstitial "
           "thickening and reticular opacities, predominantly on the "
           "right. Three left upper lobe fibronodular or solid nodular "
           "densities, measuring up to 7 mm. LUNG RADS: LUNG-RADS 3 "
           "(probably benign). Recommend follow-up low-dose CT chest "
           "in 6 months")
    # the cross-reference tail pointing back at the findings section
    # is cut from a finding (362844's / 378301's reports), and the
    # bare `Please see above` line is not a finding (370846's report)
    assert build_lab_summary([
        ct(ct_report(
            "1. Atherosclerosis, coronary artery disease with stents, "
            "and additional findings as above\n"
            "2. Trace atherosclerosis and additional findings as "
            "above\n"
            "3. Please see above for other findings/details."))
    ]) == ("11/2026- CT chest: Atherosclerosis, coronary artery "
           "disease with stents. Trace atherosclerosis")
    # the radiologist's signature lines are not findings (21834's
    # report)
    report = ct_report(
        "1. Mild left sylvian fissure widening suggesting localized "
        "brain atrophy from a remote event.\n"
        "2. No acute or focal brain parenchymal pathology.\n"
        "3. Maxillary sinus retention cysts larger on the right.")
    report = report.replace(
        "ELECTRONICALLY SIGNED BY : Provider (Trinh, Angela) on",
        "David Lefkowitz, M.D.\nDiplomate of American Board of "
        "Radiology\nCAQ in Neuroradiology\nELECTRONICALLY SIGNED BY : "
        "Provider (Lefkowitz, David) on")
    assert build_lab_summary(
        [ct(report, name="CT HEAD W/O CONTRAST")]) == (
        "11/2026- CT head: Mild left sylvian fissure widening "
        "suggesting localized brain atrophy from a remote event. "
        "Maxillary sinus retention cysts larger on the right")
    # a notes field that carries a second report: the second
    # report's `COMPUTED TOMOGRAPHY OF ...` / `HISTORY:` / `FINDINGS:`
    # heads end the first report's `IMPRESSION` (13563's report)
    two_reports = ct_report(
        "1. Destructive expansile lytic lesion of the right 8th rib.\n"
        "2. Few millimeter solid nodules in the left lower lobe.") + (
        "COMPUTED TOMOGRAPHY OF THE CHEST WITH CONTRAST.\n"
        "HISTORY:  Weight loss.\n"
        "FINDINGS:\n"
        "Lungs and pleura: Nodules.\n"
        "IMPRESSION:\n"
        "1.  Nodules.")
    assert build_lab_summary([ct(two_reports)]) == (
        "11/2026- CT chest: Destructive expansile lytic lesion of "
        "the right 8th rib. Few millimeter solid nodules in the left "
        "lower lobe")
    # a report without an `IMPRESSION` section (or with no usable
    # impression sentence) produces nothing
    assert build_lab_summary([
        ct("FINDINGS:\n\nThe lungs are clear.")
    ]) == ""
    assert build_lab_summary([
        ct(ct_report("Electronically signed by someone"))
    ]) == ""


def test_ct_order_and_date():
    # the CT token follows the BMD token (rule 9e, after the CT CAC
    # of rule 9a, the mammo of rule 9b, the US of rule 9c and the
    # BMD of rule 9d and before the CBC of rule 10)
    assert build_lab_summary([
        ct_cac(ct_classic()),
        bmd(bmd_report("1.  Normal.")),
        ct(ct_report("Unremarkable CT of the chest.")),
        cbc_quest(),
    ]) == ("11/2026- CAC=24; 75%, Bone density nl, CT chest nl, "
           "RBC 5.4(5.1), Hematocrit 46.8(46)")
    # per label the newest row wins: an older abnormal chest CT must
    # not override a newer normal one
    assert build_lab_summary([
        ct(ct_report("Unremarkable CT of the chest."),
           result_date="2026-11-07"),
        ct(ct_report("1. Multiple pulmonary nodules up to 6 mm."),
           result_date="2026-10-01"),
    ]) == "11/2026- CT chest nl"
    # a chest row and an abdomen row report both regions, chest first
    assert build_lab_summary([
        ct(ct_report("Unremarkable CT of the abdomen and pelvis."),
           name="CT ABDOMEN AND PELVIS W/O CONT",
           result_date="2026-11-07"),
        ct(ct_report("1. Multiple pulmonary nodules up to 6.3 mm."),
           result_date="2026-11-05"),
    ]) == ("11/2026- CT chest: Multiple pulmonary nodules up to 6.3 "
           "mm, CT abd/pelvic nl")
    # a report without a usable `IMPRESSION` does not stand in for
    # the region's newest result, like a pending one
    assert build_lab_summary([
        ct("FINDINGS:\n\nThe lungs are clear.",
           result_date="2026-11-07"),
        ct(ct_report("1. Multiple pulmonary nodules up to 6 mm."),
           result_date="2026-10-01"),
    ]) == "10/2026- CT chest: Multiple pulmonary nodules up to 6 mm"
    # a CT row with no result is ignored, like the other imaging rows
    assert build_lab_summary([
        row("CT HEAD W/O CONTRAST", result_date="2026-11-07"),
    ]) == ""


# ----------------------------------------------------------------------
# Vitamin D
# ----------------------------------------------------------------------

def test_vitd():
    # always emitted, normal or abnormal
    assert build_lab_summary([
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "32", "N")))
    ]) == "11/2026- VitD 32"
    assert build_lab_summary([
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "18", "L")))
    ]) == "11/2026- VitD 18"
    # LabCorp's name for the same test; the value renders as an
    # integer (19868's 42.2 -> VitD 42)
    assert build_lab_summary([
        row("Vitamin D, 25-Hydroxy", result(("25-Hydroxy Vitamin D", "41", "")))
    ]) == "11/2026- VitD 41"
    assert build_lab_summary([
        row("Vitamin D, 25-Hydroxy",
            result(("Vitamin D, 25-Hydroxy", "42.2", "", "20.0-100.0")))
    ]) == "11/2026- VitD 42"
    # an unparseable value is written out raw
    assert build_lab_summary([
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "pending", "N")))
    ]) == "11/2026- VitD pending"


# ----------------------------------------------------------------------
# PTH (intact parathyroid hormone)
# ----------------------------------------------------------------------

def pth_quest(value="30", flag="N", rng="16-77", **kw):
    return row(
        "PTH, INTACT WITHOUT$CALCIUM",
        result(("PARATHYROID HORMONE,$INTACT", value, flag, rng)),
        **kw,
    )


def test_pth():
    # normal (Quest layout, 19798's 30 in 16-77) -> PTH nl
    assert build_lab_summary([pth_quest()]) == "11/2026- PTH nl"
    # LabCorp's layout leaves the flag empty on normal items (21430's
    # 29 in 15-65) -> PTH nl too
    assert build_lab_summary([
        row("PTH, Intact", result(("PTH, Intact", "29", "", "15-65")))
    ]) == "11/2026- PTH nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("pth, intact", result(("PTH, Intact", "29", "", "15-65")))
    ]) == "11/2026- PTH nl"
    # abnormal high, range 16-77 -> PTH {val}(upper limit)
    assert build_lab_summary([pth_quest(value="120", flag="H")]) == \
        "11/2026- PTH 120(77)"
    # abnormal low -> lower limit
    assert build_lab_summary([pth_quest(value="12", flag="L")]) == \
        "11/2026- PTH 12(16)"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([pth_quest(flag="H", rng="")]) == \
        "11/2026- PTH 30"


# ----------------------------------------------------------------------
# Free (ionized) calcium
# ----------------------------------------------------------------------

def test_ica():
    # normal (LabCorp's layout, 19871's 5.1 in 4.5-5.6) -> Free
    # Calcium nl (the yellow notes' label, e.g. 17700's `Free
    # Calcium nml`)
    assert build_lab_summary([
        row("Calcium, Ionized, Serum",
            result(("Calcium, Ionized, Serum", "5.1", "", "4.5-5.6")))
    ]) == "11/2026- Free Calcium nl"
    # Quest's layout (17685's 5.1, range 4.7-5.5, flag N)
    assert build_lab_summary([
        row("CALCIUM, IONIZED",
            result(("CALCIUM, IONIZED", "5.1", "N", "4.7-5.5")))
    ]) == "11/2026- Free Calcium nl"
    # abnormal low -> lower limit (15787's 4.3 in 4.5-5.6)
    assert build_lab_summary([
        row("Calcium, Ionized, Serum",
            result(("Calcium, Ionized, Serum", "4.3", "L", "4.5-5.6")))
    ]) == "11/2026- Free Calcium 4.3(4.5)"
    # abnormal high -> upper limit
    assert build_lab_summary([
        row("CALCIUM, IONIZED",
            result(("CALCIUM, IONIZED", "5.9", "H", "4.7-5.5")))
    ]) == "11/2026- Free Calcium 5.9(5.5)"
    # next to a PTH row: the token follows PTH, in the fixed token
    # order (the notes order the tests ...PTH/Free calcium/PO4/Mg...)
    assert build_lab_summary([
        pth_quest(),
        row("Calcium, Ionized, Serum",
            result(("Calcium, Ionized, Serum", "5.1", "", "4.5-5.6"))),
    ]) == "11/2026- PTH nl, Free Calcium nl"


# ----------------------------------------------------------------------
# Magnesium
# ----------------------------------------------------------------------

def test_mg():
    # normal (17159's 2.0 in 1.6-2.3) -> Mg nl
    assert build_lab_summary([
        row("magnesium", result(("Magnesium, Serum", "2.0", "", "1.6-2.3")))
    ]) == "11/2026- Mg nl"
    # abnormal low -> Mg {val}(lower limit)
    assert build_lab_summary([
        row("magnesium", result(("Magnesium, Serum", "1.5", "L", "1.6-2.3")))
    ]) == "11/2026- Mg 1.5(1.6)"
    # abnormal high -> upper limit
    assert build_lab_summary([
        row("magnesium", result(("Magnesium, Serum", "2.5", "H", "1.6-2.3")))
    ]) == "11/2026- Mg 2.5(2.3)"
    # red-cell magnesium is a different test (its own category,
    # test_mg_rbc): the row produces no serum-magnesium token
    assert build_lab_summary([
        row("MAGNESIUM, RBC", result(("Magnesium, RBC", "5.1", "")))
    ]) == "11/2026- Mg RBC nl"


def test_mg_rbc():
    # normal (19808's 6.2 in Quest's 4.0-6.4) -> Mg RBC nl
    assert build_lab_summary([
        row("MAGNESIUM, RBC",
            result(("MAGNESIUM, RBC", "6.2", "", "4.0-6.4")))
    ]) == "11/2026- Mg RBC nl"
    # LabCorp's layout (22104's 5.0, range 3.7-7.0)
    assert build_lab_summary([
        row("Magnesium, RBC",
            result(("Magnesium, RBC", "5.0", "", "3.7-7.0")))
    ]) == "11/2026- Mg RBC nl"
    # abnormal high -> upper limit (13431's yellow note writes it
    # `Mg RBC 7.8 (nml 6.4)`)
    assert build_lab_summary([
        row("MAGNESIUM, RBC",
            result(("MAGNESIUM, RBC", "7.8", "H", "4.0-6.4")))
    ]) == "11/2026- Mg RBC 7.8(6.4)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("MAGNESIUM, RBC",
            result(("MAGNESIUM, RBC", "3.5", "L", "4.0-6.4")))
    ]) == "11/2026- Mg RBC 3.5(4)"
    # both ordered: separate categories, each reporting its own row
    # (the serum token first, in the fixed token order)
    assert build_lab_summary([
        row("magnesium", result(("Magnesium, Serum", "1.5", "L", "1.6-2.3"))),
        row("MAGNESIUM, RBC",
            result(("MAGNESIUM, RBC", "6.2", "", "4.0-6.4"))),
    ]) == "11/2026- Mg 1.5(1.6), Mg RBC nl"


# ----------------------------------------------------------------------
# Uric acid
# ----------------------------------------------------------------------

def test_uric():
    # normal -> uric acid {val}
    assert build_lab_summary([
        row("Uric Acid, Serum", result(("Uric Acid, Serum", "6.8", "")))
    ]) == "11/2026- uric acid 6.8"
    # the value's trailing zeros are stripped
    assert build_lab_summary([
        row("Uric Acid, Serum", result(("Uric Acid, Serum", "3.0", "")))
    ]) == "11/2026- uric acid 3"
    assert build_lab_summary([
        row("URIC ACID", result(("URIC ACID", "5.9", "N")))
    ]) == "11/2026- uric acid 5.9"
    # abnormal -> uric acid {val}({bound})
    assert build_lab_summary([
        row("Uric Acid, Serum",
            result(("Uric Acid, Serum", "8.1", "H", "2.4-7.0")))
    ]) == "11/2026- uric acid 8.1(7)"
    # abnormal, no parsable range -> plain value
    assert build_lab_summary([
        row("Uric Acid, Serum", result(("Uric Acid, Serum", "8.1", "H")))
    ]) == "11/2026- uric acid 8.1"
    # low flag -> lower limit in parentheses
    assert build_lab_summary([
        row("Uric Acid, Serum",
            result(("Uric Acid, Serum", "2.1", "L", "2.4-7.0")))
    ]) == "11/2026- uric acid 2.1(2.4)"


# ----------------------------------------------------------------------
# PSA
# ----------------------------------------------------------------------

def psa_quest(value="1.40", flag="N", rng="< OR = 4.00", **kw):
    return row(
        "PSA, TOTAL",
        result(("PSA, TOTAL", value, flag, rng)),
        **kw,
    )


def test_psa():
    # always emitted, normal or abnormal; trailing zeros stripped
    # (19798's 1.40 -> PSA 1.4)
    assert build_lab_summary([psa_quest()]) == "11/2026- PSA 1.4"
    # LabCorp's layout (22465's 2.2, range 0.0-4.0, empty flag = normal)
    assert build_lab_summary([
        row("PSA", result(("Prostate Specific Ag, Serum", "2.2", "", "0.0-4.0")))
    ]) == "11/2026- PSA 2.2"
    # name matching is case-insensitive
    assert build_lab_summary([row("psa", psa_quest()["result"])]) == \
        "11/2026- PSA 1.4"
    # abnormal high is written out too
    assert build_lab_summary([psa_quest(value="8.5", flag="H")]) == \
        "11/2026- PSA 8.5"
    # unparseable value is written out raw
    assert build_lab_summary([psa_quest(value="pending")]) == \
        "11/2026- PSA pending"
    # the total is rounded to one decimal, trailing zeros stripped
    # (the notes write 1.4 / 1 / 0.6 for 1.38 / 1.01 / 0.55)
    assert build_lab_summary([psa_quest(value="1.38")]) == \
        "11/2026- PSA 1.4"
    assert build_lab_summary([psa_quest(value="1.01")]) == \
        "11/2026- PSA 1"
    assert build_lab_summary([psa_quest(value="0.55")]) == \
        "11/2026- PSA 0.6"
    # the LabCorp reflex orders: the total PSA item is selected by
    # name, not position
    assert build_lab_summary([
        row("PSA total (reflex to free)",
            result(("Prostate Specific Ag, Serum", "2.7", "", "0.0-4.0"),
                   ("Reflex Criteria", "", "")))
    ]) == "11/2026- PSA 2.7"
    assert build_lab_summary([
        row("PSA total+% free", result(
            ("Prostate Specific Ag, Serum", "3.8", "", "0.0-4.0"),
            ("PSA, Free", "0.65", "", "N/A"),
            ("% Free PSA", "17.1", "", "")))
    ]) == "11/2026- PSA 3.8"
    # when the reflex fires, the free-PSA items are listed *before*
    # the total (22013's 5.6 H: free 0.88, 15.7% free); the total
    # is picked by name, and the borderline total + low free% gain
    # the free-% token
    assert build_lab_summary([
        row("PSA total (reflex to free)",
            result(("PSA, Free", "0.88", "", "N/A"),
                   ("% Free PSA", "15.7", "", ""),
                   ("Prostate Specific Ag, Serum", "5.6", "H", "0.0-4.0"),
                   ("Reflex Criteria", "", "")))
    ]) == "11/2026- PSA 5.6, PSA%free 16"
    # borderline total but a not-low free%: no free-% token
    # (21927's 6.5 H, 25.8% free)
    assert build_lab_summary([
        row("PSA total (reflex to free)",
            result(("PSA, Free", "1.68", "", "N/A"),
                   ("% Free PSA", "25.8", "", ""),
                   ("Prostate Specific Ag, Serum", "6.5", "H", "0.0-4.0"),
                   ("Reflex Criteria", "", "")))
    ]) == "11/2026- PSA 6.5"
    # total at/above 10 is beyond the gray zone: no free-% token
    assert build_lab_summary([
        row("PSA total (reflex to free)",
            result(("% Free PSA", "9.4", "", ""),
                   ("Prostate Specific Ag, Serum", "12.3", "H", "0.0-4.0")))
    ]) == "11/2026- PSA 12.3"
    # a non-numeric free%: only the total
    assert build_lab_summary([
        row("PSA total (reflex to free)",
            result(("% Free PSA", "pending", "", ""),
                   ("Prostate Specific Ag, Serum", "5.6", "H", "0.0-4.0")))
    ]) == "11/2026- PSA 5.6"


# ----------------------------------------------------------------------
# HAV total antibody
# ----------------------------------------------------------------------

def test_hav():
    # positive (Quest layout, 20831's value; Quest flags it A) -> Ab+
    assert build_lab_summary([
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A")))
    ]) == "11/2026- HAV Ab+"
    # positive (LabCorp layout) -> Ab+ too
    assert build_lab_summary([
        row("Hep A Ab, Total",
            result(("Hep A Ab, Total", "Positive", "A")))
    ]) == "11/2026- HAV Ab+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hep a total ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A")))
    ]) == "11/2026- HAV Ab+"
    # negative -> nothing (Quest's NON-REACTIVE, LabCorp's Negative)
    assert build_lab_summary([
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "NON-REACTIVE", "N")))
    ]) == ""
    assert build_lab_summary([
        row("Hep A Ab, Total", result(("Hep A Ab, Total", "Negative", "")))
    ]) == ""
    # HAV IgM (acute infection) is a different test: rule 25a's own
    # category, not part of this one
    assert build_lab_summary([
        row("HAV IgM", result(("HEPATITIS A IGM", "NON-REACTIVE", "N")))
    ]) == ""
    assert build_lab_summary([
        row("Hep A Ab, IgM", result(("Hep A Ab, IgM", "Positive", "A")))
    ]) == "11/2026- HAV IgM+"


# ----------------------------------------------------------------------
# HAV IgM
# ----------------------------------------------------------------------

def test_hav_igm():
    # negative (Quest's NON-REACTIVE, 22501's row) -> nothing: the
    # yellow notes omit a negative HAV IgM
    assert build_lab_summary([
        row("HAV IgM", result(("HEPATITIS A IGM", "NON-REACTIVE", "N")))
    ]) == ""
    # negative (LabCorp's Negative, 15372's row) -> nothing too
    assert build_lab_summary([
        row("Hep A Ab, IgM", result(("Hep A Ab, IgM", "Negative", "")))
    ]) == ""
    # positive (Quest layout) -> HAV IgM+
    assert build_lab_summary([
        row("HAV IgM", result(("HEPATITIS A IGM", "REACTIVE", "A")))
    ]) == "11/2026- HAV IgM+"
    # positive (LabCorp layout) -> HAV IgM+ too
    assert build_lab_summary([
        row("Hep A Ab, IgM", result(("Hep A Ab, IgM", "Positive", "A")))
    ]) == "11/2026- HAV IgM+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hav igm", result(("HEPATITIS A IGM", "REACTIVE", "A")))
    ]) == "11/2026- HAV IgM+"
    # a pending / empty value produces nothing
    assert build_lab_summary([
        row("HAV IgM", result(("HEPATITIS A IGM", "", "")))
    ]) == ""
    # a positive HAV IgM rides alongside the HAV total-Ab token
    assert build_lab_summary([
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A"))),
        row("HAV IgM", result(("HEPATITIS A IGM", "REACTIVE", "A"))),
    ]) == "11/2026- HAV Ab+, HAV IgM+"


# ----------------------------------------------------------------------
# Measles IgG
# ----------------------------------------------------------------------

def test_measles():
    # immune (Quest layout, 21721's value; Quest flags it N) -> Ab+
    assert build_lab_summary([
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", "204.00", "N")))
    ]) == "11/2026- measles Ab+"
    # immune (LabCorp layout) -> Ab+ too
    assert build_lab_summary([
        row("Measles _ Rubeola, IgG",
            result(("Rubeola Ab, IgG", "22.5", "")))
    ]) == "11/2026- measles Ab+"
    # Quest's capped value (>300.00, above the assay's upper limit) is
    # still immune -> Ab+ (20831's value; Quest flags it N)
    assert build_lab_summary([
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", ">300.00", "N")))
    ]) == "11/2026- measles Ab+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("measle _ rubeola _ igg",
            result(("MEASLES ANTIBODY (IGG)", "204.00", "N")))
    ]) == "11/2026- measles Ab+"
    # non-immune (LabCorp's "<13.5", flag L; the number decides) -> nothing
    assert build_lab_summary([
        row("Measles _ Rubeola, IgG",
            result(("Rubeola Ab, IgG", "<13.5", "L")))
    ]) == ""
    # non-immune (Quest's "<13.50", flag L) -> nothing too
    assert build_lab_summary([
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", "<13.50", "L")))
    ]) == ""
    # equivocal band (13.5-16.49) -> nothing
    assert build_lab_summary([
        row("Measles _ Rubeola, IgG",
            result(("Rubeola Ab, IgG", "15.0", "")))
    ]) == ""
    # other TSH-style orders are not part of this category
    assert build_lab_summary([
        row("Measles IgM", result(("Measles IgM", "0.5", "")))
    ]) == ""


# ----------------------------------------------------------------------
# MMR panel (mumps / rubella) and varicella IgG
# ----------------------------------------------------------------------

def mmr_panel(rubella=("RUBELLA ANTIBODY (IGG)", "5.87", "N"),
              measles=("MEASLES ANTIBODY (IGG)", "200.00", "N"),
              mumps=("MUMPS VIRUS$ANTIBODY (IGG)", "157.00", "N")):
    """Quest's MMR panel in its report item order (rubella, measles,
    mumps)."""
    return row("MMR (IGG) PANEL (MEASLES, MUMPS, RUBELLA)",
               result(rubella, measles, mumps))


def test_mmr_panel():
    # fully immune panel (22337-style): the tokens come out in the
    # measles/mumps/rubella order, not the result's report order
    assert build_lab_summary([mmr_panel()]) == \
        "11/2026- measles Ab+, mumps Ab+, rubella Ab+"
    # the capped values (>300.00, above the assay's upper limit) are
    # still immune
    assert build_lab_summary([
        mmr_panel(measles=("MEASLES ANTIBODY (IGG)", ">300.00", "N"),
                  mumps=("MUMPS VIRUS$ANTIBODY (IGG)", ">300.00", "N"))
    ]) == "11/2026- measles Ab+, mumps Ab+, rubella Ab+"
    # non-immune measles (<13.50), equivocal rubella (0.95 in the
    # 0.90-0.99 band) and non-immune mumps (<9.00) -> nothing
    assert build_lab_summary([
        mmr_panel(rubella=("RUBELLA ANTIBODY (IGG)", "0.95", "L"),
                  measles=("MEASLES ANTIBODY (IGG)", "<13.50", "L"),
                  mumps=("MUMPS VIRUS$ANTIBODY (IGG)", "<9.00", "L"))
    ]) == ""
    # mumps equivocal band (9.00-10.99) -> nothing on its own
    assert build_lab_summary([
        mmr_panel(rubella=("RUBELLA ANTIBODY (IGG)", "<0.90", "L"),
                  measles=("MEASLES ANTIBODY (IGG)", "<13.50", "L"),
                  mumps=("MUMPS VIRUS$ANTIBODY (IGG)", "10.50", "N"))
    ]) == ""
    # mumps just above the equivocal band (12.60, the smallest N value
    # in the database) -> the mumps token alone
    assert build_lab_summary([
        mmr_panel(rubella=("RUBELLA ANTIBODY (IGG)", "<0.90", "L"),
                  measles=("MEASLES ANTIBODY (IGG)", "<13.50", "L"),
                  mumps=("MUMPS VIRUS$ANTIBODY (IGG)", "12.60", "N"))
    ]) == "11/2026- mumps Ab+"
    # rubella immune (index >= 1.00) -> the rubella token alone
    assert build_lab_summary([
        mmr_panel(rubella=("RUBELLA ANTIBODY (IGG)", "1.04", "N"),
                  measles=("MEASLES ANTIBODY (IGG)", "<13.50", "L"),
                  mumps=("MUMPS VIRUS$ANTIBODY (IGG)", "<9.00", "L"))
    ]) == "11/2026- rubella Ab+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("mmr (igg) panel (measles, mumps, rubella)",
            result(("RUBELLA ANTIBODY (IGG)", "5.87", "N"),
                   ("MEASLES ANTIBODY (IGG)", "204.00", "N"),
                   ("MUMPS VIRUS$ANTIBODY (IGG)", "157.00", "N")))
    ]) == "11/2026- measles Ab+, mumps Ab+, rubella Ab+"
    # LabCorp's `MMR` order (LabCorp item names on the same panel,
    # no flags sent) -> the same tokens
    assert build_lab_summary([
        row("MMR",
            result(("Rubella Antibodies, IgG", "2.26", ""),
                   ("Rubeola Ab, IgG", "114.0", ""),
                   ("Mumps Abs, IgG", "64.5", "")))
    ]) == "11/2026- measles Ab+, mumps Ab+, rubella Ab+"
    # LabCorp's non-immune measles ("<13.5", flag L) with immune
    # mumps / rubella (22593's values) -> the two positive tokens
    assert build_lab_summary([
        row("MMR",
            result(("Rubella Antibodies, IgG", "6.01", ""),
                   ("Rubeola Ab, IgG", "<13.5", "L"),
                   ("Mumps Abs, IgG", "33.9", "")))
    ]) == "11/2026- mumps Ab+, rubella Ab+"


def test_rubella():
    # immune (LabCorp's layout: index 1.12, range `Immune >0.99`,
    # LabCorp sends no flag) -> Ab+
    assert build_lab_summary([
        row("Rubella Antibodies, IgG",
            result(("Rubella Antibodies, IgG", "1.12", "")))
    ]) == "11/2026- rubella Ab+"
    # immune (the in-house order, the Quest item layout) -> Ab+ too
    assert build_lab_summary([
        row("RUBELLA IMMUNE STATUS",
            result(("RUBELLA ANTIBODY (IGG)", "4.99", "N")))
    ]) == "11/2026- rubella Ab+"
    # non-immune (LabCorp's "<0.90", flag L) -> nothing
    assert build_lab_summary([
        row("Rubella Antibodies, IgG",
            result(("Rubella Antibodies, IgG", "<0.90", "L")))
    ]) == ""
    # equivocal band (0.90-0.99) -> nothing
    assert build_lab_summary([
        row("RUBELLA IMMUNE STATUS",
            result(("RUBELLA ANTIBODY (IGG)", "0.95", "L")))
    ]) == ""
    # the other vaccine orders are separate categories
    assert build_lab_summary([
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", "204.00", "N")))
    ]) == "11/2026- measles Ab+"


def test_varicella():
    # positive (Quest's current S/CO layout, units S/CO) -> Ab+
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)", "9.48",
                    "N", "", "", "S/CO")))
    ]) == "11/2026- varicella Ab+"
    # negative (Quest's "<1.00", flag L: capped below the 1.00 cutoff)
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)", "<1.00",
                    "L", "", "", "S/CO")))
    ]) == ""
    # positive text (the older Quest layout's item, range `Non
    # Reactive`) -> Ab+
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("Varicella Zoster IgG", "Reactive", "",
                    "Non Reactive")))
    ]) == "11/2026- varicella Ab+"
    # negative text (LabCorp's layout) -> nothing
    assert build_lab_summary([
        row("Varicella-Zoster V Ab, IgG",
            result(("Varicella Zoster IgG", "Non Reactive", "")))
    ]) == ""
    # the IgG/IgM combo order: the IgG item decides, the IgM item (the
    # acute-infection marker) is ignored
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS ANTIBODIES (IGG,IGM)",
            result(("VARICELLA ZOSTER VIRUS ANTIBODY (IGG)", "9.48",
                    "N", "", "", "S/CO"),
                   ("VARICELLA ZOSTER VIRUS ANTIBODY (IGM)", "0.30",
                    "N")))
    ]) == "11/2026- varicella Ab+"
    # a combo result carrying no IgG item -> nothing
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS ANTIBODIES (IGG,IGM)",
            result(("VARICELLA ZOSTER VIRUS ANTIBODY (IGM)", "0.30",
                    "N")))
    ]) == ""
    # the index layout: positive (>= 165.00), the equivocal band
    # (135.00-164.99) and negative (< 135.00) values
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)", "167.00",
                    "N", "", "", "index")))
    ]) == "11/2026- varicella Ab+"
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)", "150.00",
                    "N", "", "", "index")))
    ]) == ""
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)", "100.00",
                    "L", "", "", "index")))
    ]) == ""
    # pending / empty value -> nothing
    assert build_lab_summary([
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("Varicella Zoster IgG", "", "")))
    ]) == ""
    # combined with the MMR panel: the vaccine tokens come out in the
    # measles/mumps/rubella/varicella order
    assert build_lab_summary([
        mmr_panel(),
        row("VARICELLA ZOSTER VIRUS$ANTIBODY (IGG)",
            result(("Varicella Zoster IgG", "Reactive", ""))),
    ]) == "11/2026- measles Ab+, mumps Ab+, rubella Ab+, varicella Ab+"


# ----------------------------------------------------------------------
# STD markers (HBV/HCV/HIV/RPR)
# ----------------------------------------------------------------------

def hep_trio(**hcv_kw):
    """The three hep B/C rows, all negative/normal."""
    return [
        row("Hep C Ab RFX to Quant PCR",
            result(("Interpretation:", "", ""), ("HCV Ab", "Non Reactive", "")),
            **hcv_kw),
        row("Hep B surface Ag", result(("HBsAg Screen", "Negative", "")),
            **hcv_kw),
        row("Hep B Surface Ab",
            result(("Hep B Surface Ab, Qual", "Non Reactive", "")),
            **hcv_kw),
    ]


def hiv_quest(**kw):
    """Quest's 4th-gen HIV screen, non-reactive (22545's layout)."""
    return row("HIV 1/2 Ag/Ab, 4th generation", result(
        ("HIV AG/AB, 4TH GEN", "NON-REACTIVE", "N"),
        ("HIV FINAL INTERPRETATION", "HIV NEGATIVE", "N")),
        **kw)


def hiv_reactive(**kw):
    """Quest's REACTIVE Ag/Ab screen (flag N!) whose reflex work-up
    ends HIV NEGATIVE (22487's layout)."""
    return row("HIV 1/2 Ag/Ab, 4th generation", result(
        ("HIV AG/AB, 4TH GEN", "REACTIVE", "N"),
        ("HIV 1 ANTIBODY", "NEGATIVE", "N"),
        ("HIV 2 ANTIBODY", "NEGATIVE", "N"),
        ("HIV FINAL INTERPRETATION", "HIV NEGATIVE", "N"),
        ("HIV 1 RNA, QL RT PCR", "NOT DETECTED", "N"),
        ("HIV 2 RNA, QL RT PCR", "NOT DETECTED", "N")),
        **kw)


def hiv_labcorp(**kw):
    return row("HIV",
               result(("HIV Screen 4th Generation wRfx", "Non Reactive",
                       "")),
               **kw)


def rpr_quest(**kw):
    return row("RPR (Dx) w/ Confirmatory", result(
        ("RPR (DX) W/REFL TITER AND$CONFIRMATORY TESTING",
         "NON-REACTIVE", "N")),
        **kw)


def rpr_labcorp(**kw):
    return row("RPR", result(("RPR", "Non Reactive", "")), **kw)


def test_std():
    # hep trio only -> HBV/HCV neg; the non-reactive surface Ab row
    # reports its own HBV Ab neg token (rule 24c)
    assert build_lab_summary(hep_trio()) == "11/2026- HBV/HCV neg, HBV Ab neg"
    # Quest's name for the hep C test counts too
    trio = hep_trio()
    trio[0] = row(
        "Hep C Ab reflex to RNA, QN, PCR",
        result(("Interpretation:", "", ""), ("HCV Ab", "Non-Reactive", "N")),
    )
    assert build_lab_summary(trio) == "11/2026- HBV/HCV neg, HBV Ab neg"
    # Quest's long HCV Ab screen order name counts too (22485's
    # layout: a single HEPATITIS C ANTIBODY item)
    trio = hep_trio()
    trio[0] = row(
        "HEPATITIS C AB W/RFL RNA, PCR W/RFL GENOTYPE,LIPA",
        result(("HEPATITIS C ANTIBODY", "NON-REACTIVE", "N")),
    )
    assert build_lab_summary(trio) == "11/2026- HBV/HCV neg, HBV Ab neg"
    # a missing member suppresses the HBV/HCV group -- the negative
    # surface-Ag screen of the partial trio reports its own HBV neg
    # token instead (the Ag + Ab pair without the HCV row, below)
    assert build_lab_summary(hep_trio()[:2]) == "11/2026- HBV neg"
    # the negative surface-Ag + reactive surface-Ab pair without an
    # HCV row (19082's layout, a vaccinated patient): HBV neg from
    # the non-reactive Ag, the reactive Ab (immunity) its own token
    assert build_lab_summary([
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "NON-REACTIVE", "N"))),
        row("Hep B surface Ab",
            result(("HEPATITIS B SURFACE$ANTIBODY QL", "REACTIVE", "A"))),
    ]) == "11/2026- HBV neg, HBV Ab+"
    # a lone negative surface-Ag screen (both vendors' layouts)
    assert build_lab_summary([
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "NON-REACTIVE", "N")))
    ]) == "11/2026- HBV neg"
    assert build_lab_summary([
        row("Hep B surface Ag", result(("HBsAg Screen", "Negative", "")))
    ]) == "11/2026- HBV neg"
    # a pending / empty surface-Ag screen is undetermined, not
    # negative: no HBV neg (like the HIV / RPR screens)
    assert build_lab_summary([
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "", "")))
    ]) == ""
    assert build_lab_summary([
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "TNP", "N")))
    ]) == ""
    # the negative token reports right after the STD token when
    # other groups are negative (the trio is incomplete: no HCV row)
    assert build_lab_summary([
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "NON-REACTIVE", "N"))),
        hiv_quest(),
    ]) == "11/2026- HIV neg, HBV neg"
    # an abnormal member suppresses the neg group and reports its
    # own token (a partial trio reports it too: 20210's screen --
    # the surface-Ag and HCV Ab rows, no surface-Ab row)
    trio = hep_trio()
    trio[1] = row(
        "Hep B surface Ag", result(("HBsAg Screen", "Positive", "A")))
    assert build_lab_summary(trio) == "11/2026- HBsAg+, HBV Ab neg"
    assert build_lab_summary(hep_trio()[:1] + [trio[1]]) == \
        "11/2026- HBsAg+"
    # a lone reactive screen (no other hep B/C rows at all)
    assert build_lab_summary([trio[1]]) == "11/2026- HBsAg+"
    assert build_lab_summary([
        row("Hep C Ab RFX to Quant PCR",
            result(("Interpretation:", "", ""), ("HCV Ab", "Reactive", "A")))
    ]) == "11/2026- HCV+"
    # an abnormal HCV Ab reports HCV+ (the group drops too)
    trio = hep_trio()
    trio[0] = row(
        "Hep C Ab RFX to Quant PCR",
        result(("Interpretation:", "", ""), ("HCV Ab", "Reactive", "A")))
    assert build_lab_summary(trio) == "11/2026- HCV+, HBV Ab neg"
    # a reactive surface Ab (flag A) is immunity, not infection: it
    # does not drop the group and reports its own HBV Ab+ token
    # (22457's layout)
    trio = hep_trio()
    trio[2] = row("Hep B Surface Ab", result(
        ("HEPATITIS B SURFACE$ANTIBODY QL", "REACTIVE", "A")))
    assert build_lab_summary(trio) == "11/2026- HBV/HCV neg, HBV Ab+"
    # all three groups negative -> HBV/HCV/HIV/RPR neg (22545's Quest
    # screen)
    assert build_lab_summary(hep_trio() + [hiv_quest(), rpr_quest()]) == \
        "11/2026- HBV/HCV/HIV/RPR neg, HBV Ab neg"
    # LabCorp's HIV / RPR layouts join the token too
    assert build_lab_summary(
        hep_trio() + [hiv_labcorp(), rpr_labcorp()]) == \
        "11/2026- HBV/HCV/HIV/RPR neg, HBV Ab neg"
    # HIV + RPR without the hep trio
    assert build_lab_summary([hiv_quest(), rpr_quest()]) == \
        "11/2026- HIV/RPR neg"
    # in-house order names match too
    assert build_lab_summary([
        row("hiv", result(("HIV Screen 4th Generation wRfx", "Non Reactive",
                           "")))
    ]) == "11/2026- HIV neg"
    # a reactive RPR drops the RPR group and reports RPR+
    assert build_lab_summary(hep_trio() + [
        hiv_quest(),
        row("RPR (Dx) w/ Confirmatory", result(
            ("RPR (DX) W/REFL TITER AND$CONFIRMATORY TESTING",
             "REACTIVE", "A"))),
    ]) == "11/2026- HBV/HCV/HIV neg, RPR+, HBV Ab neg"
    # Quest's reactive RPR with its titer (20181's layout: 1:1, a
    # likely false positive next to a negative treponemal Ab)
    assert build_lab_summary(hep_trio() + [
        row("RPR (Dx) w/ Confirmatory", result(
            ("RPR TITER", "1:1", "H"),
            ("RPR (DX) W/REFL TITER AND$CONFIRMATORY TESTING",
             "REACTIVE", "A"))),
        row("TREPONEMA PALLIDUM AB",
            result(("TREPONEMA PALLIDUM AB", "NEGATIVE", "N"))),
    ]) == "11/2026- HBV/HCV/Treponema neg, RPR+, HBV Ab neg"
    # Quest's REACTIVE Ag/Ab screen (flag N!) on an HIV-negative
    # patient: the reflex work-up says HIV NEGATIVE -> still negative
    assert build_lab_summary([hiv_reactive()]) == "11/2026- HIV neg"
    # a positive final interpretation drops the HIV group and
    # reports HIV+ (22487's reflex work-up layout, positive side)
    assert build_lab_summary(hep_trio() + [
        row("HIV 1/2 Ag/Ab, 4th generation", result(
            ("HIV AG/AB, 4TH GEN", "REACTIVE", "A"),
            ("HIV FINAL INTERPRETATION", "HIV POSITIVE", "A"))),
        rpr_quest(),
    ]) == "11/2026- HBV/HCV/RPR neg, HIV+, HBV Ab neg"
    # a reactive LabCorp HIV screen reports HIV+ (14584's screen)
    assert build_lab_summary([
        row("HIV", result(("HIV Screen 4th Generation wRfx", "Reactive",
                           "A")))
    ]) == "11/2026- HIV+"
    # a reactive LabCorp RPR reports RPR+ (20131's screen)
    assert build_lab_summary([
        row("RPR", result(("RPR", "Reactive", "A")))
    ]) == "11/2026- RPR+"
    # several positives keep their group order (20131's note: HIV1+,
    # RPR reactive 1:2)
    assert build_lab_summary(hep_trio() + [
        row("HIV 1/2 Ag/Ab, 4th generation", result(
            ("HIV AG/AB, 4TH GEN", "REACTIVE", "A"),
            ("HIV FINAL INTERPRETATION", "HIV POSITIVE", "A"))),
        row("RPR (Dx) w/ Confirmatory", result(
            ("RPR TITER", "1:2", "H"),
            ("RPR (DX) W/REFL TITER AND$CONFIRMATORY TESTING",
             "REACTIVE", "A"))),
    ]) == "11/2026- HBV/HCV neg, HIV+, RPR+, HBV Ab neg"
    # a pending / empty HIV result is undetermined: no neg group and
    # no + token
    assert build_lab_summary([
        row("HIV 1/2 Ag/Ab, 4th generation",
            result(("HIV AG/AB, 4TH GEN", "", ""),
                   ("HIV FINAL INTERPRETATION", "", "")))
    ]) == ""
    # a pending / empty HCV Ab screen is undetermined too
    assert build_lab_summary([
        row("Hep C Ab RFX to Quant PCR",
            result(("Interpretation:", "", ""), ("HCV Ab", "", "")))
    ]) == ""
    # LabCorp's qualitative-RNA confirmatory order (the reflex on a
    # reactive screen) feeds the HIV group too: both RNA items
    # non-reactive -> HIV negative (20779's layout)
    assert build_lab_summary(hep_trio() + [
        row("HIV-1/HIV-2 Qualitative RNA",
            result(("HIV-1 RNA", "Non Reactive", ""),
                   ("HIV-2 RNA", "Non Reactive", ""))),
        rpr_quest(),
    ]) == "11/2026- HBV/HCV/HIV/RPR neg, HBV Ab neg"
    # a detected / flagged RNA is not negative: it drops the group
    # and reports HIV+
    assert build_lab_summary([
        row("HIV-1/HIV-2 Qualitative RNA",
            result(("HIV-1 RNA", "Detected", "A"),
                   ("HIV-2 RNA", "Non Reactive", "")))
    ]) == "11/2026- HIV+"


# ----------------------------------------------------------------------
# HSV 1/2 IgG
# ----------------------------------------------------------------------

def hsv_quest(hsv1=("<0.90", "N"), hsv2=("<0.90", "N"), **kw):
    """Quest's HerpesSelect order (both types on one result), both
    types negative by default (22447's layout)."""
    return row(
        "HSV 1/2 IGG, HERPESELECT$W/REFL HSV2 INHIBITION",
        result(
            ("HSV 1 IGG TYPE SPECIFIC$AB", *hsv1),
            ("HSV 2 IGG TYPE SPECIFIC$AB", *hsv2),
        ),
        **kw,
    )


def hsv_labcorp(hsv1=("Non Reactive", ""),
                hsv2=("Non Reactive", ""), **kw):
    """LabCorp's type-specific HSV antibody order (both types on one
    result), both types non-reactive by default (21334's layout)."""
    return row(
        "HSV 1 and 2 Ab, IgG",
        result(
            ("HSV 1 IgG, Type Spec", *hsv1),
            ("HSV 2 IgG, Type Spec", *hsv2),
        ),
        **kw,
    )


def test_hsv():
    # both types negative -> HSV joins the STD token's neg list
    # (both vendors' layouts)
    assert build_lab_summary([hsv_quest()]) == "11/2026- HSV neg"
    assert build_lab_summary([hsv_labcorp()]) == "11/2026- HSV neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hsv 1 and 2 ab, igg",
            result(("HSV 1 IgG, Type Spec", "Non Reactive", ""),
                   ("HSV 2 IgG, Type Spec", "Non Reactive", "")))
    ]) == "11/2026- HSV neg"
    # both negative join a full STD screen after RPR (21334's note:
    # HBV/HCV/HIV/RPR/HSV neg)
    assert build_lab_summary(
        hep_trio() + [hiv_quest(), rpr_quest(), hsv_quest()]) == \
        "11/2026- HBV/HCV/HIV/RPR/HSV neg, HBV Ab neg"
    # LabCorp's layout joins the token too
    assert build_lab_summary(
        hep_trio() + [hiv_labcorp(), rpr_labcorp(), hsv_labcorp()]) == \
        "11/2026- HBV/HCV/HIV/RPR/HSV neg, HBV Ab neg"
    # HSV1 positive (index above 1.09, flag H), HSV2 negative: the
    # negative type stays in the neg list, the positive type reports
    # its own token right after the STD token (16235's note:
    # HBV/HCV/HIV/RPR/HSV2 neg, HSV1+)
    assert build_lab_summary([hsv_quest(hsv1=("58.00", "H"))]) == \
        "11/2026- HSV2 neg, HSV1+"
    assert build_lab_summary(
        hep_trio() + [hiv_quest(), rpr_quest(),
                      hsv_quest(hsv1=("58.00", "H"))]) == \
        "11/2026- HBV/HCV/HIV/RPR/HSV2 neg, HSV1+, HBV Ab neg"
    # the positive type can be HSV2 too (13385's note: HIV/HSV1 neg,
    # HSV2+)
    assert build_lab_summary([hsv_quest(hsv2=("1.20", "H"))]) == \
        "11/2026- HSV1 neg, HSV2+"
    # a capped index (>58.00, the assay's upper limit) is positive
    assert build_lab_summary([hsv_quest(hsv1=(">58.00", "H"))]) == \
        "11/2026- HSV2 neg, HSV1+"
    # both positive -> one combined token (22364's note: HSV1/HSV2+),
    # the STD screen's neg list keeps no HSV type
    assert build_lab_summary(
        [hsv_quest(hsv1=("10.00", "H"), hsv2=("7.95", "H"))]) == \
        "11/2026- HSV1/HSV2+"
    assert build_lab_summary(
        hep_trio() + [hiv_quest(), rpr_quest(),
                      hsv_quest(hsv1=("10.00", "H"),
                                hsv2=("7.95", "H"))]) == \
        "11/2026- HBV/HCV/HIV/RPR neg, HSV1/HSV2+, HBV Ab neg"
    # LabCorp's Reactive / Non Reactive text decides the same way
    assert build_lab_summary(
        [hsv_labcorp(hsv1=("Reactive", "A"))]) == \
        "11/2026- HSV2 neg, HSV1+"
    assert build_lab_summary(
        [hsv_labcorp(hsv2=("Reactive", "A"))]) == \
        "11/2026- HSV1 neg, HSV2+"
    # the equivocal band (0.90-1.09) is undetermined: it drops its
    # type from the neg list and produces no + token
    assert build_lab_summary(
        [hsv_quest(hsv1=("1.00", "A"))]) == "11/2026- HSV2 neg"
    # both types undetermined -> nothing
    assert build_lab_summary(
        [hsv_quest(hsv1=("1.00", "A"), hsv2=("1.00", "A"))]) == ""
    # a pending / empty value is undetermined too
    assert build_lab_summary([hsv_quest(hsv1=("", ""))]) == \
        "11/2026- HSV2 neg"
    # the HSV 2 IgG inhibition reflex follow-up is a separate order
    # and is not part of the category
    assert build_lab_summary([
        row("HSV 2 IGG INHIBITION, IA",
            result(("HSV 2 IGG INHIBITION, IA", "NEGATIVE", "N")))
    ]) == ""


# ----------------------------------------------------------------------
# G-C (chlamydia / gonorrhea NAA)
# ----------------------------------------------------------------------

def gc_inhouse(chlamydia=("Not Detected", ""),
               gc=("Not Detected", ""), **kw):
    """The in-house `Chlamydia / GC urine` order (Quest's item
    layout), both pathogens not detected by default."""
    return row(
        "Chlamydia / GC urine",
        result(
            ("CHLAMYDIA TRACHOMATIS", *chlamydia),
            ("NEISSERIA GONORRHOEAE", *gc),
        ),
        **kw,
    )


def gc_labcorp(chlamydia=("Negative", ""),
               gc=("Negative", ""), **kw):
    """LabCorp's `Chlamydia/GC Amplification` order, both pathogens
    negative by default."""
    return row(
        "Chlamydia/GC Amplification",
        result(
            ("Chlamydia trachomatis, NAA", *chlamydia),
            ("Neisseria gonorrhoeae, NAA", *gc),
        ),
        **kw,
    )


def gc_quest(chlamydia=("NOT DETECTED", "N"),
             gc=("NOT DETECTED", "N"), **kw):
    """Quest's `CHLAMYDIA/N. GONORRHOEAE$RNA, TMA` order (with the
    `(Always Message)` note item), both pathogens not detected by
    default."""
    return row(
        "CHLAMYDIA/N. GONORRHOEAE$RNA, TMA",
        result(
            ("(Always Message)", "", ""),
            ("CHLAMYDIA TRACHOMATIS$RNA, TMA", *chlamydia),
            ("NEISSERIA GONORRHOEAE$RNA, TMA", *gc),
        ),
        **kw,
    )


def test_gc():
    # both pathogens negative -> G-C joins the STD token's neg list
    # (all three layouts)
    assert build_lab_summary([gc_inhouse()]) == "11/2026- G-C neg"
    assert build_lab_summary([gc_labcorp()]) == "11/2026- G-C neg"
    assert build_lab_summary([gc_quest()]) == "11/2026- G-C neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("chlamydia / gc urine",
            result(("CHLAMYDIA TRACHOMATIS", "Not Detected", ""),
                   ("NEISSERIA GONORRHOEAE", "Not Detected", "")))
    ]) == "11/2026- G-C neg"
    # G-C joins a full STD screen after the HSV segment (22312's
    # note: HBV/HCV/HIV/RPR/G-C neg)
    assert build_lab_summary(
        hep_trio() + [hiv_quest(), rpr_quest(), gc_inhouse()]) == \
        "11/2026- HBV/HCV/HIV/RPR/G-C neg, HBV Ab neg"
    # a detected pathogen is its own G-C+ token right after the STD
    # token; the negative member is not reported (21753's note)
    assert build_lab_summary(
        [gc_inhouse(chlamydia=("Detected", "A"))]) == "11/2026- G-C+"
    assert build_lab_summary(
        hep_trio() + [gc_inhouse(gc=("Detected", "A"))]) == \
        "11/2026- HBV/HCV neg, G-C+, HBV Ab neg"
    # Quest's DETECTED value (flag A) is positive too
    assert build_lab_summary(
        [gc_quest(chlamydia=("DETECTED", "A"))]) == "11/2026- G-C+"
    # LabCorp's Positive value (flag A) is positive too
    assert build_lab_summary(
        [gc_labcorp(gc=("Positive", "A"))]) == "11/2026- G-C+"
    # the chlamydia-only order reports G-C too (13274's note)
    assert build_lab_summary([
        row("CHLAMYDIA TRACHOMATIS$RNA, TMA",
            result(("(Always Message)", "", ""),
                   ("CHLAMYDIA TRACHOMATIS$RNA, TMA",
                    "NOT DETECTED", "N")))
    ]) == "11/2026- G-C neg"
    # a pending / empty value is undetermined -> nothing
    assert build_lab_summary([gc_inhouse(chlamydia=("", ""))]) == ""
    # the alternate-target reflex re-test is a separate order and
    # is not part of the category
    assert build_lab_summary([
        row("CHLAMYDIA TRACHOMATIS, TMA (ALTERNATE TARGET)",
            result(("CHLAMYDIA TRACHOMATIS,TMA", "Detected", "A")))
    ]) == ""


# ----------------------------------------------------------------------
# Treponema pallidum Ab
# ----------------------------------------------------------------------

def treponema_quest(value="NEGATIVE", flag="N", **kw):
    """Quest's `TREPONEMA PALLIDUM AB` confirmatory, negative by
    default (20181's layout)."""
    return row(
        "TREPONEMA PALLIDUM AB",
        result(("TREPONEMA PALLIDUM AB", value, flag)),
        **kw,
    )


def test_treponema():
    # negative -> Treponema joins the STD token's neg list
    assert build_lab_summary([treponema_quest()]) == \
        "11/2026- Treponema neg"
    # it joins a full STD screen after G-C (20181's note)
    assert build_lab_summary(
        hep_trio() + [hiv_quest(), rpr_quest(), gc_inhouse(),
                      treponema_quest()]) == \
        "11/2026- HBV/HCV/HIV/RPR/G-C/Treponema neg, HBV Ab neg"
    # a POSITIVE value is its own Treponema+ token right after the
    # STD token
    assert build_lab_summary(
        [treponema_quest(value="POSITIVE", flag="A")]) == \
        "11/2026- Treponema+"
    assert build_lab_summary(
        hep_trio() + [rpr_quest(),
                      treponema_quest(value="POSITIVE", flag="A")]) == \
        "11/2026- HBV/HCV/RPR neg, Treponema+, HBV Ab neg"
    # a pending / empty value is undetermined -> nothing
    assert build_lab_summary([treponema_quest(value="", flag="")]) == ""


# ----------------------------------------------------------------------
# Iron panel / B12
# ----------------------------------------------------------------------

def iron_labcorp(abnormal=None, **kw):
    """The full LabCorp Iron and TIBC layout, all items normal unless
    ``abnormal`` gives an item name -> (value, flag) override."""
    items = [
        ("Iron Bind.Cap.(TIBC)", "347", "", "250-450"),
        ("UIBC", "244", "", "111-343"),
        ("Iron, Serum", "103", "", "38-169"),
        ("Iron Saturation", "30", "", "15-55"),
    ]
    if abnormal:
        items = [
            (name, abnormal[name][0], abnormal[name][1], rng)
            if name in abnormal
            else (name, value, flag, rng)
            for name, value, flag, rng in items
        ]
    return row("Iron and TIBC", result(*items), **kw)


def test_iron():
    # normal panel -> iron nl (both vendors' name spellings)
    assert build_lab_summary([iron_labcorp()]) == "11/2026- iron nl"
    assert build_lab_summary([
        row("IRON, TIBC AND FERRITIN PANEL",
            iron_labcorp()["result"])
    ]) == "11/2026- iron nl"
    # an abnormal item suppresses the iron nl and gets its own token
    # with the violated limit (14395's 10/2026 panel: iron 171(169),
    # iron%sat 62(55))
    assert build_lab_summary([
        iron_labcorp(abnormal={
            "Iron, Serum": ("171", "H"),
            "Iron Saturation": ("62", "H"),
        })
    ]) == "11/2026- iron 171(169), iron%sat 62(55)"
    # one token per abnormal item, in report order (TIBC first, then
    # iron, then iron%sat -- the normal UIBC contributes nothing)
    assert build_lab_summary([
        iron_labcorp(abnormal={
            "Iron Bind.Cap.(TIBC)": ("475", "H"),
            "Iron, Serum": ("171", "H"),
            "Iron Saturation": ("62", "H"),
        })
    ]) == "11/2026- TIBC 475(450), iron 171(169), iron%sat 62(55)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        iron_labcorp(abnormal={"Iron Bind.Cap.(TIBC)": ("194", "L")})
    ]) == "11/2026- TIBC 194(250)"
    # an abnormal item without a parsable range has no parentheses
    assert build_lab_summary([
        row("Iron and TIBC", result(
            ("Iron, Serum", "171", "H"),
            ("Iron Saturation", "30", "", "15-55")))
    ]) == "11/2026- iron 171"
    # the derived UIBC item gets no token of its own, but its
    # abnormality still suppresses the iron nl (14395's 10/2026 panel
    # had a low UIBC 104 in 111-343 alongside the high iron / sat)
    assert build_lab_summary([
        row("Iron and TIBC", result(
            ("Iron Bind.Cap.(TIBC)", "275", "", "250-450"),
            ("UIBC", "104", "L", "111-343"),
            ("Iron, Serum", "171", "H", "38-169"),
            ("Iron Saturation", "62", "H", "15-55")))
    ]) == "11/2026- iron 171(169), iron%sat 62(55)"
    # Quest's IRON, TIBC AND FERRITIN PANEL item names (IRON, TOTAL /
    # IRON BINDING CAPACITY / % SATURATION / FERRITIN) match too,
    # ferritin included (the yellow notes' `ferritin 693(400)`)
    assert build_lab_summary([
        row("IRON, TIBC AND FERRITIN PANEL", result(
            ("IRON, TOTAL", "160", "H", "50-180"),
            ("IRON BINDING CAPACITY", "302", "", "250-425"),
            ("% SATURATION", "53", "H", "20-48"),
            ("FERRITIN", "693", "H", "38-400")))
    ]) == ("11/2026- iron 160(180), iron%sat 53(48), "
           "ferritin 693(400)")
    # a standalone Ferritin order is a separate category (rule 27a),
    # not part of this one
    assert build_lab_summary([
        row("Ferritin, Serum", result(("Ferritin, Serum", "693", "H", "13-150")))
    ]) == "11/2026- ferritin 693(150)"


# ----------------------------------------------------------------------
# ferritin (standalone order; rule 27a)
# ----------------------------------------------------------------------

def test_ferritin_standalone():
    # normal -> nothing (the in-house / Quest order's range 16-232)
    assert build_lab_summary([
        row("ferritin", result(("FERRITIN", "40", "N", "16-232")))
    ]) == ""
    # abnormal high -> ferritin {val}(upper limit), LabCorp's
    # `ferritin, serum` spelling (the real 693 in 30-400)
    assert build_lab_summary([
        row("ferritin, serum", result(("Ferritin, Serum", "693", "H", "30-400")))
    ]) == "11/2026- ferritin 693(400)"
    # name matching is case-insensitive; abnormal low -> lower limit
    assert build_lab_summary([
        row("FERRITIN", result(("FERRITIN", "12", "L", "16-232")))
    ]) == "11/2026- ferritin 12(16)"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([
        row("ferritin", result(("FERRITIN", "450", "H")))
    ]) == "11/2026- ferritin 450"


def test_iron_standalone():
    # normal -> nothing (22487's 100 in Quest's 45-160)
    assert build_lab_summary([
        row("Iron", result(("IRON, TOTAL", "100", "N", "45-160")))
    ]) == ""
    # LabCorp's layout (13097's 88 in 27-139, empty flag = normal)
    assert build_lab_summary([
        row("Iron, Serum", result(("Iron, Serum", "88", "", "27-139")))
    ]) == ""
    # abnormal high -> upper limit (17933's 201 in 40-190)
    assert build_lab_summary([
        row("Iron", result(("IRON, TOTAL", "201", "H", "40-190")))
    ]) == "11/2026- iron 201(190)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("Iron, Serum", result(("Iron, Serum", "20", "L", "27-139")))
    ]) == "11/2026- iron 20(27)"
    # the iron-panel orders are not this category: a normal panel is
    # reported by rule 27 as `iron nl`
    assert build_lab_summary([
        row("Iron and TIBC",
            result(("Iron, Serum", "100", "N"),
                  ("Iron Bind.Cap.(TIBC)", "400", "")))
    ]) == "11/2026- iron nl"


def test_copper():
    # normal -> copper nl (20089's 85 in 70-175; unlike most
    # standalone tokens a normal copper is reported)
    assert build_lab_summary([
        row("COPPER", result(("COPPER", "85", "N", "70-175", "", "mcg/dL"))),
    ]) == "11/2026- copper nl"
    # abnormal high -> copper {val}(upper limit)
    assert build_lab_summary([
        row("COPPER", result(("COPPER", "186", "H", "70-175"))),
    ]) == "11/2026- copper 186(175)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("COPPER", result(("COPPER", "60", "L", "70-175"))),
    ]) == "11/2026- copper 60(70)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("copper", result(("COPPER", "85", "N", "70-175"))),
    ]) == "11/2026- copper nl"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([
        row("COPPER", result(("COPPER", "186", "H"))),
    ]) == "11/2026- copper 186"


def test_b12():
    # abnormal high, range 232-1245 -> B12 {val}(upper limit)
    assert build_lab_summary([
        row("Vitamin B12", result(("Vitamin B12", "1285", "H", "232-1245")))
    ]) == "11/2026- B12 1285(1245)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("Vitamin B12", result(("Vitamin B12", "150", "L", "232-1245")))
    ]) == "11/2026- B12 150(232)"
    # name matching is case-insensitive (Quest spells it VITAMIN B12)
    assert build_lab_summary([
        row("VITAMIN B12", result(("Vitamin B12", "1285", "H", "232-1245")))
    ]) == "11/2026- B12 1285(1245)"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([
        row("Vitamin B12", result(("Vitamin B12", "1285", "H")))
    ]) == "11/2026- B12 1285"
    # normal -> the value written plain
    assert build_lab_summary([
        row("Vitamin B12", result(("Vitamin B12", "450", "", "232-1245")))
    ]) == "11/2026- B12 450"
    # the B12/folate panel order joins the B12 category (rule 28):
    # the panel's abnormal B12 (no range on the item) reports its
    # value plain, alongside its normal folate's FA nl
    assert build_lab_summary([
        row("VITAMIN B12/FOLATE,$SERUM PANEL",
            result(("Vitamin B12", "1285", "H"), ("Folate", "9.9", "")))
    ]) == "11/2026- B12 1285, FA nl"


# ----------------------------------------------------------------------
# Vitamin B1 / B2 / B6 (the B vitamins)
# ----------------------------------------------------------------------

def b1_labcorp(value="101.5", flag="", rng="66.5-200.0", **kw):
    return row(
        "Vitamin B1 (Thiamine), Blood",
        result(("Vit. B1, Whole Blood", value, flag, rng)),
        **kw,
    )


def b1_quest(value="13", flag="", rng="8-30", **kw):
    return row(
        "VITAMIN B1 (THIAMINE), SERUM/PLASMA, LC/MS/MS",
        result(("VITAMIN B1 (THIAMINE),", value, flag, rng)),
        **kw,
    )


def b2_quest(value="30.7", flag="", rng="6.2-39.0", **kw):
    return row(
        "VITAMIN B2 (RIBOFLAVIN), PLASMA",
        result(("VITAMIN B2 (RIBOFLAVIN),", value, flag, rng)),
        **kw,
    )

def test_b6():
    # normal (Quest's layout, 22427's 10.1 in 5.1-54.8) -> B6 nl
    # (the yellow notes write a normal as `B6 nl` / `Vit B6 nl`)
    assert build_lab_summary([
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "10.1", "", "5.1-54.8")))
    ]) == "11/2026- B6 nl"
    # LabCorp's layout (22012's 12.3, range 3.4-65.2, empty flag)
    assert build_lab_summary([
        row("Vitamin B6, Plasma",
            result(("Vitamin B6", "12.3", "", "3.4-65.2")))
    ]) == "11/2026- B6 nl"
    # abnormal high -> upper limit, value and bound rendered via
    # _b6_value (19751's 118.6 in 5.1-54.8, 14953's 159.8)
    assert build_lab_summary([
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "118.6", "H", "5.1-54.8")))
    ]) == "11/2026- B6 119(55)"
    assert build_lab_summary([
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "159.8", "H", "5.1-54.8")))
    ]) == "11/2026- B6 160(55)"
    # abnormal low -> lower limit (two significant figures below 10
    # keep their decimal: 2.9 in 3.4-65.2 -> 2.9(3.4))
    assert build_lab_summary([
        row("Vitamin B6, Plasma",
            result(("Vitamin B6", "2.9", "L", "3.4-65.2")))
    ]) == "11/2026- B6 2.9(3.4)"
    # next to a B12 row: the tokens follow the fixed rule order
    # (B12 before B6)
    assert build_lab_summary([
        row("Vitamin B12", result(("Vitamin B12", "1285", "H", "232-1245"))),
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "10.1", "", "5.1-54.8"))),
    ]) == "11/2026- B12 1285(1245), B6 nl"


def test_b1():
    # normal (both layouts: 22012's 101.5, 22300's 13) -> B1 nl
    assert build_lab_summary([b1_labcorp()]) == "11/2026- B1 nl"
    assert build_lab_summary([b1_quest()]) == "11/2026- B1 nl"
    # abnormal high -> upper limit; low -> lower limit
    assert build_lab_summary([b1_labcorp("250", "H")]) == \
        "11/2026- B1 250(200)"
    assert build_lab_summary([b1_quest("4", "L")]) == "11/2026- B1 4(8)"
    # name matching is case-insensitive (both order names)
    assert build_lab_summary(
        [row("vitamin b1 (thiamine), blood", b1_labcorp()["result"])]) == \
        "11/2026- B1 nl"
    assert build_lab_summary(
        [row("vitamin b1 (thiamine), serum/plasma, lc/ms/ms",
             b1_quest()["result"])]) == "11/2026- B1 nl"
    # pending value on an abnormal result -> nothing
    assert build_lab_summary([b1_labcorp("", "A")]) == ""


def test_b1b6_cluster():
    # two normal members join one token (22012's 101.5 / 12.3, the
    # note's `B1/B6 nl`)
    assert build_lab_summary([
        b1_labcorp(),
        row("Vitamin B6, Plasma",
            result(("Vitamin B6", "12.3", "", "3.4-65.2"))),
    ]) == "11/2026- B1/B6 nl"
    # a lone normal member reports its own label
    assert build_lab_summary([b1_labcorp()]) == "11/2026- B1 nl"
    # an abnormal member reports its own token right after the joined
    # normal one, in member order
    assert build_lab_summary([
        row("Vitamin B6, Plasma",
            result(("Vitamin B6", "12.3", "", "3.4-65.2"))),
        b1_quest("4", "L"),
    ]) == "11/2026- B6 nl, B1 4(8)"
    assert build_lab_summary([
        b1_labcorp(),
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "118.6", "H", "5.1-54.8"))),
    ]) == "11/2026- B1 nl, B6 119(55)"
    # both abnormal: no joined token, one token per member
    assert build_lab_summary([
        b1_quest("4", "L"),
        row("VITAMIN B6, PLASMA",
            result(("VITAMIN B6, PLASMA", "118.6", "H", "5.1-54.8"))),
    ]) == "11/2026- B1 4(8), B6 119(55)"


def test_b2():
    # normal (16978's 30.7) -> B2 nl
    assert build_lab_summary([b2_quest()]) == "11/2026- B2 nl"
    # abnormal low -> lower limit; high -> upper limit
    assert build_lab_summary([b2_quest("4.1", "L")]) == \
        "11/2026- B2 4.1(6.2)"
    assert build_lab_summary([b2_quest("50.0", "H")]) == \
        "11/2026- B2 50.0(39)"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("vitamin b2 (riboflavin), plasma", b2_quest()["result"])]) == \
        "11/2026- B2 nl"


# ----------------------------------------------------------------------
# QTB (QuantiFERON-TB Gold Plus)
# ----------------------------------------------------------------------

def qtb_quest(**kw):
    return row(
        "QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE",
        result(
            ("MITOGEN-NIL", "9.16", "N"),
            ("NIL", "0.05", "N"),
            ("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", "NEGATIVE", "N"),
            ("TB1-NIL", "0.00", "N"),
            ("TB2-NIL", "0.01", "N"),
        ),
        **kw,
    )


def qtb_labcorp(interpretation="Negative", **kw):
    return row(
        "QuantiFERON-TB Gold Plus",
        result(
            ("QuantiFERON Criteria", "", ""),
            ("QuantiFERON Incubation", "Incubation performed.", ""),
            ("QuantiFERON Mitogen Value", ">10.00", ""),
            ("QuantiFERON Nil Value", "0.02", ""),
            ("QuantiFERON TB1 Ag Value", "0.02", ""),
            ("QuantiFERON TB2 Ag Value", "0.02", ""),
            ("QuantiFERON-TB Gold Plus", interpretation, ""),
        ),
        **kw,
    )


def test_qtb():
    # negative (both vendors' layouts) -> QTB neg
    assert build_lab_summary([qtb_quest()]) == "11/2026- QTB neg"
    assert build_lab_summary([qtb_labcorp()]) == "11/2026- QTB neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("quantiferon(r)-tb gold plus, 1 tube", qtb_quest()["result"])
    ]) == "11/2026- QTB neg"
    # positive -> QTB+ (both vendors' layouts)
    assert build_lab_summary([qtb_quest_interpretation("POSITIVE")]) == \
        "11/2026- QTB+"
    assert build_lab_summary([qtb_labcorp("Positive")]) == "11/2026- QTB+"
    # indeterminate -> nothing
    assert build_lab_summary([qtb_labcorp("Indeterminate")]) == ""
    # no interpretation item (values only) -> nothing
    assert build_lab_summary([
        row("QuantiFERON-TB Gold Plus", result(("QuantiFERON Criteria", "", "")))
    ]) == ""


def qtb_quest_interpretation(interpretation="NEGATIVE"):
    data = json.loads(qtb_quest()["result"])
    for item in data:
        if item["itemName"].startswith("QUANTIFERON"):
            item["value"] = interpretation
    return row("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", json.dumps(data))


# ----------------------------------------------------------------------
# ABO grouping / Rho(D) typing
# ----------------------------------------------------------------------

def abo_labcorp(group="B", rh="Positive", **kw):
    return row(
        "ABO Grouping and Rho(D) Typing",
        result(
            ("ABO Grouping", group, ""),
            ("Rh Factor", rh, ""),
        ),
        **kw,
    )


def abo_quest(group="A", rh="RH(D) POSITIVE", **kw):
    return row(
        "ABO GROUP AND RH TYPE",
        result(
            ("ABO GROUP", group, ""),
            ("RH TYPE", rh, ""),
        ),
        **kw,
    )


def test_abo():
    # positive (both vendors' layouts) -> ABO {group}+
    assert build_lab_summary([abo_labcorp()]) == "11/2026- ABO B+"
    assert build_lab_summary([abo_quest()]) == "11/2026- ABO A+"
    # negative -> ABO {group}-
    assert build_lab_summary([abo_labcorp(rh="Negative")]) == "11/2026- ABO B-"
    assert build_lab_summary([abo_quest(rh="RH(D) NEGATIVE")]) == "11/2026- ABO A-"
    # the other groups
    assert build_lab_summary([abo_labcorp(group="AB")]) == "11/2026- ABO AB+"
    assert build_lab_summary([abo_quest(group="O")]) == "11/2026- ABO O+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("abo grouping and rho(d) typing", abo_labcorp()["result"])
    ]) == "11/2026- ABO B+"
    # pending / empty values produce nothing
    assert build_lab_summary([
        row("ABO Grouping and Rho(D) Typing", result(
            ("ABO Grouping", "", ""), ("Rh Factor", "", "")))
    ]) == ""
    assert build_lab_summary([
        row("ABO Grouping and Rho(D) Typing", result_text="[]")
    ]) == ""
    # an unrecognized Rh value produces nothing
    assert build_lab_summary([abo_quest(rh="PENDING")]) == ""
    # per category the newest row wins (both vendors' orders feed the
    # one category)
    assert build_lab_summary([
        abo_labcorp(group="B", rh="Positive", result_date="2026-11-07"),
        abo_quest(group="A", rh="RH(D) NEGATIVE", result_date="2026-10-01"),
    ]) == "11/2026- ABO B+"


# ----------------------------------------------------------------------
# H. pylori / stool occult blood
# ----------------------------------------------------------------------

def hpylori_quest(value="NOT DETECTED", flag="N", result_date="2026-11-07"):
    return row(
        "H PYLORI,$UREA BREATH TEST",
        result(("HELICOBACTER PYLORI,$UREA BREATH TEST", value, flag)),
        result_date=result_date,
    )


def hpylori_labcorp(value="Negative", flag=""):
    return row(
        "H pylori Breath Test",
        result(("H pylori Breath Test", value, flag)),
    )


def stool_quest(value="", flag=""):
    return row(
        "Stool occult",
        result(("FECAL GLOBIN BY$IMMUNOCHEMISTRY", value, flag)),
    )


def stool_labcorp(value="Negative", flag=""):
    return row(
        "Stool occult blood",
        result(("Occult Blood, Fecal, IA", value, flag)),
    )


def test_hpylori():
    # negative (both vendors' layouts) -> H pylori neg
    assert build_lab_summary([hpylori_quest()]) == "11/2026- H pylori neg"
    assert build_lab_summary([hpylori_labcorp()]) == "11/2026- H pylori neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("h pylori,$urea breath test", hpylori_quest()["result"])
    ]) == "11/2026- H pylori neg"
    # positive (both vendors) -> H pylori+
    assert build_lab_summary([hpylori_quest("DETECTED", "A")]) == "11/2026- H pylori+"
    assert build_lab_summary([hpylori_labcorp("Positive", "A")]) == "11/2026- H pylori+"
    # pending value (Quest's TNP) -> nothing
    assert build_lab_summary([hpylori_quest("TNP", "N")]) == ""
    # collection-kit / stool-antigen rows with no value -> nothing
    assert build_lab_summary([
        row("H. pylori Breath Collection",
            result(("H. pylori Breath Collection", "", "")))
    ]) == ""
    assert build_lab_summary([
        row("H PYLORI AG,$EIA, STOOL",
            result(("HELICOBACTER PYLORI AG,$EIA, STOOL", "", "")))
    ]) == ""
    # the newest row wins
    assert build_lab_summary([
        hpylori_quest(),
        hpylori_quest("DETECTED", "A", result_date="2026-09-01"),
    ]) == "11/2026- H pylori neg"
    assert build_lab_summary([
        hpylori_quest("DETECTED", "A"),
        hpylori_quest(result_date="2026-09-01"),
    ]) == "11/2026- H pylori+"


def test_stool():
    # negative: the in-house FIT leaves the value empty, LabCorp
    # reports `Negative` text
    assert build_lab_summary([stool_quest()]) == "11/2026- stool occult neg"
    assert build_lab_summary([stool_labcorp()]) == "11/2026- stool occult neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("stool occult blood", stool_labcorp()["result"])
    ]) == "11/2026- stool occult neg"
    # positive (both vendors; a flagged empty FIT value counts too)
    assert build_lab_summary([stool_quest(flag="A")]) == "11/2026- stool occult+"
    assert build_lab_summary([stool_labcorp("Positive", "A")]) == "11/2026- stool occult+"
    # an unrecognized nonempty value -> nothing
    assert build_lab_summary([stool_quest("PENDING")]) == ""
    # the two tests are reported next to each other, H pylori first
    assert build_lab_summary([
        hpylori_labcorp(),
        stool_quest(),
    ]) == "11/2026- H pylori neg, stool occult neg"


# ----------------------------------------------------------------------
# Stool culture (in-house)
# ----------------------------------------------------------------------

# The in-house orders' result-note texts carry the negative culture
# result (`No ... isolated`) on an empty item value.
ECOLI_CX_NEG_NOTES = (
    "ESCHERICHIA COLI O157, CULTURE\n"
    "  Test Status:       Final\n"
    "  Result:            No Escherichia coli O157 isolated"
)
SALM_CX_NEG_NOTES = (
    "SALMONELLA AND SHIGELLA, CULTURE\n"
    "  Test Status:       Final\n"
    "  Result:            No Salmonella or Shigella isolated"
)


def stool_cx_campy(value="NOT ISOLATED", flag="N", result_date="2026-11-08"):
    return row(
        "Stool culture - Campylobacter",
        result(("CULTURE", value, flag)),
        result_date=result_date,
    )


def stool_cx_ecoli(value="", flag="", notes=ECOLI_CX_NEG_NOTES,
                   result_date="2026-11-08"):
    return row(
        "Stool culture for Ecoli O157:H7",
        result(("CULTURE", value, flag, "", notes)),
        result_date=result_date,
    )


def stool_cx_salm(value="", flag="", notes=SALM_CX_NEG_NOTES,
                  result_date="2026-11-08"):
    return row(
        "SALMONELLA AND SHIGELLA, CULTURE",
        result(("CULTURE", value, flag, "", notes)),
        result_date=result_date,
    )


def test_stool_cx():
    # negative: each in-house order's layout -> stool culture neg
    assert build_lab_summary([stool_cx_campy()]) == "11/2026- stool culture neg"
    assert build_lab_summary([stool_cx_ecoli()]) == "11/2026- stool culture neg"
    assert build_lab_summary([stool_cx_salm()]) == "11/2026- stool culture neg"
    # all three negative -> one combined token
    assert build_lab_summary([
        stool_cx_campy(), stool_cx_ecoli(), stool_cx_salm(),
    ]) == "11/2026- stool culture neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("stool culture - campylobacter", stool_cx_campy()["result"])
    ]) == "11/2026- stool culture neg"
    # a positive culture is reported alone (the yellow notes' labels),
    # not the negative members
    assert build_lab_summary([stool_cx_campy("ISOLATED", "A")]) \
        == "11/2026- Campylobactor+"
    assert build_lab_summary([
        stool_cx_campy("ISOLATED", "A"), stool_cx_ecoli(), stool_cx_salm(),
    ]) == "11/2026- Campylobactor+"
    assert build_lab_summary([stool_cx_ecoli("ISOLATED", "A")]) \
        == "11/2026- E. coli O157:H7+"
    # a flagged empty value is an isolated culture too
    assert build_lab_summary([stool_cx_salm(flag="A")]) \
        == "11/2026- Salmonella/Shigella+"
    # pending: an empty value whose note carries no negative marker
    # (an in-process result) -> nothing
    assert build_lab_summary([
        stool_cx_ecoli(notes="Test Status: In Process"),
    ]) == ""
    # a lone negative next to a pending culture reports nothing
    assert build_lab_summary([
        stool_cx_campy(), stool_cx_ecoli(notes=""),
    ]) == ""
    # an unrecognized value -> nothing
    assert build_lab_summary([
        stool_cx_campy("PENDING", ""),
    ]) == ""
    # the newest row wins, per order
    assert build_lab_summary([
        stool_cx_campy(),
        stool_cx_campy("ISOLATED", "A", result_date="2026-09-01"),
    ]) == "11/2026- stool culture neg"
    assert build_lab_summary([
        stool_cx_campy("ISOLATED", "A"),
        stool_cx_campy(result_date="2026-09-01"),
    ]) == "11/2026- Campylobactor+"
    # the susceptibility / bacterial-ID follow-ups are separate orders
    # and produce nothing
    assert build_lab_summary([
        row("ANTIMICROBIAL SUSC., CAMPYLOBACTER,MIC PANEL",
            result(("ORGANISM", "CAMPYLOBACTER JEJUNI", "N"),
                   ("CIPROFLOXACIN", "0.030 S", "N"),
                   ("SPECIMEN SOURCE", "STOOL", "N"))),
        row("BACTERIAL ID AND SUSCEPTIBILITY, AEROBIC",
            result(("ORGANISM", "CAMPYLOBACTER JEJUNI", "N"))),
    ]) == ""
    # reported right after the stool-occult token
    assert build_lab_summary([
        stool_cx_campy(), stool_quest(),
    ]) == "11/2026- stool occult neg, stool culture neg"


# ----------------------------------------------------------------------
# Stool parasites (ova & parasites, giardia, cryptosporidium) / C. diff toxin
# ----------------------------------------------------------------------

# The ova-and-parasite / antigen orders' result notes carry the
# negative result text on an empty item value.  Quest's Ova and
# Parasite order's reference-range line carries the negative text as
# well, so its smear lines decide (a positive report's lines name the
# organism seen instead).
OVA_Q_NEG_NOTES = (
    "OVA AND PARASITES, CONC AND PERM SMEAR\n"
    "  Test Status:       Final\n"
    "  CONCENTRATION 1:   No ova or parasites seen\n"
    "  TRICHROME 1:       No ova or parasites seen\n"
    "  Reference Range:   No ova or parasites seen."
)
OVA_Q_POS_NOTES = (
    "OVA AND PARASITES, CONC AND PERM SMEAR\n"
    "  Test Status:       Final\n"
    "  CONCENTRATION 1:   Giardia lamblia trophozoites seen\n"
    "  TRICHROME 1:       Giardia lamblia trophozoites seen\n"
    "  Reference Range:   No ova or parasites seen."
)
OVA_LC_NEG_NOTES = (
    "No ova, cysts, or parasites seen.\n"
    "One negative specimen does not rule out the possibility of a\n"
    "parasitic infection."
)
GIARDIA_NEG_NOTES = (
    "GIARDIA AG, EIA, STOOL\n"
    "  Giardia Result 1:  Not Detected"
)
CRYPTO_NEG_NOTES = (
    "CRYPTOSPORIDIUM AG, EIA\n"
    "  Cryptosporidium:   Not Detected"
)
CDIF_NEG_NOTES = (
    "CLOSTRIDIUM DIFFICILE TOXIN/GDH W/REFL TO PCR\n"
    "  Test Status:       Final\n"
    "  GDH Antigen:       Not Detected\n"
    "  Toxin A and B:     Not Detected\n"
    "  Reference Range:   Not Detected\n"
    "  Comment:           No toxigenic C. difficile detected"
)
CDIF_POS_NOTES = (
    "CLOSTRIDIUM DIFFICILE TOXIN/GDH W/REFL TO PCR\n"
    "  Test Status:       Final\n"
    "  GDH Antigen:       Detected\n"
    "  Toxin A and B:     Detected\n"
    "  Reference Range:   Not Detected\n"
    "  Comment:           Toxigenic C. difficile detected"
)


def stool_ova_quest(value="", flag="", notes=OVA_Q_NEG_NOTES,
                    result_date="2026-11-08"):
    return row(
        "Stool Ova and Parasite",
        result(("OVA AND PARASITES,$CONC AND PERM SMEAR",
                value, flag, "", notes)),
        result_date=result_date,
    )


def stool_ova_labcorp(value="", flag="", notes=OVA_LC_NEG_NOTES,
                      result_date="2026-11-08"):
    return row(
        "Stool Ova + Parasite Exam",
        result(
            ("Ova + Parasite Exam", "Final report", ""),
            ("Result 1", value, flag, "", notes),
        ),
        result_date=result_date,
    )


def stool_giardia(value="", flag="", notes=GIARDIA_NEG_NOTES,
                  result_date="2026-11-08"):
    return row(
        "Stool Giardia Ag, EIA",
        result(("GIARDIA AG, EIA, STOOL", value, flag, "", notes)),
        result_date=result_date,
    )


def stool_crypto(value="", flag="", notes=CRYPTO_NEG_NOTES,
                 result_date="2026-11-08"):
    return row(
        "Stool CRYPTOSPORIDIUM AG, EIA",
        result(("CRYPTOSPORIDIUM AG, EIA", value, flag, "", notes)),
        result_date=result_date,
    )


def stool_cdiff(value="", flag="", notes=CDIF_NEG_NOTES,
                result_date="2026-11-08"):
    return row(
        "Stool C-diff Toxin",
        result(("CLOSTRIDIUM DIFFICILE$TOXIN/GDH W/REFL TO PCR",
                value, flag, "", notes)),
        result_date=result_date,
    )


def test_stool_para():
    # negative: each layout -> stool O-P neg
    assert build_lab_summary([stool_ova_quest()]) == "11/2026- stool O-P neg"
    assert build_lab_summary([stool_ova_labcorp()]) == "11/2026- stool O-P neg"
    assert build_lab_summary([stool_giardia()]) == "11/2026- stool O-P neg"
    assert build_lab_summary([stool_crypto()]) == "11/2026- stool O-P neg"
    # all three orders negative -> one combined token
    assert build_lab_summary([
        stool_ova_quest(), stool_giardia(), stool_crypto(),
    ]) == "11/2026- stool O-P neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("stool giardia ag, eia", stool_giardia()["result"])
    ]) == "11/2026- stool O-P neg"
    # a positive order is reported alone (the yellow notes' labels),
    # not the negative members
    assert build_lab_summary([stool_ova_quest(notes=OVA_Q_POS_NOTES)]) \
        == "11/2026- O-P+"
    assert build_lab_summary([
        stool_ova_quest(notes=OVA_Q_POS_NOTES), stool_giardia(),
        stool_crypto(),
    ]) == "11/2026- O-P+"
    assert build_lab_summary([
        stool_ova_quest(),
        stool_giardia(notes="GIARDIA AG, EIA, STOOL\n"
                           "  Giardia Result 1:  Detected"),
        stool_crypto(),
    ]) == "11/2026- Giardia+"
    assert build_lab_summary([stool_crypto("Detected", "A")]) \
        == "11/2026- Cryptosporidium+"
    # pending: an empty value whose note carries no negative marker
    # (an in-process result) -> nothing
    assert build_lab_summary([
        stool_ova_quest(notes="Test Status: In Process"),
    ]) == ""
    # a lone negative next to a pending order reports nothing
    assert build_lab_summary([
        stool_ova_quest(), stool_giardia(notes=""),
    ]) == ""
    # the newest row wins, per order
    assert build_lab_summary([
        stool_ova_quest(),
        stool_ova_quest(notes=OVA_Q_POS_NOTES, result_date="2026-09-01"),
    ]) == "11/2026- stool O-P neg"
    assert build_lab_summary([
        stool_ova_quest(notes=OVA_Q_POS_NOTES),
        stool_ova_quest(result_date="2026-09-01"),
    ]) == "11/2026- O-P+"
    # reported right after the stool-occult / stool-culture tokens
    assert build_lab_summary([
        stool_quest(), stool_cx_campy(), stool_ova_quest(),
    ]) == ("11/2026- stool occult neg, stool culture neg, "
           "stool O-P neg")


def test_stool_cdiff():
    # negative: the note's Toxin A/B line / comment -> C diff neg
    assert build_lab_summary([stool_cdiff()]) == "11/2026- C diff neg"
    # a toxin-positive note -> C diff+
    assert build_lab_summary([stool_cdiff(notes=CDIF_POS_NOTES)]) \
        == "11/2026- C diff+"
    # a flagged empty value is a positive result too
    assert build_lab_summary([stool_cdiff(flag="A")]) == "11/2026- C diff+"
    # a GDH-positive / toxin-negative result is C diff neg
    assert build_lab_summary([
        stool_cdiff(notes=CDIF_NEG_NOTES.replace(
            "GDH Antigen:       Not Detected",
            "GDH Antigen:       Detected")),
    ]) == "11/2026- C diff neg"
    # pending / unrecognized -> nothing
    assert build_lab_summary([
        stool_cdiff(notes="Test Status: In Process"),
    ]) == ""
    # reported right after the stool-parasite tokens
    assert build_lab_summary([
        stool_ova_quest(), stool_giardia(), stool_cdiff(),
    ]) == "11/2026- stool O-P neg, C diff neg"


# ----------------------------------------------------------------------
# FA (B12/folate panel), ANA, ESR/CRP
# ----------------------------------------------------------------------

def b12_folate_quest(folate_value="14.6", folate_flag="N",
                     b12_value="418", b12_flag="N"):
    return row(
        "VITAMIN B12/FOLATE,$SERUM PANEL",
        result(
            ("FOLATE, SERUM", folate_value, folate_flag),
            ("VITAMIN B12", b12_value, b12_flag, "200-1100"),
        ),
    )


def b12_folate_labcorp(folate_value="6.1", folate_flag="",
                       folate_range=">3.0", b12_value="512", b12_flag=""):
    return row(
        "Vitamin B12 and Folate",
        result(
            ("Vitamin B12", b12_value, b12_flag, "232-1245"),
            ("Folate (Folic Acid), Serum",
             folate_value, folate_flag, folate_range),
        ),
    )


def test_fa():
    # normal folate (both vendors' panels) -> FA nl, next to the
    # panel's B12 value (rule 28)
    assert build_lab_summary([b12_folate_quest()]) == "11/2026- B12 418, FA nl"
    assert build_lab_summary([b12_folate_labcorp()]) == "11/2026- B12 512, FA nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("vitamin b12/folate,$serum panel", b12_folate_quest()["result"])
    ]) == "11/2026- B12 418, FA nl"
    # abnormal folate: Quest's item carries no range (plain value),
    # LabCorp's `>3.0` range yields the lower bound
    assert build_lab_summary([b12_folate_quest("2.4", "L")]) == "11/2026- B12 418, FA 2.4"
    assert build_lab_summary([b12_folate_labcorp("2.1", "L")]) == "11/2026- B12 512, FA 2.1(3)"
    # the value's trailing zeros are stripped
    assert build_lab_summary([b12_folate_quest("11.0", "H")]) == "11/2026- B12 418, FA 11"
    # an abnormal panel B12 carries its violated range limit, like the
    # standalone order's token (rule 28)
    assert build_lab_summary([
        b12_folate_quest(b12_value="1290", b12_flag="H")
    ]) == "11/2026- B12 1290(1100), FA nl"


def ana_quest(pattern_value="", pattern_flag="A",
              titer_value="", titer_flag="H"):
    return row(
        "ANTINUCLEAR ANTIBODIES   TITER AND PATTERN",
        result(
            ("ANA PATTERN", pattern_value, pattern_flag),
            ("ANA TITER", titer_value, titer_flag),
        ),
    )


def ana_labcorp(value="Negative", flag=""):
    return row(
        "Antinuclear Antibodies, IFA",
        result(("Antinuclear Antibodies, IFA", value, flag)),
    )


def test_ana():
    # positive: Quest's positive results can carry empty values with
    # an A/H flag (the titer sits in a note)
    assert build_lab_summary([ana_quest()]) == "11/2026- ANA+"
    # ... with the titer value present it is appended
    assert build_lab_summary([
        ana_quest(titer_value="1:80", titer_flag="H")
    ]) == "11/2026- ANA+ 1:80"
    # negative (both vendors) -> ANA nl
    assert build_lab_summary([
        ana_quest("NEGATIVE", "N", "NEGATIVE", "N")
    ]) == "11/2026- ANA nl"
    assert build_lab_summary([ana_labcorp()]) == "11/2026- ANA nl"
    # the `ANA Screen` spellings: LabCorp's `ANA Direct` item and
    # Quest's `ANA SCREEN, IFA` item (the `$` is part of the name)
    assert build_lab_summary([
        row("ANA Screen, IFA, W/Refl$titer and Pattern",
            result(("ANA SCREEN, IFA", "NEGATIVE", "N")))
    ]) == "11/2026- ANA nl"
    assert build_lab_summary([
        row("ANA Screen",
            result(("ANA Direct", "POSITIVE", "A")))
    ]) == "11/2026- ANA+"
    # LabCorp positive / titer values
    assert build_lab_summary([ana_labcorp("Positive", "A")]) == "11/2026- ANA+"
    assert build_lab_summary([ana_labcorp("1:40", "A")]) == "11/2026- ANA+ 1:40"
    # an unrecognized nonempty value -> nothing
    assert build_lab_summary([ana_labcorp("Pending")]) == ""
    # an unflagged non-titer value on an otherwise normal result -> nothing
    assert build_lab_summary([
        ana_quest("Fine speckled", "N", titer_flag="N")
    ]) == ""
    # the `ANA SCREEN, IFA` item of LabCorp's ANA/Rheumatoid panel
    # (whose RF / CCP items are rules 34a / b) is an ANA item too
    assert build_lab_summary([ana_rheum_panel()]) == (
        "11/2026- ANA nl, RF nl, Anti-CCP nl")
    assert build_lab_summary([
        ana_rheum_panel(ana=("POSITIVE", "A"))
    ]) == "11/2026- ANA+, RF nl, Anti-CCP nl"
    # the panel's RF / CCP items are not ANA items: an abnormal RF
    # does not flip a negative ANA
    assert build_lab_summary([
        ana_rheum_panel(rf=("25", "H"))
    ]) == "11/2026- ANA nl, RF 25(14), Anti-CCP nl"


def esr_quest(value="28", flag="H", rng="< OR = 20"):
    return row(
        "ESR",
        result(("SED RATE BY MODIFIED$WESTERGREN", value, flag, rng)),
    )


def crp_quest(value="14.8", flag="H", rng="<8.0"):
    return row("CRP", result(("C-REACTIVE PROTEIN", value, flag, rng)))


def crp_labcorp(value="14", flag="H", rng="0-10"):
    return row("CRP, Quant",
               result(("C-Reactive Protein, Quant", value, flag, rng)))


def test_esrcrp():
    # both present and normal -> ESR/CRP nl
    assert build_lab_summary([
        esr_quest(value="12", flag="N"),
        crp_quest(value="<3.0", flag="N"),
    ]) == "11/2026- ESR/CRP nl"
    # one abnormal, the other absent or normal
    assert build_lab_summary([esr_quest()]) == "11/2026- ESR 28(20)"
    assert build_lab_summary([crp_quest()]) == "11/2026- CRP 15(8)"
    assert build_lab_summary([
        esr_quest(value="12", flag="N"),
        crp_quest(),
    ]) == "11/2026- CRP 15(8)"
    assert build_lab_summary([
        esr_quest(),
        crp_quest(value="<3.0", flag="N"),
    ]) == "11/2026- ESR 28(20)"
    # both abnormal -> both tokens, ESR first
    assert build_lab_summary([esr_quest(), crp_quest()]) == (
        "11/2026- ESR 28(20), CRP 15(8)")
    # a lone normal test reports its own nl
    assert build_lab_summary([esr_quest(value="12", flag="N")]) == "11/2026- ESR nl"
    assert build_lab_summary([crp_quest(value="<3.0", flag="N")]) == "11/2026- CRP nl"
    # LabCorp CRP, Quant layout
    assert build_lab_summary([crp_labcorp()]) == "11/2026- CRP 14(10)"
    # CRP, Cardiac (the high-sensitivity cardiac CRP) is not the test
    assert build_lab_summary([
        row("CRP, Cardiac",
            result(("C-Reactive Protein, High Sensitivity", "1.2", "H", "0.00-3.00")))
    ]) == ""
    # an unparseable range -> plain value
    assert build_lab_summary([esr_quest(rng="")]) == "11/2026- ESR 28"
    # an abnormal flag with an empty value counts as no result
    assert build_lab_summary([esr_quest(value="", flag="A")]) == ""


# ----------------------------------------------------------------------
# RF / Anti-CCP / C3 / C4 / dsDNA (the autoimmune cluster)
# ----------------------------------------------------------------------

def rf_quest(value="<10", flag="N", rng="<14"):
    return row("RHEUMATOID FACTOR",
               result(("RHEUMATOID FACTOR", value, flag, rng)))


def ccp_quest(value="<16", flag="N", rng=""):
    # the item name carries a literal `$`; Quest's item has no
    # reference range
    return row("Anti-CCP Abs",
               result(("CYCLIC CITRULLINATED$PEPTIDE (CCP) AB (IGG)",
                      value, flag, rng)))


def ana_rheum_panel(rf=("<10", "N"), ccp=("<16", "N"),
                    ana=("NEGATIVE", "N")):
    """LabCorp's ANA/Rheumatoid panel: one order carries the RF, CCP
    and ANA items (plus an empty INTERPRETATION item); the ANA / RF /
    CCP items feed the summary (rules 33 / 34a / 34b)."""
    return row(
        "ANA SCR, IFA, W/REFL TITER/PATTERN/RHEUMATOID ARTHRITIS PANEL 1",
        result(
            ("RHEUMATOID FACTOR", *rf, "<14"),
            ("CYCLIC CITRULLINATED$PEPTIDE (CCP) AB (IGG)", *ccp),
            ("INTERPRETATION", "", ""),
            ("ANA SCREEN, IFA", *ana),
        ),
    )


def c3c4(c3_value="92", c3_flag="N", c3_rng="83-193",
         c4_value="19", c4_flag="N", c4_rng="15-57"):
    items = []
    if c3_value is not None:
        items.append(("COMPLEMENT COMPONENT C3C", c3_value, c3_flag, c3_rng))
    if c4_value is not None:
        items.append(("COMPLEMENT COMPONENT C4C", c4_value, c4_flag, c4_rng))
    return row("COMPLEMENT COMP C3 + C4", result(*items))


def dsdna(value="2", flag="N"):
    return row("Anti Ds-DNA",
               result(("DNA (DS) ANTIBODY", value, flag)))


def test_rf():
    # normal -> RF nl (the standalone order and LabCorp's ANA /
    # Rheumatoid panel)
    assert build_lab_summary([rf_quest()]) == "11/2026- RF nl"
    # the one-sided <14 range yields the violated limit
    assert build_lab_summary([rf_quest(value="25", flag="H")]) == "11/2026- RF 25(14)"
    # an unparseable range -> plain value
    assert build_lab_summary([rf_quest(value="25", flag="H", rng="")]) == "11/2026- RF 25"
    # an abnormal flag with an empty value -> nothing
    assert build_lab_summary([rf_quest(value="", flag="A")]) == ""


def test_ccp():
    # normal -> Anti-CCP nl (the standalone order and the panel)
    assert build_lab_summary([ccp_quest()]) == "11/2026- Anti-CCP nl"
    # the item carries no range -> plain value
    assert build_lab_summary([ccp_quest(value="45", flag="A")]) == "11/2026- Anti-CCP 45"
    # ... with a range the violated limit is appended
    assert build_lab_summary([ccp_quest(value="45", flag="A", rng="<25")]) == "11/2026- Anti-CCP 45(25)"
    # LabCorp's ANA/Rheumatoid panel feeds the ANA, RF and CCP
    # categories from the one order, in rule order
    assert build_lab_summary([ana_rheum_panel()]) == (
        "11/2026- ANA nl, RF nl, Anti-CCP nl")
    assert build_lab_summary([
        ana_rheum_panel(rf=("25", "H"), ccp=("45", "A"))
    ]) == "11/2026- ANA nl, RF 25(14), Anti-CCP 45"


def test_c3c4():
    # both present and normal -> C3/C4 nl
    assert build_lab_summary([c3c4()]) == "11/2026- C3/C4 nl"
    # one abnormal, the other normal -> the abnormal one alone
    assert build_lab_summary([c3c4(c3_value="70", c3_flag="L")]) == "11/2026- C3 70(83)"
    assert build_lab_summary([c3c4(c4_value="12", c4_flag="L")]) == "11/2026- C4 12(15)"
    # both abnormal -> both tokens, C3 first
    assert build_lab_summary([
        c3c4(c3_value="70", c3_flag="L", c4_value="12", c4_flag="L")
    ]) == "11/2026- C3 70(83), C4 12(15)"
    # an unparseable range -> plain value
    assert build_lab_summary([c3c4(c3_value="70", c3_flag="L", c3_rng="")]) == "11/2026- C3 70"
    # a normal member reports its own nl only when the other is absent
    assert build_lab_summary([c3c4(c4_value=None)]) == "11/2026- C3 nl"
    assert build_lab_summary([c3c4(c3_value=None)]) == "11/2026- C4 nl"
    # an abnormal flag with an empty value counts as absent
    assert build_lab_summary([c3c4(c3_value="", c3_flag="A")]) == "11/2026- C4 nl"


def test_dsdna():
    # negative: a numeric value with Quest's N flag, and LabCorp's ''
    # flag on a numeric value
    assert build_lab_summary([dsdna()]) == "11/2026- dsDNA neg"
    assert build_lab_summary([dsdna(value="1", flag="")]) == "11/2026- dsDNA neg"
    # a negative-set value
    assert build_lab_summary([dsdna(value="Negative", flag="")]) == "11/2026- dsDNA neg"
    # abnormal -> dsDNA+
    assert build_lab_summary([dsdna(value="120", flag="H")]) == "11/2026- dsDNA+"


def test_crp_cardiac():
    # normal -> hsCRP nl (20021's 0.64 in 0.00-3.00)
    assert build_lab_summary([
        row("CRP, Cardiac",
            result(("C-Reactive Protein, Cardiac", "0.64", "", "0.00-3.00",
                    "", "mg/L"))),
    ]) == "11/2026- hsCRP nl"
    # abnormal high -> hsCRP {val}(upper limit)
    assert build_lab_summary([
        row("CRP, Cardiac",
            result(("C-Reactive Protein, Cardiac", "5.2", "H", "0.00-3.00"))),
    ]) == "11/2026- hsCRP 5.2(3)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("crp, cardiac",
            result(("C-Reactive Protein, Cardiac", "0.64", "", "0.00-3.00"))),
    ]) == "11/2026- hsCRP nl"
    # the inflammatory CRP is the separate category of rule 34: both
    # are reported, hsCRP after the ESR/CRP token
    assert build_lab_summary([
        crp_quest(value="<3.0", flag="N"),
        row("CRP, Cardiac",
            result(("C-Reactive Protein, Cardiac", "0.64", "", "0.00-3.00"))),
    ]) == "11/2026- CRP nl, hsCRP nl"


def test_autoimmune_cluster_order():
    # the autoimmunity cluster appends after ANA / ESR-CRP in rule
    # order: RF, Anti-CCP, C3/C4, dsDNA
    assert build_lab_summary([
        dsdna(),
        c3c4(),
        ccp_quest(),
        rf_quest(),
        crp_quest(value="<3.0", flag="N"),
        esr_quest(value="12", flag="N"),
    ]) == "11/2026- ESR/CRP nl, RF nl, Anti-CCP nl, C3/C4 nl, dsDNA neg"
    # with an ANA row
    assert build_lab_summary([
        ana_labcorp(),
        dsdna(value="120", flag="H"),
        c3c4(c3_value="70", c3_flag="L"),
    ]) == "11/2026- ANA nl, C3 70(83), dsDNA+"
    # the panel row feeds the ANA, RF and CCP categories at once
    assert build_lab_summary([
        ana_rheum_panel(ana=("POSITIVE", "A")),
        c3c4(),
    ]) == "11/2026- ANA+, RF nl, Anti-CCP nl, C3/C4 nl"


# ----------------------------------------------------------------------
# HBV DNA
# ----------------------------------------------------------------------

def hbv_dna(value="NOT DETECTED", flag="N", units="Log IU/mL"):
    # the current Quest assay reports log10 IU/mL; older assays and
    # TNP rows carry plain IU/mL
    return row("Hep B DNA, PCR", json.dumps([
        {"itemName": "HEPATITIS B VIRUS DNA", "value": value,
         "units": units, "range": "NOT DETECTED", "flag": flag,
         "paramNotes": ""},
    ]))


def hbv_dna_labcorp(linear="1300", log="3.114"):
    # LabCorp's two-item layout: linear value first, log10 second,
    # no flags
    return row("Hep B Real-Time PCR, Quant", json.dumps([
        {"itemName": "HBV IU/mL", "value": linear,
         "units": "IU/mL", "range": "", "flag": "",
         "paramNotes": ""},
        {"itemName": "log10 HBV IU/mL", "value": log,
         "units": "log10 IU/mL", "range": "", "flag": "",
         "paramNotes": ""},
    ]))


def test_hbv_dna():
    # not detected (the vendor's value spellings) -> HBV DNA neg
    assert build_lab_summary([hbv_dna()]) == "11/2026- HBV DNA neg"
    assert build_lab_summary([hbv_dna("<1.00 NOT DETECTED")]) == "11/2026- HBV DNA neg"
    assert build_lab_summary([hbv_dna("<10 NOT DETECTED", units="IU/mL")]) == "11/2026- HBV DNA neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hep b dna, pcr", hbv_dna()["result"])
    ]) == "11/2026- HBV DNA neg"
    # detected below the quantification limit: on the current assay
    # the limit is a log10, so <1.00 renders as <10 (10**1.00 IU/mL);
    # a linear <10 (older assay) is kept as-is
    assert build_lab_summary([hbv_dna("<1.00 DETECTED", "A")]) == "11/2026- HBV DNA <10"
    assert build_lab_summary([hbv_dna("<10 DETECTED", "A", "IU/mL")]) == "11/2026- HBV DNA <10"
    # the current assay reports the log10 directly: the linear level
    # is reconstructed (10**2.62 = 417)
    assert build_lab_summary([hbv_dna("2.62", "H")]) == "11/2026- HBV DNA 417/2.62"
    assert build_lab_summary([hbv_dna("3.30", "H")]) == "11/2026- HBV DNA 1995/3.3"
    assert build_lab_summary([hbv_dna("1.63", "H")]) == "11/2026- HBV DNA 43/1.63"
    # a value without log units is treated as linear IU/mL
    assert build_lab_summary([hbv_dna("2000", "H", "IU/mL")]) == "11/2026- HBV DNA 2000/3.3"
    assert build_lab_summary([hbv_dna("147000", "H", "IU/mL")]) == "11/2026- HBV DNA 147000/5.17"
    assert build_lab_summary([hbv_dna("4450000", "H", "IU/mL")]) == "11/2026- HBV DNA 4450000/6.65"
    # pending / empty value -> nothing
    assert build_lab_summary([hbv_dna("TNP", units="IU/mL")]) == ""
    assert build_lab_summary([hbv_dna("", "N")]) == ""
    # LabCorp: linear value in the first item, log10 in a second
    # item, no flags
    assert build_lab_summary([hbv_dna_labcorp()]) == "11/2026- HBV DNA 1300/3.11"
    # below the quantification limit (leading <, no 'detected' text)
    assert build_lab_summary([hbv_dna_labcorp("<10", "TNP")]) == "11/2026- HBV DNA <10"
    # LabCorp's not-detected text
    assert build_lab_summary([hbv_dna_labcorp("HBV DNA not detected", "TNP")]) == "11/2026- HBV DNA neg"
    # the (Graph) order name matches too
    assert build_lab_summary([
        row("HBV RT PCR, Quant (Graph)", hbv_dna_labcorp()["result"])
    ]) == "11/2026- HBV DNA 1300/3.11"
    # the token follows the STD group
    assert build_lab_summary([*hep_trio(), hbv_dna()]) == (
        "11/2026- HBV/HCV neg, HBV DNA neg, HBV Ab neg")


# ----------------------------------------------------------------------
# Phos / zinc / lipase / AFP / CEA / CA 125
# ----------------------------------------------------------------------

def phos_labcorp(value="3.4", flag="", rng="3.0-4.3"):
    return row("Phosphorus, Serum",
               result(("Phosphorus, Serum", value, flag, rng)))


def test_phos():
    assert build_lab_summary([phos_labcorp()]) == "11/2026- Phos nl"
    assert build_lab_summary([phos_labcorp("5.5", "H")]) == "11/2026- Phos 5.5(4.3)"
    assert build_lab_summary([phos_labcorp("2.6", "L")]) == "11/2026- Phos 2.6(3)"
    # without a parsable range the token is plain
    assert build_lab_summary([phos_labcorp("5.5", "H", "")]) == "11/2026- Phos 5.5"


def zinc_labcorp(value="80", flag="", rng="44-115"):
    return row("Zinc, Plasma or Serum",
               result(("Zinc, Plasma or Serum", value, flag, rng)))


def zinc_quest(value="75", flag="N", rng="60-130"):
    return row("ZINC", result(("ZINC", value, flag, rng)))


def test_zinc():
    assert build_lab_summary([zinc_labcorp()]) == "11/2026- zinc nl"
    assert build_lab_summary([zinc_quest()]) == "11/2026- zinc nl"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("zinc, plasma or serum", zinc_labcorp()["result"])
    ]) == "11/2026- zinc nl"
    assert build_lab_summary([zinc_quest("50", "L")]) == "11/2026- zinc 50(60)"
    # ZINC, RBC (red-cell zinc) is a different test (its own
    # category, test_zinc_rbc): the row produces no serum / plasma
    # zinc token
    assert build_lab_summary([
        row("ZINC, RBC", result(("ZINC, RBC", "120", "H", "100-300")))
    ]) == "11/2026- zinc RBC 120(300)"


def test_zinc_rbc():
    # normal (the in-database Quest values 10.1 / 11.9 / 14.6 in
    # 9.0-14.7) -> zinc RBC nl
    assert build_lab_summary([
        row("ZINC, RBC", result(("ZINC, RBC", "10.1", "", "9.0-14.7")))
    ]) == "11/2026- zinc RBC nl"
    # abnormal high -> upper limit
    assert build_lab_summary([
        row("ZINC, RBC", result(("ZINC, RBC", "15.2", "H", "9.0-14.7")))
    ]) == "11/2026- zinc RBC 15.2(14.7)"
    # abnormal low -> lower limit
    assert build_lab_summary([
        row("ZINC, RBC", result(("ZINC, RBC", "8.2", "L", "9.0-14.7")))
    ]) == "11/2026- zinc RBC 8.2(9)"
    # both ordered: separate categories, each reporting its own row
    # (the serum / plasma token first, in the fixed token order)
    assert build_lab_summary([
        row("ZINC", result(("ZINC", "50", "L", "60-130"))),
        row("ZINC, RBC", result(("ZINC, RBC", "10.1", "", "9.0-14.7"))),
    ]) == "11/2026- zinc 50(60), zinc RBC nl"


def lipase_quest(value="73", flag="H", rng="7-60"):
    return row("LIPASE", result(("LIPASE", value, flag, rng)))


def lipase_labcorp(value="69", flag="", rng="13-78"):
    return row("Lipase, Serum",
               result(("Lipase, Serum", value, flag, rng)))


def test_lipase():
    assert build_lab_summary([lipase_quest()]) == "11/2026- lipase 73(60)"
    assert build_lab_summary([lipase_quest("32", "N")]) == "11/2026- lipase nl"
    assert build_lab_summary([lipase_labcorp()]) == "11/2026- lipase nl"
    assert build_lab_summary([lipase_labcorp("90", "H")]) == "11/2026- lipase 90(78)"


def afp_labcorp(value="2.1", flag="", rng="0.0-6.4"):
    return row("AFP, Serum, Tumor Marker",
               result(("AFP, Serum, Tumor Marker", value, flag, rng)))


def afp_quest(value="6.2", flag="H", rng="<6.1"):
    name = "ALPHA FETOPROTEIN,$TUMOR MARKER"
    return row(name, result((name, value, flag, rng)))


def cea_labcorp(value="2.7", flag="H"):
    return row("CEA", result(("CEA", value, flag, "See Note:")))


def ca125_labcorp(value="11", flag="N", rng="<35"):
    return row("CA 125", result(("CA 125", value, flag, rng)))


def test_tumor_markers():
    # AFP
    assert build_lab_summary([afp_labcorp()]) == "11/2026- AFP nl"
    assert build_lab_summary([afp_labcorp("7.2", "H")]) == "11/2026- AFP 7.2(6.4)"
    # Quest spells the order out (the `$` is part of the name); the
    # `<6.1` range yields the upper bound
    assert build_lab_summary([afp_quest()]) == "11/2026- AFP 6.2(6.1)"
    assert build_lab_summary([afp_quest("4.8", "N")]) == "11/2026- AFP nl"
    # CEA: the `See Note:` range is unparseable, so an abnormal
    # result is plain
    assert build_lab_summary([cea_labcorp("2.2", "N")]) == "11/2026- CEA nl"
    assert build_lab_summary([cea_labcorp()]) == "11/2026- CEA 2.7"
    # a below-limit CEA is normal
    assert build_lab_summary([cea_labcorp("<2.0", "N")]) == "11/2026- CEA nl"
    # CA 125: the `<35` range yields the upper bound
    assert build_lab_summary([ca125_labcorp()]) == "11/2026- CA 125 nl"
    assert build_lab_summary([ca125_labcorp("40", "H")]) == "11/2026- CA 125 40(35)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("ca 125", ca125_labcorp()["result"])
    ]) == "11/2026- CA 125 nl"


# ----------------------------------------------------------------------
# Estradiol
# ----------------------------------------------------------------------

def estradiol(value="120", flag="N"):
    # the in-house order carries no reference range
    return row("Estradiol", result(("ESTRADIOL", value, flag)))


def test_estradiol():
    assert build_lab_summary([estradiol()]) == "11/2026- Estradiol nl"
    # abnormal without a parsable range -> plain value
    assert build_lab_summary([estradiol("890", "H")]) == "11/2026- Estradiol 890"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("estradiol", estradiol()["result"])
    ]) == "11/2026- Estradiol nl"


# ----------------------------------------------------------------------
# Testosterone
# ----------------------------------------------------------------------

def ts_quest(total_value="347", total_flag="", total_range="250-1100",
                free_value="59.1", free_flag="", free_range="46.0-224.0"):
    # Quest's LC/MS/MS panel (18466's layout): the total and free
    # items plus the items the summary does not name
    return row("TESTOSTERONE, FREE,BIO$AND TOTAL, LC/MS/MS",
               result(("SEX HORMONE BINDING$GLOBULIN", "23", "", "22-77"),
                      ("TESTOSTERONE, FREE", free_value, free_flag, free_range),
                      ("TESTOSTERONE,BIOAVAILABLE", "121.5", "", "110.0-575.0"),
                      ("ALBUMIN,SERUM", "4.5", "", "3.6-5.1"),
                      ("TESTOSTERONE, TOTAL,$LC/MS/MS",
                       total_value, total_flag, total_range)))


def ts_labcorp(total_value="600", total_flag="",
                  free_value="9.0", free_flag=""):
    # LabCorp's Testosterone,Free and Total (21203's layout); the
    # reference ranges sit in the items' paramNotes, not their
    # range fields
    return row("Testosterone,Free and Total",
               result(("Testosterone, Serum", total_value, total_flag, ""),
                      ("Free Testosterone(Direct)", free_value, free_flag, "")))


def ts_labcorp_panel(total_value="273", total_flag="",
                        free_value="41", free_flag="L"):
    # LabCorp's Testosterone  Total/Free (12604's layout); the
    # reference ranges sit in the items' paramNotes
    return row("Testosterone  Total/Free",
               result(("% Free Testosterone (Dialysis)", "1.5", ""),
                      ("Free Testosterone, Serum", free_value, free_flag),
                      ("Bioavailable Testosterone, S", "94", "L"),
                      ("Testosterone, Serum (Total)", total_value, total_flag),
                      ("Sex Hormone Binding Globulin", "32.7", ""),
                      ("Bioavailable Testosterone, %", "34.6", "")))


def ts_total(value="493", flag="N", rng="250-827"):
    # Quest's standalone total order (20983's layout): a single item
    # named after the order (the trailing comma is part of the name)
    return row("TESTOSTERONE, TOTAL, MALES (ADULT),IA (REFL)",
               result(("TESTOSTERONE, TOTAL,", value, flag, rng)))


def test_testosterone():
    # both members normal -> the yellow notes' joined label
    # (18466's normal Quest panel)
    assert build_lab_summary([ts_quest()]) == \
        "11/2026- testosterone T/F nl"
    # 21203's normal LabCorp panel, the same label
    assert build_lab_summary([ts_labcorp()]) == \
        "11/2026- testosterone T/F nl"
    # abnormal members report their own tokens, total first (22336's
    # all-high panel; the violated upper limits in parentheses)
    assert build_lab_summary(
        [ts_quest(total_value="370", total_flag="H", total_range="2-45",
                     free_value="15.8", free_flag="H", free_range="0.2-5.0")]) == (
        "11/2026- testosterone T 370(45), testosterone F 15.8(5)")
    # one normal member keeps its nl token next to the abnormal one
    assert build_lab_summary(
        [ts_quest(free_value="15.8", free_flag="H", free_range="0.2-5.0")]) == (
        "11/2026- testosterone T nl, testosterone F 15.8(5)")
    assert build_lab_summary(
        [ts_quest(total_value="370", total_flag="H", total_range="2-45")]) == (
        "11/2026- testosterone F nl, testosterone T 370(45)")
    # 12604's LabCorp panel (total normal, free low): the ranges sit
    # in the items' paramNotes, so the abnormal member is plain
    assert build_lab_summary([ts_labcorp_panel()]) == \
        "11/2026- testosterone T nl, testosterone F 41"
    # a free item flagged abnormal with no value produces nothing
    # for that member
    assert build_lab_summary(
        [ts_quest(free_value="", free_flag="A")]) == \
        "11/2026- testosterone T nl"
    # the standalone total order always emits the value (20983's
    # normal 493), trailing zeros stripped
    assert build_lab_summary([ts_total()]) == "11/2026- testosterone 493"
    # ... normal or abnormal alike (no bound, the A1c / PSA style)
    assert build_lab_summary(
        [ts_total(value="200.0", flag="L", rng="250-827")]) == \
        "11/2026- testosterone 200"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("testosterone, total, males (adult),ia (refl)",
             ts_total()["result"])]) == "11/2026- testosterone 493"
    # pending total value -> nothing
    assert build_lab_summary([ts_total(value="", flag="")]) == ""


# ----------------------------------------------------------------------
# Cortisol / Prolactin / LH
# ----------------------------------------------------------------------

def cortisol(value="11.8", flag="N"):
    # Quest's CORTISOL, A.M. order; the reference range sits in the
    # item's paramNotes, not its range field
    return row("CORTISOL, A.M.",
               result(("CORTISOL, A.M.", value, flag, "",
                       "Reference Range\n8 a.m. (7-9 a.m.) "
                       "Specimen: 4.0-22.0")))


def prolactin(value="11.7", flag="N"):
    # Quest's PROLACTIN order; the reference range (females,
    # 3.0-30.0 ng/mL non-pregnant) sits in the item's paramNotes
    return row("PROLACTIN",
               result(("PROLACTIN", value, flag, "",
                       "Reference Range\n Females\n        "
                       "Non-pregnant        3.0-30.0")))


def lh_quest(value="5.6", flag="N", rng="2.4-12.6"):
    return row("LH, Serum", result(("LH", value, flag, rng)))


def lh_labcorp(value="5.6", flag="", rng="2.4-12.6"):
    return row("LH (Luteinizing Hormone)",
               result(("LH (Luteinizing Hormone)", value, flag, rng)))


def lh_inhouse(value="5.6", flag=""):
    # the in-house `LH hormone` order (22388's layout); the phase-
    # dependent reference range sits in the item's paramNotes, not
    # its range field
    return row("LH hormone",
               result(("LH", value, flag, "",
                       "Reference Range\nFollicular Phase  1.9-12.5\n"
                       "Mid-Cycle Peak    8.7-76.3\n"
                       "Luteal Phase      0.5-16.9\n"
                       "Postmenopausal    10.0-54.7")))


def test_cortisol():
    # normal (19444's 11.8) -> cortisol nl
    assert build_lab_summary([cortisol()]) == "11/2026- cortisol nl"
    # abnormal: the range sits in the paramNotes, so no bound
    assert build_lab_summary([cortisol("25.4", "H")]) == \
        "11/2026- cortisol 25.4"
    assert build_lab_summary([cortisol("3.1", "L")]) == \
        "11/2026- cortisol 3.1"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("cortisol, a.m.", cortisol()["result"])]) == \
        "11/2026- cortisol nl"
    # pending value on an abnormal result -> nothing
    assert build_lab_summary([cortisol("", "A")]) == ""


def test_prolactin():
    # normal (17478's / 20936's) -> prolactin nl
    assert build_lab_summary([prolactin()]) == "11/2026- prolactin nl"
    # abnormal: no bound (the range sits in the paramNotes)
    assert build_lab_summary([prolactin("200", "H")]) == \
        "11/2026- prolactin 200"
    assert build_lab_summary([prolactin("1.5", "L")]) == \
        "11/2026- prolactin 1.5"
    # name matching is case-insensitive
    assert build_lab_summary(
        [row("prolactin", prolactin()["result"])]) == \
        "11/2026- prolactin nl"


def test_lh():
    # normal (all three layouts) -> LH nl (20779's in-house 6.9)
    assert build_lab_summary([lh_quest()]) == "11/2026- LH nl"
    assert build_lab_summary([lh_labcorp()]) == "11/2026- LH nl"
    assert build_lab_summary([lh_inhouse()]) == "11/2026- LH nl"
    # 22388's mid-cycle high (81.5): no range field, so the token
    # is plain (the yellow notes parse the mid-cycle peak range out
    # of the paramNotes: `LH 82++(76)`); the value renders as an
    # integer, matching the note's `82`
    assert build_lab_summary([lh_inhouse("81.5", "H")]) == \
        "11/2026- LH 82"
    # abnormal high -> upper limit; low -> lower limit (the vendor
    # layouts carry their ranges)
    assert build_lab_summary([lh_quest("15.2", "H")]) == \
        "11/2026- LH 15(12.6)"
    assert build_lab_summary([lh_quest("2", "L")]) == "11/2026- LH 2(2.4)"
    # name matching is case-insensitive (both the in-house and the
    # Quest order names)
    assert build_lab_summary(
        [row("lh hormone", lh_inhouse()["result"])]) == "11/2026- LH nl"
    assert build_lab_summary(
        [row("lh, serum", lh_quest()["result"])]) == "11/2026- LH nl"
    # pending value on an abnormal result -> nothing
    assert build_lab_summary([lh_inhouse("", "A")]) == ""


# ----------------------------------------------------------------------
# Progesterone
# ----------------------------------------------------------------------

def test_progest():
    # normal -> Progesterone nl (20727's 4.7; no range field -- the
    # phase-dependent range sits in the item's paramNotes; the notes
    # write a normal `Progesterone nml`)
    assert build_lab_summary([
        row("Progesterone", result(("PROGESTERONE", "4.7", "N")))
    ]) == "11/2026- Progesterone nl"
    # a luteal-phase value is not flagged either (20872's 18.6)
    assert build_lab_summary([
        row("Progesterone", result(("PROGESTERONE", "18.6", "N")))
    ]) == "11/2026- Progesterone nl"
    # an abnormal flag without a parsable range -> plain value, written
    # raw like LH (17764's `Progesterone <0.5`)
    assert build_lab_summary([
        row("Progesterone", result(("PROGESTERONE", "<0.5", "A")))
    ]) == "11/2026- Progesterone <0.5"
    # a flagged numeric value is written raw too (no integer
    # rendering, unlike LH)
    assert build_lab_summary([
        row("Progesterone", result(("PROGESTERONE", "35.1", "H")))
    ]) == "11/2026- Progesterone 35.1"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("progesterone", result(("PROGESTERONE", "4.7", "N")))
    ]) == "11/2026- Progesterone nl"


# ----------------------------------------------------------------------
# AMH (anti-Mullerian hormone)
# ----------------------------------------------------------------------

def amh_inhouse(value="3.90", flag="N", rng="0.18-5.68", **kw):
    return row(
        "Infertility _ AMH _ Anti-Mullerian hormone",
        result(("ANTI-MULLERIAN HORMONE (AMH), FEMALE", value, flag, rng)),
        **kw,
    )


def amh_labcorp(value="3.05", flag="", **kw):
    return row(
        "AMH _ Anti-Mullerian hormone",
        result(("Anti-Mullerian Hormone (AMH)", value, flag)),
        **kw,
    )


def test_amh():
    # normal (14966's 5.42, 18977's 3.90; the yellow notes write a
    # normal `AMH nml`) -> AMH nl
    assert build_lab_summary(
        [amh_inhouse("5.42", "N", "0.36-10.07")]) == "11/2026- AMH nl"
    assert build_lab_summary([amh_inhouse()]) == "11/2026- AMH nl"
    # LabCorp's layout (no range field, the age-dependent range in
    # the item's paramNotes) -> AMH nl (20779's 3.05)
    assert build_lab_summary([amh_labcorp()]) == "11/2026- AMH nl"
    # abnormal: the age-dependent range on the in-house item's range
    # field gives a bound (high -> upper limit, low -> lower limit;
    # the value's trailing zeros stripped, 7.20 -> 7.2)
    assert build_lab_summary([amh_inhouse("7.20", "H")]) == \
        "11/2026- AMH 7.2(5.68)"
    assert build_lab_summary([amh_inhouse("0.1", "L")]) == \
        "11/2026- AMH 0.1(0.18)"
    # LabCorp's abnormal: the range sits in the paramNotes, so the
    # token is plain (like the LH of rule 4d)
    assert build_lab_summary([amh_labcorp("25", "H")]) == \
        "11/2026- AMH 25"
    # name matching is case-insensitive (both vendors' order names)
    assert build_lab_summary([
        row("infertility _ amh _ anti-mullerian hormone",
            amh_inhouse()["result"])
    ]) == "11/2026- AMH nl"
    assert build_lab_summary(
        [row("amh _ anti-mullerian hormone", amh_labcorp()["result"])]) == \
        "11/2026- AMH nl"
    # pending value on an abnormal result -> nothing
    assert build_lab_summary([amh_inhouse("", "A")]) == ""


# ----------------------------------------------------------------------
# INR / PT, PTT, BNP
# ----------------------------------------------------------------------

def inr_order(pt_value="12.0", pt_flag="N", pt_range="",
              inr_value="1.0", inr_flag="N", inr_range=""):
    # the `INR` order: a PT and an INR item
    return row("INR", result(("PT", pt_value, pt_flag, pt_range),
                             ("INR", inr_value, inr_flag, inr_range)))


def inrpt_order(inr_value="1.0", inr_flag="N",
                pt_value="12", pt_flag="N", pt_range=""):
    # the `INR /PT` order: INR + Prothrombin Time
    return row("INR /PT", result(("INR", inr_value, inr_flag),
                                 ("Prothrombin Time", pt_value, pt_flag,
                                  pt_range)))


def ptt_order(item="PARTIAL THROMBOPLASTIN TIME, ACTIVATED",
              value="29.9", flag="", rng="24.1-34.5"):
    return row("PTT", result((item, value, flag, rng)))


def coag_combined(pt=("PT", "12.0", "N", "11-13.4"),
                  inr=("INR", "1.0", "N"),
                  ptt=("PARTIAL THROMBOPLASTIN TIME, ACTIVATED", "29.9",
                       "", "24.1-34.5")):
    # the in-house combined prothrombin / partial-thromboplastin order
    return row("PROTHROMBIN W/INR + PARTIAL THROMBOPLASTIN TIMES",
               result(pt, inr, ptt))


def bnp_labcorp(value="85", flag="", rng="0-100"):
    return row("BNP",
               result(("B-Type Natriuretic Peptide", value, flag, rng)))


def bnp_quest(value="85", flag="N", rng="0-100"):
    # Quest's item name carries a literal `$`
    return row("BNP",
               result(("B TYPE NATRIURETIC$PEPTIDE (BNP)", value, flag, rng)))


def test_inrpt():
    # both items present and normal -> INR/PT nl (both layouts)
    assert build_lab_summary([inr_order()]) == "11/2026- INR/PT nl"
    assert build_lab_summary([inrpt_order()]) == "11/2026- INR/PT nl"
    # one token per abnormal item, INR first; the INR item usually
    # carries no range, so it renders plain
    assert build_lab_summary([
        inr_order(pt_value="15.0", pt_flag="H", pt_range="11-13.4",
                  inr_value="1.4", inr_flag="H")
    ]) == "11/2026- INR 1.4, PT 15(13.4)"
    assert build_lab_summary([inr_order(inr_value="1.4", inr_flag="H")]) \
        == "11/2026- INR 1.4"
    assert build_lab_summary([
        inr_order(pt_value="15.0", pt_flag="H", pt_range="11-13.4")
    ]) == "11/2026- PT 15(13.4)"
    # the `INR /PT` layout's Prothrombin Time item renders as PT
    assert build_lab_summary([
        inrpt_order(pt_value="15.0", pt_flag="H", pt_range="11-13.4")
    ]) == "11/2026- PT 15(13.4)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("inr", inr_order()["result"])
    ]) == "11/2026- INR/PT nl"


def test_ptt():
    # Quest's item name carries a literal `$` in the middle
    assert build_lab_summary([
        ptt_order("PARTIAL THROMBOPLASTIN$TIME, ACTIVATED")
    ]) == "11/2026- PTT nl"
    assert build_lab_summary([
        ptt_order("PARTIAL THROMBOPLASTIN$TIME, ACTIVATED", "55", "H")
    ]) == "11/2026- PTT 55(34.5)"
    # LabCorp's spelling
    assert build_lab_summary([
        ptt_order("PARTIAL THROMBOPLASTIN TIME, ACTIVATED", "55", "H")
    ]) == "11/2026- PTT 55(34.5)"


def test_bnp():
    assert build_lab_summary([bnp_labcorp()]) == "11/2026- BNP nl"
    assert build_lab_summary([bnp_quest()]) == "11/2026- BNP nl"
    assert build_lab_summary([bnp_labcorp("450", "H")]) == "11/2026- BNP 450(100)"
    assert build_lab_summary([bnp_quest("450", "H")]) == "11/2026- BNP 450(100)"


def test_coag_combined():
    # the combined order feeds both the INR/PT and the PTT tokens
    assert build_lab_summary([coag_combined()]) == "11/2026- INR/PT nl, PTT nl"
    assert build_lab_summary([
        coag_combined(
            pt=("PT", "13.9", "H", "11-13.4"),
            ptt=("PARTIAL THROMBOPLASTIN TIME, ACTIVATED", "40", "H",
                 "24.1-34.5"))
    ]) == "11/2026- PT 13.9(13.4), PTT 40(34.5)"


# ----------------------------------------------------------------------
# Hep B eAg / HBcAb
# ----------------------------------------------------------------------

def eag_quest(value="NON-REACTIVE", flag="N"):
    return row("Hep B eAg",
               result(("HEPATITIS BE ANTIGEN", value, flag, "NON-REACTIVE")))


def eag_labcorp(value="Negative", flag=""):
    return row("Hep Be Ag", result(("Hep Be Ag", value, flag, "Negative")))


def hbcab_quest(value="NON-REACTIVE", flag="N"):
    return row("Hep B core Ab",
               result(("HEPATITIS B CORE AB TOTAL", value, flag,
                       "NON-REACTIVE")))


def test_eag():
    assert build_lab_summary([eag_quest()]) == "11/2026- eAg neg"
    assert build_lab_summary([eag_labcorp()]) == "11/2026- eAg neg"
    assert build_lab_summary([eag_quest("REACTIVE", "A")]) == "11/2026- eAg+"
    assert build_lab_summary([eag_labcorp("Positive", "A")]) == "11/2026- eAg+"
    # a pending / not-performed value (LabCorp's TNP) produces nothing
    assert build_lab_summary([
        row("Hep Be Ag", result(("Hep Be Ag", "TNP", "", "Negative")))
    ]) == ""


def test_hbcab():
    assert build_lab_summary([hbcab_quest()]) == "11/2026- HBcAb neg"
    assert build_lab_summary([hbcab_quest("REACTIVE", "A")]) == "11/2026- HBcAb+"
    assert build_lab_summary([
        row("Hep B Core Ab, Tot",
            result(("Hep B Core Ab, Tot", "Positive", "A", "Negative")))
    ]) == "11/2026- HBcAb+"


# ----------------------------------------------------------------------
# HDV / HTLV
# ----------------------------------------------------------------------

def hdv_quest(value="NEGATIVE", flag="N"):
    return row("Hep D antibody",
               result(("HEPATITIS D ANTIBODY,", value, flag)))


def hdv_labcorp(value="Non Reactive", flag=""):
    return row("Hepatitis D Antibody, IgG/IgM",
               result(("HDV Antibody, IgG/IgM", value, flag, "Non Reactive")))


def test_hdv():
    # both vendors' layouts, negative by default (21070 / 19506's
    # notes: HDV/eAg/HIV neg)
    assert build_lab_summary([hdv_quest()]) == "11/2026- HDV neg"
    assert build_lab_summary([hdv_labcorp()]) == "11/2026- HDV neg"
    # a positive result is its own token
    assert build_lab_summary([hdv_quest("POSITIVE", "A")]) == "11/2026- HDV+"
    assert build_lab_summary([hdv_labcorp("Reactive", "A")]) == "11/2026- HDV+"
    # a pending / empty value produces nothing
    assert build_lab_summary([hdv_labcorp("", "")]) == ""


def test_hb_elec_htlv():
    # both negative -> the notes' joined token (20779's note: Hb
    # electrophoresis/HTLV neg)
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Negative", ""))),
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "Negative", "",
                    "Negative"))),
    ]) == "11/2026- Hb electrophoresis/HTLV neg"
    # standalone HTLV negative -> HTLV neg (the old rule 24b shape)
    assert build_lab_summary([
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "Negative", "",
                    "Negative")))
    ]) == "11/2026- HTLV neg"
    # standalone Hb electrophoresis negative -> its own token
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Negative", "")))
    ]) == "11/2026- Hb electrophoresis neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Negative", ""))),
        row("htlv-i/ii antibodies, qual",
            result(("HTLV-I/II Antibodies, Qual", "Negative", ""))),
    ]) == "11/2026- Hb electrophoresis/HTLV neg"
    # a positive member is its own token right after the negative
    # members' one
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Positive", "A"))),
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "Negative", ""))),
    ]) == "11/2026- HTLV neg, Hb electrophoresis+"
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Negative", ""))),
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "Positive", "A"))),
    ]) == "11/2026- Hb electrophoresis neg, HTLV+"
    # both positive -> the two tokens in member order
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "Positive", "A"))),
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "Positive", "A"))),
    ]) == "11/2026- Hb electrophoresis+, HTLV+"
    # a pending / empty value produces nothing
    assert build_lab_summary([
        row("Hb electrophoresis",
            result(("Hemoglobin (Hgb) Solubility", "", ""))),
        row("HTLV-I/II Antibodies, Qual",
            result(("HTLV-I/II Antibodies, Qual", "", ""))),
    ]) == ""


# ----------------------------------------------------------------------
# HCV RNA / HBV Ab (surface Ab screen + titer)
# ----------------------------------------------------------------------

def hcv_rna_quest(value="<15 NOT DETECTED", flag="N",
                  log_value="<1.18 NOT DETECTED", log_flag="N"):
    """Quest's HCV RNA quant order, linear item first (22487's /
    19926's layout, with the `COMMENT` note item)."""
    return row(
        "HCV RNA, QUANTITATIVE$REAL TIME PCR",
        result(
            ("HCV RNA, QUANTITATIVE$REAL TIME PCR", value, flag),
            ("HCV RNA, QUANTITATIVE$REAL TIME PCR", log_value,
             log_flag),
            ("COMMENT", "", ""),
        ),
    )


def hcv_rna_labcorp(value="HCV Not Detected", flag=""):
    """LabCorp's HCV RNA quant order (22044's layout)."""
    return row(
        "HCV RT-PCR, Quant (Non-Graph)",
        result(("Hepatitis C Quantitation", value, flag),
               ("Test Information:", "", "")),
    )


def test_hcv_rna():
    # not detected -> HCV RNA neg (both vendors' layouts)
    assert build_lab_summary([hcv_rna_quest()]) == "11/2026- HCV RNA neg"
    assert build_lab_summary([hcv_rna_labcorp()]) == "11/2026- HCV RNA neg"
    # the plain-spelling Quest order is the category too; a detected
    # linear level pairs with its computed log10, like the HBV DNA
    # token (19926's result: 53 IU/mL = 1.72 log)
    assert build_lab_summary([
        row("HCV RNA, QUANTITATIVE REAL TIME PCR",
            result(("HCV RNA, QUANTITATIVE REAL TIME PCR", "53", "H"),
                   ("HCV RNA, QUANTITATIVE REAL TIME PCR", "1.72",
                    "H"),
                   ("COMMENT", "", "")))
    ]) == "11/2026- HCV RNA 53/1.72"
    assert build_lab_summary(
        [hcv_rna_quest(value="53", flag="H", log_value="1.72",
                       log_flag="H")]) == "11/2026- HCV RNA 53/1.72"
    # a pending / empty value produces nothing
    assert build_lab_summary([hcv_rna_quest(value="TNP", flag="")]) == ""
    # the HCV Ab screen with reflex to RNA is not an RNA order
    assert build_lab_summary([
        row("HEPATITIS C AB W/RFL RNA, PCR W/RFL GENOTYPE,LIPA",
            result(("HEPATITIS C ANTIBODY", "NON-REACTIVE", "N")))
    ]) == ""


def hbsabq_labcorp(value="117.0", flag=""):
    """LabCorp's Hep B surface-Ab titer (22119's layout)."""
    return row("Hep B Surf Ab Quant",
               result(("Hepatitis B Surf Ab Quant", value, flag,
                       "Immunity>10")))


def hbsab_inhouse(value="REACTIVE", flag="A"):
    """The in-house `Hep B surface Ab` screen (12967's layout)."""
    return row("Hep B surface Ab",
               result(("HEPATITIS B SURFACE$ANTIBODY QL", value, flag,
                       "NON-REACTIVE")))


def test_hbsabq():
    # an immune titer (above the 10 mIU/mL cutoff) -> HBV Ab+
    assert build_lab_summary([hbsabq_labcorp()]) == "11/2026- HBV Ab+"
    assert build_lab_summary([hbsabq_labcorp(value="5572.0")]) == \
        "11/2026- HBV Ab+"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("hep b surf ab quant",
            result(("Hepatitis B Surf Ab Quant", "117.0", "")))
    ]) == "11/2026- HBV Ab+"
    # a non-immune titer (at / below the cutoff) -> HBV Ab neg
    # (the notes' `need HBV vacc`)
    assert build_lab_summary(
        [hbsabq_labcorp(value="<3.5", flag="L")]) == "11/2026- HBV Ab neg"
    assert build_lab_summary(
        [hbsabq_labcorp(value="8.1", flag="L")]) == "11/2026- HBV Ab neg"
    # a pending / empty value produces nothing
    assert build_lab_summary([hbsabq_labcorp(value="", flag="")]) == ""


def test_hbsab_screen():
    # the qualitative screen is reported too: reactive -> HBV Ab+
    # (12967's row: a REACTIVE screen on a chronic-HBV patient)
    assert build_lab_summary([hbsab_inhouse()]) == "11/2026- HBV Ab+"
    # non-reactive -> HBV Ab neg
    assert build_lab_summary(
        [hbsab_inhouse(value="NON-REACTIVE", flag="N")]) == \
        "11/2026- HBV Ab neg"
    # LabCorp's qualitative layout (Reactive / Non Reactive value, no
    # flag): the value decides
    assert build_lab_summary([
        row("Hep B Surface Ab",
            result(("Hep B Surface Ab, Qual", "Reactive", "")))
    ]) == "11/2026- HBV Ab+"
    assert build_lab_summary([
        row("Hep B Surface Ab",
            result(("Hep B Surface Ab, Qual", "Non Reactive", "")))
    ]) == "11/2026- HBV Ab neg"
    # the BORDERLINE band is undetermined -> nothing
    assert build_lab_summary(
        [hbsab_inhouse(value="BORDERLINE", flag="A")]) == ""
    # a pending / empty value produces nothing
    assert build_lab_summary(
        [hbsab_inhouse(value="", flag="")]) == ""
    # the titer order decides when both are present (the definitive
    # follow-up of the screen)
    assert build_lab_summary(
        [hbsabq_labcorp(value="8.1", flag="L"),
         hbsab_inhouse()]) == "11/2026- HBV Ab neg"
    # a reactive screen inside a normal trio keeps the HBV/HCV neg
    # group and reports HBV Ab+ (22457's layout)
    assert build_lab_summary(
        hep_trio()[:2] + [row("Hep B Surface Ab",
                              result(("Hep B Surface Ab, Qual",
                                      "Reactive", "")))]
    ) == "11/2026- HBV/HCV neg, HBV Ab+"


# ----------------------------------------------------------------------
# CBC eosinophils (the absolute item only)
# ----------------------------------------------------------------------

def test_cbc_eos():
    # Quest's ABSOLUTE EOSINOPHILS, range 15-500
    assert build_lab_summary([
        row("CBC (INCLUDES DIFF/PLT)",
            result(("ABSOLUTE EOSINOPHILS", "526", "H", "15-500")))
    ]) == "11/2026- Eos 526(500)"
    # LabCorp's Eos (Absolute), range 0.0-0.4 (trailing zeros stripped)
    assert build_lab_summary([
        row("CBC With Differential/Platelet",
            result(("Eos (Absolute)", "0.5", "H", "0.0-0.4")))
    ]) == "11/2026- Eos 0.5(0.4)"
    # a normal item produces nothing
    assert build_lab_summary([
        row("CBC (INCLUDES DIFF/PLT)",
            result(("ABSOLUTE EOSINOPHILS", "210", "N", "15-500")))
    ]) == ""
    # the percentage eosinophil items carry no usable range and are not it
    assert build_lab_summary([
        row("CBC (INCLUDES DIFF/PLT)",
            result(("EOSINOPHILS", "9", "H", "0-5")))
    ]) == ""
    assert build_lab_summary([
        row("CBC With Differential/Platelet",
            result(("Eos", "9", "H", "0-5")))
    ]) == ""


# ----------------------------------------------------------------------
# liver panel electrolytes
# ----------------------------------------------------------------------

def test_liver_electrolytes():
    # one token per abnormal item, in the order Ca / Na / Cl / K
    assert build_lab_summary([
        row("CMP", result(
            ("AST", "20", "N", "10-35"),
            ("ALT", "25", "N", "9-46"),
            ("SODIUM", "134", "L", "136-145"),
            ("POTASSIUM", "6.0", "H", "3.5-5.1"),
            ("CHLORIDE", "109", "H", "98-107"),
            ("CALCIUM", "10.3", "H", "8.6-10.2")))
    ]) == "11/2026- Ca 10.3(10.2), Na 134(136), Cl 109(107), K 6(5.1)"
    # LabCorp's in-house-CMP item spellings
    assert build_lab_summary([
        row("CMP", result(
            ("AST (SGOT)", "20", "N", "10-35"),
            ("Sodium, Serum", "134", "L", "136-145"),
            ("Potassium, Serum", "6.0", "H", "3.5-5.1")))
    ]) == "11/2026- Na 134(136), K 6(5.1)"
    # normal AST / ALT and electrolytes produce no tokens of their
    # own (only the fixture's high glucose, with no A1c row)
    assert build_lab_summary([cmp_quest(ast_flag="N", alt_flag="N")]) == \
        "11/2026- Glu 101(99)"


# ----------------------------------------------------------------------
# amylase / CA 19-9 / LDH
# ----------------------------------------------------------------------

def amylase(value="90", flag="N", rng="30-110"):
    return row("AMYLASE", result(("AMYLASE", value, flag, rng)))


def ca199(value="12", flag="N", rng="0-35"):
    return row("CA 19-9", result(("CA 19-9", value, flag, rng)))


def ldh_quest(value="190", flag="N", rng="98-175"):
    # Quest's single item is named LD
    return row("LDH", result(("LD", value, flag, rng)))


def ldh_labcorp(value="190", flag="", rng="120-246"):
    return row("LDH", result(("LDH", value, flag, rng)))


def test_amylase():
    assert build_lab_summary([amylase()]) == "11/2026- amylase nl"
    assert build_lab_summary([amylase("220", "H")]) == "11/2026- amylase 220(110)"


def test_ca199():
    # the 0-35 / <34 ranges yield the upper bound, like CEA
    assert build_lab_summary([ca199()]) == "11/2026- CA 19-9 nl"
    assert build_lab_summary([ca199("60.5", "H")]) == "11/2026- CA 19-9 60.5(35)"
    assert build_lab_summary([
        ca199("50", "H", "<34")
    ]) == "11/2026- CA 19-9 50(34)"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("ca 19-9", ca199()["result"])
    ]) == "11/2026- CA 19-9 nl"


def test_ldh():
    # the item is Quest's LD or LabCorp's LDH
    assert build_lab_summary([ldh_quest()]) == "11/2026- LDH nl"
    assert build_lab_summary([ldh_quest("240", "H")]) == "11/2026- LDH 240(175)"
    assert build_lab_summary([ldh_labcorp()]) == "11/2026- LDH nl"
    assert build_lab_summary([ldh_labcorp("260", "H")]) == "11/2026- LDH 260(246)"


# ----------------------------------------------------------------------
# rows with no lab/result are ignored
# ----------------------------------------------------------------------

def test_rows_without_result():
    # imaging rows carry no result JSON
    assert build_lab_summary([
        row("CT CARDIAC SCORING"),
        row("CT CHEST W/O CONTRAST (HIGH RES.)", result_date="2026-10-15",
            date="2026-09-29"),
    ]) == ""
    # empty / invalid / empty-array results are all ignored
    assert build_lab_summary([row("CMP", result_text="")]) == ""
    assert build_lab_summary([row("CMP", result_text="not json")]) == ""
    assert build_lab_summary([row("CMP", result_text="[]")]) == ""
    assert build_lab_summary([row("CMP", result_text='"just a string"')]) == ""
    # categories with no rule (the CMP's electrolytes, ...) contribute
    # nothing, even when abnormal; a negative hep A total Ab and a
    # negative hep A IgM are handled but produce no token (a CMP row's
    # BUN is reported when abnormal -- this row's BUN 20 is normal, and
    # the row's glucose only shows up when an A1c row is present, so
    # this patient's CMP contributes nothing)
    assert build_lab_summary([
        row("CMP", result(
            ("Glucose, Serum", "97", ""), ("BUN", "20", ""))),
        row("Hep A Ab, Total", result(("Hep A Ab, Total", "Negative", ""))),
        row("Hep A Ab, IgM", result(("Hep A Ab, IgM", "Negative", ""))),
        row("QuantiFERON-TB Gold Plus",
            result(("QuantiFERON Criteria", "", ""))),
    ]) == ""
    # an ignored row with no result does not block a real lab row
    assert build_lab_summary([
        row("CT CARDIAC SCORING", result_date="2026-10-15"),
        ua_labcorp(result_date="2026-11-07"),
    ]) == "11/2026- UA nl"


# ----------------------------------------------------------------------
# leading mm/yyyy date
# ----------------------------------------------------------------------

def test_date():
    assert build_lab_summary(
        [ua_labcorp(result_date="2026-11-07")]) == "11/2026- UA nl"
    # zero-padded month
    assert build_lab_summary(
        [ua_labcorp(result_date="2026-01-15")]) == "01/2026- UA nl"
    # unparseable/missing result_date falls back to the order date
    assert build_lab_summary(
        [ua_labcorp(result_date=None)]) == "10/2026- UA nl"
    assert build_lab_summary(
        [ua_labcorp(result_date="not a date")]) == "10/2026- UA nl"
    # no parseable date at all: tokens without a prefix
    assert build_lab_summary(
        [ua_labcorp(result_date=None, date=None)]) == "UA nl"


# ----------------------------------------------------------------------
# result ordering
# ----------------------------------------------------------------------

def test_result_ordering():
    # per category the newest row wins: an older abnormal UA must not
    # override a newer normal one
    assert build_lab_summary([
        ua_labcorp(result_date="2026-11-07"),
        ua_labcorp(result_date="2026-10-01"),
    ]) == "11/2026- UA nl"
    data = json.loads(ua_labcorp(result_date="2026-10-01")["result"])
    for item in data:
        if item["itemName"] == "Protein":
            item.update(value="30", flag="A")
    assert build_lab_summary([
        ua_labcorp(result_date="2026-11-07"),
        row("UA, Routine", json.dumps(data), result_date="2026-10-01"),
    ]) == "11/2026- UA nl"
    # ... and the reverse (newest abnormal) does report it
    assert build_lab_summary([
        row("UA, Routine", json.dumps(data), result_date="2026-11-07"),
        ua_labcorp(result_date="2026-10-01"),
    ]) == "11/2026- UA protein 30"

    # the function trusts the caller's order: the first matching row is
    # the newest one, even if its result_date looks older
    assert build_lab_summary([
        ua_labcorp(result_date="2026-10-01"),
        row("UA, Routine", json.dumps(data), result_date="2026-11-07"),
    ]) == "10/2026- UA nl"

    # the leading date comes from the newest row with a usable result,
    # and each category picks up its own newest row
    assert build_lab_summary([
        ua_labcorp(result_date="2026-11-07"),
        row("TSH reflex to T4F", result(("TSH", "2.460", "")),
            result_date="2026-10-20"),
    ]) == "11/2026- UA nl, TSH 2.5"

    # tokens come out in the fixed order no matter what order the rows
    # were given in (newest-first within each category)
    rows = [
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "32", "N"))),
        pth_quest(),
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "22.8", ""))),
        lipid_labcorp(),
        row("Uric Acid, Serum", result(("Uric Acid, Serum", "6.8", ""))),
        psa_quest(),
        phos_labcorp("5.5", "H"),
        zinc_quest("50", "L"),
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", "204.00", "N"))),
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A"))),
        iron_labcorp(),
        row("Vitamin B12", result(("Vitamin B12", "1285", "H", "232-1245"))),
        hep_quest(result_date="2026-11-07"),
        b12_folate_quest(folate_value="2.4", folate_flag="L"),
        lipase_quest(),
        row("H PYLORI,$UREA BREATH TEST",
            result(("HELICOBACTER PYLORI,$UREA BREATH TEST", "DETECTED", "A"))),
        row("Stool occult",
            result(("FECAL GLOBIN BY$IMMUNOCHEMISTRY", "", ""))),
        row("Stool culture - Campylobacter",
            result(("CULTURE", "NOT ISOLATED", "N"))),
        row("Stool Ova and Parasite",
            result(("OVA AND PARASITES,$CONC AND PERM SMEAR", "", "", "",
                    "CONCENTRATION 1:   No ova or parasites seen\n"
                    "  TRICHROME 1:       No ova or parasites seen\n"
                    "  Reference Range:   No ova or parasites seen."))),
        row("Stool C-diff Toxin",
            result(("CLOSTRIDIUM DIFFICILE$TOXIN/GDH W/REFL TO PCR",
                    "", "", "",
                    "GDH Antigen:       Not Detected\n"
                    "  Toxin A and B:     Not Detected\n"
                    "  Comment:           No toxigenic C. difficile detected"))),
        hsv_quest(hsv1=("58.00", "H")),
        afp_labcorp("7.2", "H"),
        cea_labcorp(),
        ca125_labcorp("40", "H"),
        ana_quest(),
        esr_quest(),
        crp_quest(),
        row("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE",
            result(("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", "NEGATIVE", "N"))),
        albc_quest(),
        *hep_trio()[:2],
        *hep_trio()[2:],
        hbv_dna("2000", "H", "IU/mL"),
        row("Hemoglobin A1c", result(("Hemoglobin A1c", "6.0", "H"))),
        row("TSH reflex to T4F", result(("TSH", "2.460", ""))),
        row("Thyroid Stim Immunoglobulin",
            result(("Thyroid Stim Immunoglobulin", "<0.10", "", "0.00-0.55"))),
        row("FSH, Serum", result(("FSH", "5.6", ""))),
        row("CORTISOL, A.M.",
            result(("CORTISOL, A.M.", "11.8", "N"))),
        row("PROLACTIN", result(("PROLACTIN", "11.7", "N"))),
        row("LH, Serum", result(("LH", "5.6", "N", "2.4-12.6"))),
        ts_quest(),
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "102", "H", "<90"))),
        row("magnesium", result(("Magnesium, Serum", "2.0", "", "1.6-2.3"))),
        ua_labcorp(),
        cbc_quest(),
    ]
    assert build_lab_summary(rows) == (
        "11/2026- UA nl, TSH 2.5, TSI nl, FSH nl, testosterone T/F nl, "
        "cortisol nl, prolactin nl, LH nl, A1c 6, Alb/Cr<30, "
        "LDL 104, LpA nl, ApoB 102(90), RBC 5.4(5.1), "
        "Hematocrit 46.8(46), VitD 32, "
        "PTH nl, Mg nl, Phos 5.5(4.3), zinc 50(60), uric acid 6.8, PSA 1.4, "
        "HBV/HCV/HSV2 neg, HSV1+, HBV DNA 2000/3.3, HBV Ab neg, HAV Ab+, "
        "measles Ab+, iron nl, B12 1285(1245), FA 2.4, AST/ALT 35/54(46), "
        "lipase 73(60), ANA+, ESR 28(20), CRP 15(8), "
        "H pylori+, stool occult neg, stool culture neg, "
        "stool O-P neg, C diff neg, "
        "AFP 7.2(6.4), CEA 2.7, CA 125 40(35), "
        "QTB neg"
    )

    # empty input
    assert build_lab_summary([]) == ""


# ----------------------------------------------------------------------
# the reference patients from the yellow notes
# ----------------------------------------------------------------------

def test_reference_patients():
    # MRN 21721 (Yang, Quest): ketones 2+/occult blood trace ignored;
    # the Quest LIPID PANEL's LDL-CHOLESTEROL item yields the LDL token
    # (the note's "45(50)/140/66" shorthand is HDL(=50 target)/LDL/TG;
    # the low HDL with its normal triglycerides renders the standalone
    # `HDL 45` line), measles IgG 204.00 is immune -> measles Ab+,
    # QTB NEGATIVE -> QTB neg.
    yang = [
        row("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE",
            result(("MITOGEN-NIL", "9.16", "N"), ("NIL", "0.05", "N"),
                   ("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", "NEGATIVE", "N"),
                   ("TB1-NIL", "0.00", "N"), ("TB2-NIL", "0.01", "N")),
            result_date="2026-11-07"),
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.2", "N")),
            result_date="2026-11-07"),
        albc_quest(result_date="2026-11-07"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "66", "N"),
            ("CHOLESTEROL, TOTAL", "201", "H"),
            ("HDL CHOLESTEROL", "45", "L"),
            ("LDL-CHOLESTEROL", "140", "H"),
            ("CHOL/HDLC RATIO", "4.5", "N"),
            ("NON HDL CHOLESTEROL", "156", "H")),
            result_date="2026-11-07"),
        row("TSH W/REFLEX TO FT4",
            result(("TSH W/REFLEX TO FT4", "2.79", "N")),
            result_date="2026-11-07"),
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", "204.00", "N")),
            result_date="2026-11-07"),
        ua_quest(result_date="2026-11-07"),
    ]
    data = json.loads(yang[-1]["result"])
    for item in data:
        if item["itemName"] == "KETONES":
            item.update(value="2+", flag="A")
        if item["itemName"] == "OCCULT BLOOD":
            item.update(value="TRACE", flag="A")
    yang[-1] = row("UA, urine routine", json.dumps(data),
                   result_date="2026-11-07")
    assert build_lab_summary(yang) == \
        ("11/2026- UA nl, TSH 2.8, A1c 5.2, Alb/Cr<30, HDL 45, LDL 140, "
         "measles Ab+, QTB neg")

    # MRN 22443 (Wu, LabCorp): everything the note says, in order.
    wu = [
        row("Lipid Panel", result(
            ("Cholesterol, Total", "173", ""),
            ("Triglycerides", "111", ""),
            ("HDL Cholesterol", "51", ""),
            ("VLDL Cholesterol Cal", "18", ""),
            ("LDL Chol Calc (NIH)", "104", "H")),
            result_date="2026-11-07"),
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "53.1", "")),
            result_date="2026-11-07"),
        row("Hemoglobin A1c", result(("Hemoglobin A1c", "6.0", "H")),
            result_date="2026-11-07"),
        row("Uric Acid, Serum", result(("Uric Acid, Serum", "6.8", "")),
            result_date="2026-11-07"),
        row("TSH reflex to T4F", result(("TSH", "2.460", "")),
            result_date="2026-11-07"),
        *hep_trio(),
        ua_labcorp(),
    ]
    assert build_lab_summary(wu) == (
        "11/2026- UA nl, TSH 2.5, A1c 6, LDL 104, LpA nl, "
        "uric acid 6.8, HBV/HCV neg, HBV Ab neg"
    )

    # MRN 22523: trace esterase/ketones ignored, crystals present,
    # hep A ignored, iron panel normal, B12 1285 (H, range 232-1245)
    # -> B12 1285(1245), QTB negative.
    alex = [
        row("Hep A Ab, Total", result(("Hep A Ab, Total", "Negative", "")),
            result_date="2026-11-07"),
        row("Lipoprotein (a)", result(("Lipoprotein (a)", "22.8", "")),
            result_date="2026-11-07"),
        row("Vitamin B12",
            result(("Vitamin B12", "1285", "H", "232-1245")),
            result_date="2026-11-07"),
        row("Iron and TIBC",
            result(("Iron Bind.Cap.(TIBC)", "347", "", "250-450"),
                   ("UIBC", "244", "", "111-343"),
                   ("Iron, Serum", "103", "", "38-169"),
                   ("Iron Saturation", "30", "", "15-55")),
            result_date="2026-11-07"),
        *hep_trio(),
        qtb_labcorp(result_date="2026-11-07"),
    ]
    ua = json.loads(ua_labcorp()["result"])
    for item in ua:
        if item["itemName"] == "WBC Esterase":
            item.update(value="Trace", flag="A")
        if item["itemName"] == "Ketones":
            item.update(value="Trace", flag="A")
        if item["itemName"] == "Crystals":
            item.update(value="Present", flag="A")
    alex.append(row("UA, Routine", json.dumps(ua)))
    assert build_lab_summary(alex) == \
        ("11/2026- UA crystals+, LpA nl, HBV/HCV neg, HBV Ab neg, "
         "iron nl, B12 1285(1245), QTB neg")

    # MRN 22457 (Quest): UA pH `< OR = 5.0`, protein trace, calcium
    # oxalate crystals (squamous cells / bacteria few ignored) ->
    # UA pH<5, protein trace+, crystals+; the CBC's high RBC (5.43 in
    # 3.80-5.10, rendered to one decimal) renders RBC 5.4(5.1) and its
    # high Hct (46.8 in 35.9-46.0) renders Hematocrit 46.8(46); the
    # abnormal LpA (97, no range) renders LpA 97 and the reactive
    # hep B surface Ab (immunity) leaves the hep trio as HBV/HCV
    # neg and reports its own HBV Ab+ token; the reactive hep A total
    # Ab renders HAV Ab+; the CMP's high AST (34 in 10-30) / ALT (66
    # in 6-29) render AST/ALT 34(30)/66(29) and its high protein
    # (8.4 in 6.1-8.1) the protein 8.4(8.1) token; its BUN, Cr, EGFR,
    # albumin, bilirubin and ALP are normal so they produce nothing;
    # its GLUCOSE 86 joins the A1c token as Glu 86/A1c 5.7.
    p22457 = [
        row("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE",
            result(("MITOGEN-NIL", "7.39", "N"), ("NIL", "0.11", "N"),
                   ("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", "NEGATIVE", "N"),
                   ("TB1-NIL", "0.01", "N"), ("TB2-NIL", "0.04", "N")),
            result_date="2026-11-07"),
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A")),
            result_date="2026-11-07"),
        row("Hep C Ab reflex to RNA, QN, PCR",
            result(("HEPATITIS C ANTIBODY", "NON-REACTIVE", "N")),
            result_date="2026-11-07"),
        row("MICROALBUMIN, RANDOM URINE (W/CREATININE)",
            result(("CREATININE, RANDOM URINE", "162", "N", "20-275"),
                   ("MICROALBUMIN", "5.5", "N"),
                   ("MICROALBUMIN/CREATININE$RATIO, RANDOM URINE", "34",
                    "H", "<30")),
            result_date="2026-11-07"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "103", "N", "<150"),
            ("CHOLESTEROL, TOTAL", "215", "H", "<200"),
            ("HDL CHOLESTEROL", "52", "N", "> OR = 50"),
            ("LDL-CHOLESTEROL", "141", "H"),
            ("CHOL/HDLC RATIO", "4.1", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "163", "H", "<130")),
            result_date="2026-11-07"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "97", "H")),
            result_date="2026-11-07"),
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.7", "H", "<5.7")),
            result_date="2026-11-07"),
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "78", "N", "30-100")),
            result_date="2026-11-07"),
        row("TSH W/REFLEX TO FT4",
            result(("TSH W/REFLEX TO FT4", "1.87", "N")),
            result_date="2026-11-07"),
        row("CMP", result(
            ("GLUCOSE", "86", "N", "65-99"),
            ("UREA NITROGEN (BUN)", "13", "N", "7-25"),
            ("CREATININE", "0.78", "N", "0.50-0.97"),
            ("SODIUM", "135", "N", "135-146"),
            ("POTASSIUM", "4.4", "N", "3.5-5.3"),
            ("CHLORIDE", "98", "N", "98-110"),
            ("CARBON DIOXIDE", "26", "N", "20-32"),
            ("CALCIUM", "10.1", "N", "8.6-10.2"),
            ("PROTEIN, TOTAL", "8.4", "H", "6.1-8.1"),
            ("ALBUMIN", "5.0", "N", "3.6-5.1"),
            ("BILIRUBIN, TOTAL", "0.6", "N", "0.2-1.2"),
            ("ALKALINE PHOSPHATASE", "60", "N", "31-125"),
            ("AST", "34", "H", "10-30"),
            ("ALT", "66", "H", "6-29"),
            ("EGFR", "101", "N", "> OR = 60")),
            result_date="2026-11-07"),
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "NON-REACTIVE", "N")),
            result_date="2026-11-07"),
        row("Hep B Surface Ab",
            result(("HEPATITIS B SURFACE$ANTIBODY QL", "REACTIVE", "A")),
            result_date="2026-11-07"),
        ua_22457(),
        row("CBC (INCLUDES DIFF/PLT)", result(
            ("WHITE BLOOD CELL COUNT", "9.9", "N", "3.8-10.8"),
            ("RED BLOOD CELL COUNT", "5.43", "H", "3.80-5.10"),
            ("HEMOGLOBIN", "15.4", "N", "11.7-15.5"),
            ("HEMATOCRIT", "46.8", "H", "35.9-46.0"),
            ("MCV", "86.2", "N", "81.4-101.7"),
            ("MCH", "28.4", "N", "27.0-33.0"),
            ("MCHC", "32.9", "N", "31.6-35.4"),
            ("RDW", "15.1", "H", "11.0-15.0"),
            ("PLATELET COUNT", "348", "N", "140-400")),
            result_date="2026-11-07"),
    ]
    assert build_lab_summary(p22457) == (
        "11/2026- UA pH<5, protein trace+, crystals+, TSH 1.9, "
        "Glu 86/A1c 5.7, Alb/Cr 34, LDL 141, LpA 97, RBC 5.4(5.1), "
        "Hematocrit 46.8(46), VitD 78, HBV/HCV neg, HBV Ab+, HAV Ab+, "
        "AST/ALT 34(30)/66(29), "
        "protein 8.4(8.1), QTB neg"
    )

    # MRN 12885 (Quest hepatic function panel): only the ALT is high
    # (54 (H), range 9-46); the normal AST (35) is written plain ->
    # AST/ALT 35/54(46).
    assert build_lab_summary([hep_quest()]) == "11/2026- AST/ALT 35/54(46)"

    # MRN 19798 (Quest, all normal): the intact PTH (30, range 16-77)
    # joins the vitamin D token; the normal lipid panel still carries
    # its LDL value (84).
    p19798 = [
        psa_quest(value="1.40", result_date="2026-11-02"),
        pth_quest(result_date="2026-11-02"),
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "48", "N", "30-100")),
            result_date="2026-11-02"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "<10", "N")),
            result_date="2026-11-02"),
        row("URIC ACID", result(("URIC ACID", "5.7", "N", "4.0-8.0")),
            result_date="2026-11-02"),
        row("HEMOGLOBIN A1c",
            result(("HEMOGLOBIN A1c", "5.6", "N", "<5.7")),
            result_date="2026-11-02"),
        row("MICROALBUMIN, RANDOM URINE (W/CREATININE)",
            result(("CREATININE, RANDOM URINE", "106", "N", "20-320"),
                   ("MICROALBUMIN", "0.3", "N"),
                   ("MICROALBUMIN/CREATININE$RATIO, RANDOM URINE", "3",
                    "N", "<30")),
            result_date="2026-11-02"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "109", "N", "<150"),
            ("CHOLESTEROL, TOTAL", "159", "N", "<200"),
            ("HDL CHOLESTEROL", "54", "N", "> OR = 40"),
            ("LDL-CHOLESTEROL", "84", "N"),
            ("CHOL/HDLC RATIO", "2.9", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "105", "N", "<130")),
            result_date="2026-11-02"),
        row("TSH W/REFLEX TO FT4",
            result(("TSH W/REFLEX TO FT4", "0.89", "N", "0.40-4.50")),
            result_date="2026-11-02"),
        ua_quest(result_date="2026-11-02"),
    ]
    assert build_lab_summary(p19798) == (
        "11/2026- UA nl, TSH 0.9, A1c 5.6, Alb/Cr<30, LDL 84, LpA nl, "
        "VitD 48, PTH nl, uric acid 5.7, PSA 1.4"
    )

    # MRN 12708 (Quest): the `TSH+FREE T4` layout's high TSH (6.96 in
    # 0.40-4.50) with its normal T4 joins as /T4 nl (the note writes
    # it `TSH 7(4.5)`); the normal TPO / TgAb panel (both < the
    # limits) joins one slash token; the high triglycerides (198 in
    # <150) render the 35/66/198(150) shorthand, the normal LpA
    # renders LpA nl and the normal B12 (318 in 200-1100) reports its
    # value plain.
    p12708 = [
        row("TSH+FREE T4",
            result(("TSH", "6.96", "H", "0.40-4.50"),
                   ("T4, FREE", "1.2", "N", "0.8-1.8")),
            result_date="2026-10-24"),
        row("THYROID PEROXIDASE AND THYROGLOBULIN ANTIBODIES",
            result(("THYROGLOBULIN ANTIBODIES", "<2", "N", "< or = 2"),
                   ("THYROID PEROXIDASE$ANTIBODIES", "<1", "N", "<9")),
            result_date="2026-10-27"),
        row("VITAMIN B12", result(("VITAMIN B12", "318", "N", "200-1100")),
            result_date="2026-10-24"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "198", "H", "<150"),
            ("CHOLESTEROL, TOTAL", "128", "N", "<200"),
            ("HDL CHOLESTEROL", "35", "L", "> OR = 40"),
            ("LDL-CHOLESTEROL", "66", "N"),
            ("CHOL/HDLC RATIO", "3.7", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "93", "N", "<130")),
            result_date="2026-10-27"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "<10", "N")),
            result_date="2026-10-27"),
    ]
    assert build_lab_summary(p12708) == (
        "10/2026- TSH 7.0/T4 nl, TPO/thyroglobulin nl, 35/66/198(150), "
        "LpA nl, B12 318"
    )

    # MRN 17159 (Meng, LabCorp items on in-house order names): the
    # abnormal LpA (227.3, range <75.0) and the Apolipoprotein B
    # order's 102 (range <90) carry the violated limit in
    # parentheses; the lipid panel's high triglycerides (151, range
    # 0-149) render the `45/131/151(149)` shorthand; the in-house
    # magnesium (2.0, range 1.6-2.3) and FSH (5.6, no range) orders
    # are normal; the normal CBC produces nothing and the CMP's
    # Glucose, Serum 97 joins the A1c token (Glu 97/A1c 5.5).
    p17159 = [
        row("CMP", result(("Glucose, Serum", "97", ""),
                         ("BUN", "20", "")),
            result_date="2026-11-09"),
        row("CBC With Differential/Platelet", result(
            ("WBC", "4.1", "", "3.4-10.8"),
            ("Hemoglobin", "12.5", "", "11.1-15.9"),
            ("Platelets", "279", "", "150-450")),
            result_date="2026-11-09"),
        row("TSH+Free T4",
            result(("TSH-ICMA", "1.4", ""),
                   ("Free T4 by Dialysis/Mass Spec", "1.1", "")),
            result_date="2026-11-09"),
        row("lipid _ Apolipoprotein B",
            result(("Apolipoprotein B", "102", "H", "<90")),
            result_date="2026-11-09"),
        row("Lipid Panel", result(
            ("Cholesterol, Total", "202", "H", "100-199"),
            ("Triglycerides", "151", "H", "0-149"),
            ("HDL Cholesterol", "45", "", ">39"),
            ("VLDL Cholesterol Cal", "26", "", "5-40"),
            ("LDL Chol Calc (NIH)", "131", "H", "0-99")),
            result_date="2026-11-09"),
        row("magnesium", result(("Magnesium, Serum", "2.0", "", "1.6-2.3")),
            result_date="2026-11-09"),
        row("Lipoprotein (a)",
            result(("Lipoprotein (a)", "227.3", "H", "<75.0")),
            result_date="2026-11-09"),
        row("Hemoglobin A1c",
            result(("Hemoglobin A1c", "5.5", "", "4.8-5.6")),
            result_date="2026-11-09"),
        row("FSH, Serum", result(("FSH", "5.6", "")),
            result_date="2026-11-09"),
        ua_labcorp(result_date="2026-11-09"),
    ]
    assert build_lab_summary(p17159) == (
        "11/2026- UA nl, TSH 1.4/T4 nl, FSH nl, Glu 97/A1c 5.5, "
        "45/131/151(149), LpA 227(75), ApoB 102(90), Mg nl"
    )


    # MRN 22545 (Quest): the full STD screen joins the hep token; the
    # normal lipid panel still carries its LDL value (92), the flagged
    # LpA (119, no range) renders LpA 119; the normal CBC produces
    # nothing and the CMP's GLUCOSE 88 joins the A1c token
    # (Glu 88/A1c 5.8).
    p22545 = [
        row("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", result(
            ("MITOGEN-NIL", "3.46", "N"), ("NIL", "0.04", "N"),
            ("QUANTIFERON(R)-TB GOLD PLUS, 1 TUBE", "NEGATIVE", "N"),
            ("TB1-NIL", "0.01", "N"), ("TB2-NIL", "0.00", "N")),
            result_date="2026-11-10"),
        hiv_quest(result_date="2026-11-10"),
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "31", "N", "30-100")),
            result_date="2026-11-10"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "119", "H")),
            result_date="2026-11-10"),
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.8", "H", "<5.7")),
            result_date="2026-11-10"),
        rpr_quest(result_date="2026-11-10"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "88", "N", "<150"),
            ("CHOLESTEROL, TOTAL", "180", "N", "<200"),
            ("HDL CHOLESTEROL", "70", "N", "> OR = 50"),
            ("LDL-CHOLESTEROL", "92", "N"),
            ("CHOL/HDLC RATIO", "2.6", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "110", "N", "<130")),
            result_date="2026-11-10"),
        row("Hep C Ab reflex to RNA, QN, PCR",
            result(("HEPATITIS C ANTIBODY", "NON-REACTIVE", "N")),
            result_date="2026-11-10"),
        row("Hep B surface Ag",
            result(("HEPATITIS B SURFACE$ANTIGEN", "NON-REACTIVE", "N")),
            result_date="2026-11-10"),
        row("Hep B surface Ab",
            result(("HEPATITIS B SURFACE$ANTIBODY QL", "NON-REACTIVE", "N")),
            result_date="2026-11-10"),
        row("UA, urine routine", result(
            ("COLOR", "YELLOW", "N"), ("APPEARANCE", "CLEAR", "N"),
            ("BILIRUBIN", "NEGATIVE", "N"), ("KETONES", "NEGATIVE", "N"),
            ("SPECIFIC GRAVITY", "1.021", "N", "1.001-1.035"),
            ("OCCULT BLOOD", "NEGATIVE", "N"),
            ("PH", "5.5", "N", "5.0-8.0"),
            ("PROTEIN", "NEGATIVE", "N"), ("NITRITE", "NEGATIVE", "N"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N"),
            ("WBC", "0-5", "N"), ("RBC", "NONE SEEN", "N"),
            ("SQUAMOUS EPITHELIAL CELLS", "0-5", ""),
            ("BACTERIA", "NONE SEEN", "N"), ("HYALINE CAST", "NONE SEEN",
             "N"), ("GLUCOSE", "NEGATIVE", "N")),
            result_date="2026-11-10"),
        row("CMP", result(("GLUCOSE", "88", "N", "65-99"),
                         ("CREATININE", "0.71", "N", "0.50-1.05"),
                         ("SODIUM", "141", "N", "135-146"))),
        row("CBC (INCLUDES DIFF/PLT)", result(
            ("WHITE BLOOD CELL COUNT", "4.5", "N", "3.8-10.8"),
            ("HEMOGLOBIN", "13.7", "N", "11.7-15.5"),
            ("PLATELET COUNT", "283", "N", "140-400"))),
    ]
    assert build_lab_summary(p22545) == (
        "11/2026- UA nl, Glu 88/A1c 5.8, LDL 92, LpA 119, VitD 31, "
        "HBV/HCV/HIV/RPR neg, HBV Ab neg, QTB neg"
    )

    # MRN 20831 (Quest): the reactive HAV total Ab renders HAV Ab+ and
    # the capped measles IgG (>300.00) is still immune -> measles Ab+;
    # the normal lipid panel still carries its LDL value (88), the
    # normal LpA renders LpA nl; the normal CBC produces nothing and
    # the CMP's GLUCOSE 92 joins the A1c token (Glu 92/A1c 5.5).
    p20831 = [
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "97", "N", "<150"),
            ("CHOLESTEROL, TOTAL", "165", "N", "<200"),
            ("HDL CHOLESTEROL", "58", "N", "> OR = 40"),
            ("LDL-CHOLESTEROL", "88", "N"),
            ("CHOL/HDLC RATIO", "2.8", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "107", "N", "<130")),
            result_date="2026-11-10"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "<10", "N")),
            result_date="2026-11-10"),
        row("Measle _ Rubeola _ IgG",
            result(("MEASLES ANTIBODY (IGG)", ">300.00", "N")),
            result_date="2026-11-10"),
        row("HEMOGLOBIN A1c",
            result(("HEMOGLOBIN A1c", "5.5", "N", "<5.7")),
            result_date="2026-11-10"),
        row("Hep A total Ab",
            result(("HEPATITIS A AB, TOTAL", "REACTIVE", "A", "NON-REACTIVE")),
            result_date="2026-11-10"),
        ua_quest(result_date="2026-11-10"),
        row("CMP", result(("GLUCOSE", "92", "N", "65-99"),
                         ("CREATININE", "0.96", "N", "0.60-1.26")),
            result_date="2026-11-10"),
        row("CBC (INCLUDES DIFF/PLT)", result(
            ("WHITE BLOOD CELL COUNT", "7.0", "N", "3.8-10.8"),
            ("HEMOGLOBIN", "15.4", "N", "13.2-17.1")),
            result_date="2026-11-10"),
    ]
    assert build_lab_summary(p20831) == (
        "11/2026- UA nl, Glu 92/A1c 5.5, LDL 88, LpA nl, HAV Ab+, "
        "measles Ab+"
    )

    # MRN 14952 (Li, in-house orders with Quest items): the CMP's high
    # AST (42, range 10-35) and ALT (62, range 9-46) render
    # AST/ALT 42(35)/62(46) (the note's shorthand); the panel's high
    # glucose joins the A1c token (Glu 101/A1c 5.7); the normal lipid
    # panel (LDL 51) still renders LDL 51 and the normal iron panel's
    # items are ignored;
    # the flagged "bacteria many" is
    # reported.
    p14952 = [
        row("CMP", result(
            ("GLUCOSE", "101", "H", "65-99"),
            ("UREA NITROGEN (BUN)", "22", "N", "7-25"),
            ("CREATININE", "1.03", "N", "0.70-1.35"),
            ("BUN/CREATININE RATIO", "SEE NOTE:", "", "6-22"),
            ("SODIUM", "139", "N", "135-146"),
            ("POTASSIUM", "4.4", "N", "3.5-5.3"),
            ("CHLORIDE", "103", "N", "98-110"),
            ("CARBON DIOXIDE", "29", "N", "20-32"),
            ("CALCIUM", "9.4", "N", "8.6-10.3"),
            ("PROTEIN, TOTAL", "7.4", "N", "6.1-8.1"),
            ("ALBUMIN", "4.6", "N", "3.6-5.1"),
            ("GLOBULIN", "2.8", "N", "1.9-3.7"),
            ("ALBUMIN/GLOBULIN RATIO", "1.6", "N", "1.0-2.5"),
            ("BILIRUBIN, TOTAL", "0.6", "N", "0.2-1.2"),
            ("ALKALINE PHOSPHATASE", "48", "N", "35-144"),
            ("AST", "42", "H", "10-35"),
            ("ALT", "62", "H", "9-46"),
            ("EGFR", "83", "N", "> OR = 60")),
            result_date="2026-11-10"),
        row("HEMOGLOBIN A1c", result(("HEMOGLOBIN A1c", "5.7", "H", "<5.7")),
            result_date="2026-11-10"),
        row("LIPID PANEL", result(
            ("TRIGLYCERIDES", "65", "N", "<150"),
            ("CHOLESTEROL, TOTAL", "112", "N", "<200"),
            ("HDL CHOLESTEROL", "47", "N", "> OR = 40"),
            ("LDL-CHOLESTEROL", "51", "N"),
            ("CHOL/HDLC RATIO", "2.4", "N", "<5.0"),
            ("NON HDL CHOLESTEROL", "65", "N", "<130")),
            result_date="2026-11-10"),
        row("IRON AND TOTAL IRON$BINDING CAPACITY", result(
            ("IRON, TOTAL", "131", "N", "50-180"),
            ("IRON BINDING CAPACITY", "351", "N", "250-425"),
            ("% SATURATION", "37", "N", "20-48")),
            result_date="2026-11-10"),
        row("VITAMIN D,25-OH,TOTAL,IA",
            result(("VITAMIN D,25-OH,TOTAL,IA", "39", "N", "30-100")),
            result_date="2026-09-14"),
        row("LIPOPROTEIN (a)", result(("LIPOPROTEIN (a)", "140", "H")),
            result_date="2026-09-14"),
        row("lipid_ APOLIPOPROTEIN B",
            result(("APOLIPOPROTEIN B", "54", "N")),
            result_date="2026-09-14"),
        row("PSA, TOTAL",
            result(("PSA, TOTAL", "0.40", "N", "< OR = 4.00")),
            result_date="2026-09-14"),
        row("TSH W/REFLEX TO FT4",
            result(("TSH W/REFLEX TO FT4", "4.10", "N", "0.40-4.50")),
            result_date="2026-09-14"),
        row("MICROALBUMIN, RANDOM URINE (W/CREATININE)", result(
            ("CREATININE, RANDOM URINE", "67", "N", "20-320"),
            ("MICROALBUMIN", "0.2", "N"),
            ("MICROALBUMIN/CREATININE$RATIO, RANDOM URINE", "3", "N",
             "<30")),
            result_date="2026-09-14"),
        row("UA, urine routine", result(
            ("COLOR", "YELLOW", "N", "YELLOW"),
            ("APPEARANCE", "CLEAR", "N", "CLEAR"),
            ("BILIRUBIN", "NEGATIVE", "N", "NEGATIVE"),
            ("KETONES", "NEGATIVE", "N", "NEGATIVE"),
            ("SPECIFIC GRAVITY", "1.012", "N", "1.001-1.035"),
            ("OCCULT BLOOD", "NEGATIVE", "N", "NEGATIVE"),
            ("PH", "7.5", "N", "5.0-8.0"),
            ("PROTEIN", "NEGATIVE", "N", "NEGATIVE"),
            ("NITRITE", "NEGATIVE", "N", "NEGATIVE"),
            ("LEUKOCYTE ESTERASE", "NEGATIVE", "N", "NEGATIVE"),
            ("WBC", "0-5", "N", "< OR = 5"),
            ("RBC", "NONE SEEN", "N", "< OR = 2"),
            ("SQUAMOUS EPITHELIAL CELLS", "NONE SEEN", "N", "< OR = 5"),
            ("BACTERIA", "MANY", "A", "NONE SEEN"),
            ("HYALINE CAST", "NONE SEEN", "N", "NONE SEEN"),
            ("GLUCOSE", "NEGATIVE", "N", "NEGATIVE")),
            result_date="2026-09-14"),
    ]
    assert build_lab_summary(p14952) == (
        "11/2026- UA bacteria many, TSH 4.1, Glu 101/A1c 5.7, "
        "Alb/Cr<30, LDL 51, LpA 140, "
        "ApoB nl, VitD 39, PSA 0.4, iron nl, AST/ALT 42(35)/62(46)"
    )

    # MRN 16030 (Zhou, in-house stool cultures): the isolated
    # campylobacter reports alone as the yellow notes' `Campylobactor+
    # (the negative salmonella/shigella and e. coli O157:H7 cultures
    # carry empty values with their `No ... isolated` note text, and
    # the susceptibility / bacterial-ID follow-ups are separate
    # orders); the high ESR (range < OR = 20); the negative O/P and
    # C-diff toxin orders report `stool O-P neg` / `C diff neg`; the
    # normal CBC / CMP and the calprotectin, giardia and
    # cryptosporidium orders are not in the summary.
    p16030 = [
        row("SALMONELLA AND SHIGELLA, CULTURE",
            result(("CULTURE", "", "", "", SALM_CX_NEG_NOTES)),
            result_date="2026-11-08"),
        row("ANTIMICROBIAL SUSC., CAMPYLOBACTER,MIC PANEL",
            result(("ORGANISM", "CAMPYLOBACTER JEJUNI", "N"),
                   ("CIPROFLOXACIN", "0.030 S", "N"),
                   ("ERYTHROMYCIN", "0.500 S", "N"),
                   ("SPECIMEN SOURCE", "STOOL", "N")),
            result_date="2026-11-08"),
        row("BACTERIAL ID AND SUSCEPTIBILITY, AEROBIC",
            result(("SOURCE", "STOOL", "N"),
                   ("STATUS", "FINAL", "N"),
                   ("ORGANISM", "CAMPYLOBACTER JEJUNI", "N")),
            result_date="2026-11-08"),
        row("Stool culture - Campylobacter",
            result(("CULTURE", "ISOLATED", "A", "",
                    "REFERENCE RANGE:  NOT ISOLATED")),
            result_date="2026-11-08"),
        row("Stool culture for Ecoli O157:H7",
            result(("CULTURE", "", "", "", ECOLI_CX_NEG_NOTES)),
            result_date="2026-11-08"),
        row("ESR",
            result(("SED RATE BY MODIFIED$WESTERGREN", "28", "H",
                    "< OR = 20")),
            result_date="2026-11-08"),
        row("Stool _ CALPROTECTIN for IBD",
            result(("CALPROTECTIN, STOOL", "789", "H")),
            result_date="2026-11-06"),
        row("Stool C-diff Toxin",
            result(("CLOSTRIDIUM DIFFICILE$TOXIN/GDH W/REFL TO PCR",
                    "", "", "",
                    "CLOSTRIDIUM DIFFICILE TOXIN/GDH W/REFL TO PCR\n"
                    "  GDH Antigen:       Not Detected\n"
                    "  Toxin A and B:     Not Detected")),
            result_date="2026-11-06"),
        row("Stool Ova and Parasite",
            result(("OVA AND PARASITES,$CONC AND PERM SMEAR", "", "", "",
                    "OVA AND PARASITES, CONC AND PERM SMEAR\n"
                    "  CONCENTRATION 1:   No ova or parasites seen")),
            result_date="2026-11-08"),
    ]
    assert build_lab_summary(p16030) == (
        "11/2026- ESR 28(20), Campylobactor+, stool O-P neg, C diff neg")



# ----------------------------------------------------------------------
# Allergy (allergen-specific IgE / IgG4 panels)
# ----------------------------------------------------------------------

def allergy_eval(mite_value="<0.10", mite_flag="N", **kw):
    """The in-house `ALLERGY EVALUATION 9, NORTHWEST` panel (mrn
    21553's layout): tree / weed / grass pollen, molds, cat / dog
    dander, dust mite, beside the `CLASS` items that are not
    reported.  The mite item's value / flag are parameterized."""
    return row(
        "ALLERGY EVALUATION 9, NORTHWEST",
        result(
            ("ALDER (T2) IGE", "<0.10", "N"),
            ("ALTERNARIA ALTERNATA (M6) IGE", "<0.10", "N"),
            ("CAT DANDER (E1) IGE", "<0.10", "N"),
            ("CLADOSPORIUM HERBARUM (M2) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("CLASS", "0", ""),
            ("DERMATOPHAGOIDES FARINAE (D2) IGE", mite_value, mite_flag),
            ("DOG DANDER (E5) IGE", "<0.10", "N"),
            ("ENGLISH PLANTAIN (W9) IGE", "<0.10", "N"),
            ("JUNE GRASS(KENTUCKY BLUE) (G8) IGE", "<0.10", "N"),
            ("LAMB'S QUARTERS (GOOSE FOOT) (W10) IGE", "<0.10", "N"),
            ("PERENNIAL RYE GRASS (G5) IGE", "<0.10", "N"),
        ),
        **kw,
    )


def allergy_mold(**kw):
    """The in-house `ALLERGY MOLD PANEL, COMPLETE` panel (mrn
    21553's layout): five molds beside the `CLASS` items."""
    return row(
        "ALLERGY MOLD PANEL, COMPLETE",
        result(
            ("ALTERNARIA ALTERNATA (M6) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("ASPERGILLUS FUMIGATUS (M3) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("CLADOSPORIUM HERBARUM (M2) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("MUCOR RACEMOSUS (M4) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("PENICILLIUM NOTATUM (M1) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("STEMPHYLIUM BOTRYOSUM (M10) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
        ),
        **kw,
    )


def allergy_mite_igg4(value="<0.30", flag="", rng="<0.50",
                      name="Allergy  _ D PTERONYSSINUS MITE IGG4*",
                      **kw):
    """One in-house dust-mite IgG4 order: the code-less mite item,
    its reference range on its range field (mrn 21553's layout)."""
    return row(
        name,
        result(("D PTERONYSSINUS MITE", value, flag, rng,
                "FLAG Interpretation: A = Abnormal, H = High, L = Low")),
        **kw,
    )


def allergy_cat(value="<0.10", flag="N", **kw):
    """The in-house `Allergy _ Cat IgE` order: the cat-dander item
    plus the `CLASS` item (mrn 19469's layout)."""
    return row(
        "Allergy _ Cat IgE",
        result(
            ("CAT DANDER (E1) IGE", value, flag),
            ("CLASS", "0", ""),
        ),
        **kw,
    )


def allergy_food(shrimp_value="<0.10", shrimp_flag="N",
                 scallop_value="<0.10", scallop_flag="N", **kw):
    """The in-house `FOOD ALLERGY PANEL (REFL)` panel (mrn 21598's
    layout): ten food items beside the `CLASS` items; the shrimp and
    scallop items' values / flags are parameterized."""
    return row(
        "FOOD ALLERGY PANEL (REFL)",
        result(
            ("EGG WHITE (F1) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("PEANUT (F13) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("WHEAT (F4) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("WALNUT (F256) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("CODFISH (F3) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("COW'S MILK (F2) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("SOYBEAN (F14) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("MAIZE/CORN (F8) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("SHRIMP (F24) IGE", shrimp_value, shrimp_flag),
            ("CLASS", "0/1", ""),
            ("SCALLOP (F338) IGE", scallop_value, scallop_flag),
            ("CLASS", "0", ""),
            ("CLAM (F207) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("SESAME SEED (F10) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
        ),
        **kw,
    )


def allergy_food_labcorp(shrimp_value="<0.10", shrimp_flag="",
                         scallop_value="<0.10", scallop_flag="", **kw):
    """LabCorp's `Allergy Profile, Food` panel (mrn 21088's layout):
    the `{CODE}-IgE {ALLERGEN}` items, their IgE class on their
    range field, the not-performed items' `TNP` values, beside the
    `Class Description` / `Reflex` items the summary does not
    report; the shrimp and scallop items' values / flags are
    parameterized."""
    return row(
        "Allergy Profile, Food",
        result(
            ("Class Description", "", ""),
            ("F014-IgE Soybean", "<0.10", "", "Class 0"),
            ("F041-IgE Salmon", "TNP", ""),
            ("F338-IgE Scallop", scallop_value, scallop_flag, "Class 0/I"),
            ("F024-IgE Shrimp", shrimp_value, shrimp_flag, "Class I"),
            ("F002-IgE Milk", "<0.10", "", "Class 0"),
            ("F001-IgE Egg White", "<0.10", "", "Class 0"),
            ("F010-IgE Sesame Seed", "TNP", ""),
            ("F013-IgE Peanut", "<0.10", "", "Class 0"),
            ("F256-IgE Walnut", "<0.10", "", "Class 0"),
            ("F004-IgE Wheat", "<0.10", "", "Class 0"),
            ("Reflex", "TNP", ""),
        ),
        **kw,
    )


def allergy_resp_profile(**kw):
    """The in-house `RESPIRATORY ALLERGY PROFILE REGION XVII` panel
    (mrn 19357's layout): tree / weed / grass pollen, molds, cat /
    dog / mouse dander, dust mite, beside the total-IgE / `CLASS`
    / `INTERPRETATION` items and the unreportable cockroach `(I6)`
    item that the summary does not report."""
    return row(
        "RESPIRATORY ALLERGY PROFILE REGION XVII",
        result(
            ("IMMUNOGLOBULIN E", "103", "N", "<OR=114"),
            ("PENICILLIUM NOTATUM (M1)$IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("DERMATOPHAGOIDES$PTERONYSSINUS (D1) IGE", "<0.10", "N"),
            ("ROUGH PIGWEED (W14) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("MAPLE (BOX ELDER) (T1)$IGE", "<0.10", "N"),
            ("BIRCH (T3) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("DERMATOPHAGOIDES FARINAE$(D2) IGE", "<0.10", "N"),
            ("CAT DANDER (E1) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("DOG DANDER (E5) IGE", "<0.10", "N"),
            ("TIMOTHY GRASS (G6) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("ALTERNARIA ALTERNATA (M6)$IGE", "<0.10", "N"),
            ("OAK (T7) IGE", "<0.10", "N"),
            ("COMMON RAGWEED (SHORT)$(W1) IGE", "<0.10", "N"),
            ("MOUSE URINE PROTEINS$(E72) IGE", "<0.10", "N"),
            ("CLASS", "0", ""),
            ("COCKROACH (I6) IGE", "<0.10", "N"),
            ("INTERPRETATION", "", "", "",
             "Specific IGE Class\nLevel of Allergen kU/L"),
        ),
        **kw,
    )


def test_allergy():
    # a negative panel: the tested groups join one token, in the
    # fixed group order (the yellow notes write `all.ergy mold/dust
    # mite/Pollen neg`, `animal/mold/pollen neg`, `food allergy neg`)
    assert build_lab_summary([allergy_eval()]) == \
        "11/2026- allergy mold/dust mite/pollen/animal neg"
    assert build_lab_summary([allergy_mold()]) == "11/2026- allergy mold neg"
    assert build_lab_summary([allergy_mite_igg4()]) == \
        "11/2026- allergy dust mite neg"
    assert build_lab_summary([allergy_cat()]) == \
        "11/2026- allergy animal neg"
    assert build_lab_summary([allergy_food()]) == \
        "11/2026- allergy food neg"
    # the in-house food profile (with reflexes) feeds food like the
    # food panel does (same item layout)
    assert build_lab_summary([
        row("FOOD ALLERGY PROFILE WITH REFLEXES", allergy_food()["result"]),
    ]) == "11/2026- allergy food neg"
    # LabCorp's food panel: the `{CODE}-IgE` leading code joins the
    # same food group, and its `Class 0/I` range label is not a
    # numeric range
    assert build_lab_summary([allergy_food_labcorp()]) == \
        "11/2026- allergy food neg"
    # the in-house respiratory profile (like the eval panel) feeds
    # every respiratory group; the total-IgE / cockroach items are
    # not reported
    assert build_lab_summary([allergy_resp_profile()]) == \
        "11/2026- allergy mold/dust mite/pollen/animal neg"
    # name matching is case-insensitive
    assert build_lab_summary([
        row("allergy mold panel, complete", allergy_mold()["result"]),
    ]) == "11/2026- allergy mold neg"
    assert build_lab_summary([
        row("Food Allergy Panel (refl)", allergy_food()["result"]),
    ]) == "11/2026- allergy food neg"
    # the CLASS items are not reported: a panel whose allergen items
    # are all pending (empty values) produces nothing
    assert build_lab_summary([
        row("ALLERGY MOLD PANEL, COMPLETE",
            result(("ALTERNARIA ALTERNATA (M6) IGE", "", ""),
                   ("CLASS", "0", ""))),
    ]) == ""
    # a flagged positive mite (21309's yellow note writes `dust mite
    # 0.23+(0.1)`): the positive item reports alone, the negative
    # groups join the leading token
    assert build_lab_summary(
        [allergy_eval(mite_value="0.23", mite_flag="H")]) == (
            "11/2026- allergy mold/pollen/animal neg, "
            "dust mite 0.23+(0.1)")
    # an unflagged level at / above the 0.10 kU/L cutoff counts too
    # (the IgE items carry no reference range)
    assert build_lab_summary(
        [allergy_eval(mite_value="0.15", mite_flag="")]) == (
            "11/2026- allergy mold/pollen/animal neg, "
            "dust mite 0.15+(0.1)")
    # an unflagged level below the cutoff is negative
    assert build_lab_summary(
        [allergy_eval(mite_value="0.05", mite_flag="")]) == (
            "11/2026- allergy mold/dust mite/pollen/animal neg")
    # a positive food item: the food panel has no negative group left,
    # so the positive item reports alone (mrn 21598's panel carried a
    # flagged SHRIMP 0.24)
    assert build_lab_summary(
        [allergy_food(shrimp_value="0.24", shrimp_flag="H")]) == \
        "11/2026- food 0.24+(0.1)"
    # several positive food items, one token per item in report order
    assert build_lab_summary(
        [allergy_food(shrimp_value="0.24", shrimp_flag="H",
                      scallop_value="0.20", scallop_flag="H")]) == \
        "11/2026- food 0.24+(0.1), food 0.2+(0.1)"
    # mrn 21088: the LabCorp food panel's flagged positives -- their
    # range field carries the IgE class label, not a numeric range,
    # so the bound is the 0.10 cutoff, not the `Class 0/I`'s `0`
    assert build_lab_summary([
        allergy_food_labcorp(shrimp_value="0.36", shrimp_flag="A",
                             scallop_value="0.31", scallop_flag="A"),
    ]) == "11/2026- food 0.31+(0.1), food 0.36+(0.1)"
    # a positive mite IgG4: the bound is the item's range upper limit
    # (<0.50 -> 0.5), not the specific-IgE 0.10 cutoff
    assert build_lab_summary([
        allergy_mite_igg4(value="0.6", flag="H"),
    ]) == "11/2026- dust mite 0.6+(0.5)"
    # mrn 21553: the eval panel, the standalone mold panel and the
    # mite IgG4 order feed the same groups; the newest row per group
    # decides and the negative groups join one token
    assert build_lab_summary([
        allergy_eval(result_date="2026-11-07"),
        allergy_mite_igg4(result_date="2026-11-07"),
        allergy_mold(result_date="2026-11-04"),
    ]) == "11/2026- allergy mold/dust mite/pollen/animal neg"
    # the newest row wins per group: a newer negative panel supersedes
    # an older positive mite, and vice versa
    assert build_lab_summary([
        allergy_eval(result_date="2026-11-07"),
        allergy_mite_igg4(value="0.6", flag="H", result_date="2026-09-01"),
    ]) == "11/2026- allergy mold/dust mite/pollen/animal neg"
    assert build_lab_summary([
        allergy_mite_igg4(value="0.6", flag="H", result_date="2026-11-07"),
        allergy_eval(result_date="2026-09-01"),
    ]) == ("11/2026- allergy mold/pollen/animal neg, dust mite 0.6+(0.5)")
    # reported after the ABO token, in the fixed order
    assert build_lab_summary([
        row("ABO Grouping and Rho(D) Typing",
            result(("ABO Grouping", "O", ""),
                   ("Rh Factor", "Positive", ""))),
        allergy_mold(),
    ]) == "11/2026- ABO O+, allergy mold neg"
