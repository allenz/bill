"""Checks for note.parse_note (the /encounter page's progress-note parser).

The fixtures are minimal SOAP envelopes in the shape db.progress_notes()
stores from the ECW physician's dashboard: <return> holds UI-state
elements plus <subItems> blocks, each a run of <item> entries (older
shape) or of named content blocks (newer shape). parse_note returns
(section_title, groups); a group is (label, children), children a list of
("t", text) lines and ("g", group) nested groups.
"""
import xml.etree.ElementTree as ET

from note import parse_note


def envelope(body):
    """A minimal SOAP envelope wrapping `body` in <return> (the stored
    notes lead with the same XML declaration)."""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<SOAP-ENV:Envelope '
            'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<SOAP-ENV:Body><return>{body}</return></SOAP-ENV:Body>'
            '</SOAP-ENV:Envelope>')


def subitems(name, *children):
    return (f'<subItems><subItemsName>{name}:</subItemsName>'
            + ''.join(children) + '</subItems>')


def item(name, *content):
    inner = f'<itemName>{name}</itemName>' if name else ''
    return f'<item>{inner}{"".join(content)}</item>'


def lines_of(groups):
    """All text lines of a groups list, in display order (nested groups
    included)."""
    out = []
    for _, children in groups:
        for n in children:
            if n[0] == 't':
                out.append(n[1])
            else:
                out.extend(lines_of([n[1]]))
    return out


def labels(groups):
    """The group labels (h4 level), in order, None labels dropped."""
    return [label for label, _ in groups if label]


def sublabels(groups):
    """The nested group labels (h5 level), in display order."""
    out = []
    for _, children in groups:
        for n in children:
            if n[0] == 'g':
                if n[1][0]:
                    out.append(n[1][0])
                out.extend(sublabels([n[1]]))
    return out


def test_sections():
    note = envelope(
        subitems('Subjective', item('HPI:', '<itemValue>a</itemValue>'))
        + subitems('Plan')  # an empty section is dropped
        + subitems('Billing  Information',
                   item('Visit Code:', '<itemValue>99214</itemValue>')))
    sections = parse_note(note)
    assert [t for t, _ in sections] == ['Subjective', 'Billing Information']
    assert lines_of(sections[0][1]) == ['a']
    # the item label leads its group
    assert labels(sections[0][1]) == ['HPI']


def test_item_values():
    note = envelope(subitems('Subjective', item(
        'Medical History:',
        '<itemValue>HTN: Valsartan &gt; 2024</itemValue>'
        '<itemValue>line one&lt;br&gt;line two</itemValue>'  # <br> is stored as text
        '<itemValue>&lt;b&gt;bold&lt;/b&gt; text</itemValue>')))
    assert lines_of(parse_note(note)[0][1]) == [
        'HTN: Valsartan > 2024',  # entities unescaped
        'line one', 'line two',    # <br> splits the line
        'bold text',               # the remaining tags are stripped
    ]


def test_duplicate_lines_are_dropped():
    # the envelope stores family history twice: plain and <br>-form
    note = envelope(subitems('Subjective', item(
        'Family History:',
        '<familyNotes>Father: cancer</familyNotes>'
        '<itemValueBR>Father: cancer</itemValueBR>')))
    assert lines_of(parse_note(note)[0][1]) == ['Father: cancer']


def test_ros():
    note = envelope(subitems('Subjective', item('ROS:',
        '<category><categoryName>Cardiovascular</categoryName>'
        '<rosDetail><name>Chest pain</name><notes>denies</notes></rosDetail>'
        '<rosDetail><name>Palpitations</name><notes/></rosDetail>'
        '</category>')))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['ROS']
    assert sublabels([groups]) == ['Cardiovascular']
    assert lines_of([groups]) == ['Chest pain: denies', 'Palpitations']


def test_exam():
    note = envelope(subitems('Objective', item('Examination:',
        '<category><categoryName>General Examination</categoryName>'
        '<categoryInDetail><cat_det>'
        '<categorySubName>EYES:</categorySubName>'
        '<examNotes>&lt;font size="2"&gt;pupils equal&lt;/font&gt;</examNotes>'
        '</cat_det><cat_det>'
        '<categorySubName>HEART:</categorySubName>'
        '<examNotes>&lt;font size="2"&gt;rrr&lt;/font&gt;&lt;font size="2"&gt;, no murmur&lt;/font&gt;</examNotes>'
        '</cat_det></categoryInDetail>'
        '</category>')))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['Examination']
    assert sublabels([groups]) == ['General Examination']
    assert lines_of([groups]) == [
        'EYES: pupils equal',
        'HEART: rrr, no murmur',  # the font fragments join back together
    ]


def test_vitals():
    note = envelope(subitems('Objective', item(
        'Vitals:', '<vitalValue>HR: &lt;B&gt;74&lt;/B&gt; /min, BP: 129/64 mm Hg.</vitalValue>')))
    assert lines_of(parse_note(note)[0][1]) == [
        'HR: 74 /min, BP: 129/64 mm Hg.']


def test_treatment():
    # the refill line comes from categoryValue, the notes from
    # categoryNotesHtm (its leading "Notes:" label is dropped)
    note = envelope(subitems('Plan', item('Treatment:',
        '<category><categoryName>Essential hypertension</categoryName>'
        '<categoryValueTrmt><ndcCode>00781-5690-05</ndcCode></categoryValueTrmt>'
        '<categoryValue>Refill Ezetimibe 10 MG, daily</categoryValue>'
        '<categoryNotesHtm>Notes: &lt;font&gt;Stable on therapy.&lt;/font&gt;</categoryNotesHtm>'
        '</category>')))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['Treatment']
    assert sublabels([groups]) == ['Essential hypertension']
    assert lines_of([groups]) == ['Refill Ezetimibe 10 MG, daily',
                                  'Stable on therapy.']


def test_hpi_structured():
    # HPI detail with no combined value: one line per answered StData
    # entry, the detail's item name (when stored) as a sub-group label
    note = envelope(subitems('Subjective', item('HPI:',
        '<category><categoryName>Depression Screening</categoryName>'
        '<HpiDetail3><hpiName>PHQ-9</hpiName>'
        '<StData><name>Feeling down</name><value>Several days</value></StData>'
        '<StData><name>Feeling tired</name><value>Not at all</value></StData>'
        '<StData><name>Unanswered</name><value></value></StData>'
        '</HpiDetail3></category>')))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['HPI']
    assert sublabels([groups]) == ['Depression Screening', 'PHQ-9']
    # one line per question, answered entries only
    assert lines_of([groups]) == [
        'Feeling down Several days', 'Feeling tired Not at all']


def test_social_detail_groups():
    # socialDetail carries its own item name (Tobacco Use/Smoking,
    # AUDIT-C) as a sub-group below the category
    note = envelope(subitems('Subjective',
        '<SocialHistory>'
        '<category><categoryName>Tobacco Use:</categoryName>'
        '<socialDetail><itemname>Tobacco Use/Smoking</itemname>'
        '<StData><name>Are you a</name><value>nonsmoker</value></StData>'
        '</socialDetail></category>'
        '<category><categoryName>Drug/Alcohol:</categoryName>'
        '<socialDetail><itemname>AUDIT-C (Standard)</itemname>'
        '<StData><name>Did you drink last year?</name><value>No</value></StData>'
        '<StData><name>Points</name><value>0</value></StData>'
        '<StData><name>Interpretation</name><value>Negative</value></StData>'
        '</socialDetail></category>'
        '</SocialHistory>'))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['Social History']
    assert sublabels([groups]) == [
        'Tobacco Use', 'Tobacco Use/Smoking', 'Drug/Alcohol',
        'AUDIT-C (Standard)']
    assert lines_of([groups]) == [
        'Are you a nonsmoker', 'Did you drink last year? No',
        'Points 0', 'Interpretation Negative']


def test_nested_items_and_surg_reasons():
    note = envelope(subitems('Subjective', item('Surgical History:',
        '<itemValue>Denies Past Surgical History.</itemValue>'
        '<surgHxItemDetail><reason>Denies Past Surgical History.</reason></surgHxItemDetail>'
        '<item><itemName>Appendectomy</itemName>'
        '<itemValue>2019, uncomplicated</itemValue></item>')))
    (groups,) = parse_note(note)[0][1]
    # the surg reason duplicates the itemValue; the nested item becomes a
    # sub-group under the item
    assert lines_of([groups]) == [
        'Denies Past Surgical History.', '2019, uncomplicated']
    assert labels([groups]) == ['Surgical History']
    assert sublabels([groups]) == ['Appendectomy']


def test_labelless_and_empty_items_are_skipped():
    note = envelope(subitems('Plan',
                             item('', '<itemValue>orphan</itemValue>'),
                             item('Procedures:')))
    groups = parse_note(note)[0][1]
    # the unlabeled item keeps its text; the empty item is dropped
    assert lines_of(groups) == ['orphan']
    assert labels(groups) == []


def test_block_level_lines_stay_out_of_subgroups():
    # the lines after a category in a block belong to the block, not to
    # the category (Social History: the Tobacco Use category, then the
    # "Verified" line and the life-situation notes at block level)
    note = envelope(subitems('Subjective',
        '<SocialHistory>'
        '<category><categoryName>Tobacco Use</categoryName>'
        '<socialDetail>'
        '<StData><name>Are you a</name><value>nonsmoker</value></StData>'
        '</socialDetail></category>'
        '<itemValueBR>Social History Verified.</itemValueBR>'
        '<category><categoryNotesBR>Married, living with husband</categoryNotesBR>'
        '</category>'
        '</SocialHistory>'))
    (group,) = parse_note(note)[0][1]
    label, children = group
    assert label == 'Social History'
    assert [n[0] for n in children] == ['g', 't', 'g']
    assert children[0][1][0] == 'Tobacco Use'
    assert children[1][1] == 'Social History Verified.'
    assert children[2][1][0] is None  # the unnamed category is block-level
    assert lines_of([group]) == [
        'Are you a nonsmoker', 'Social History Verified.',
        'Married, living with husband']


def test_treatment_lab_imaging_orders():
    # treatment assessments hold Test (LAB:) and Xrayname (IMAGING:)
    # orders alongside rx and notes, in document order
    note = envelope(subitems('Plan',
        '<treatment><assessment><name>Annual exam</name>'
        '<Test><TestName>CBC (INCLUDES DIFF/PLT)</TestName><ReportId>1</ReportId></Test>'
        '<Test><TestName>CMP</TestName><ReportId>2</ReportId></Test>'
        '<notesBR>Notes: &lt;font&gt;Advised diet and exercise.&lt;/font&gt;</notesBR>'
        '</assessment><assessment><name>Breast cancer screening</name>'
        '<Xrayname><TestName>Mammo DIAGNOSTIC, BIL, W/ IMPLANTS</TestName></Xrayname>'
        '<Xrayname><TestName>US BREAST BILATERAL COMPLETE</TestName></Xrayname>'
        '</assessment></treatment>'))
    (groups,) = parse_note(note)[0][1]
    assert labels([groups]) == ['Treatment']
    assert sublabels([groups]) == ['Annual exam', 'Breast cancer screening']
    assert lines_of([groups]) == [
        'LAB: CBC (INCLUDES DIFF/PLT)', 'LAB: CMP',
        'Advised diet and exercise.',
        'IMAGING: Mammo DIAGNOSTIC, BIL, W/ IMPLANTS',
        'IMAGING: US BREAST BILATERAL COMPLETE']


def test_new_shape_blocks():
    # newer dashboard envelopes hold named content blocks per <subItems>
    # instead of <item> entries
    note = envelope(
        subitems('Subjective',
                 '<cc><itemValue>c/o cough</itemValue></cc>'
                 '<hpi><category><categoryName>General</categoryName>'
                 '<hpiCatNotes>c/o cough since yesterday</hpiCatNotes>'
                 '</category></hpi>'
                 '<ros><category><categoryName>ENT</categoryName>'
                 '<rosDetail><name>Sore throat</name><notes>admits</notes></rosDetail>'
                 '</category></ros>')
        + subitems('Objective',
                   '<vitals2BR>HR: 74, BP: 129/64.</vitals2BR>')
        + subitems('Assessment',
                   '<assessmentData><assessmentDiagnosis><icdName>Cough in adult</icdName></assessmentDiagnosis></assessmentData>'  # display duplicate
                   '<categoryValueAssessment><assessmentName>x</assessmentName></categoryValueAssessment>'
                   '<assessment>Cough in adult - R05.9 (Primary)</assessment>')
        + subitems('Plan',
                   '<treatment><assessment><name>Cough in adult</name>'
                   '<rx>Start Tessalon 100 MG as needed</rx>'
                   '<rxData><ndcCode>x</ndcCode></rxData>'
                   '<notesBR>Notes: &#160;Supportive care.</notesBR></assessment></treatment>'
                   '<FollowUp>2 - 3 Days PRN</FollowUp>'))
    sections = parse_note(note)
    assert [t for t, _ in sections] == [
        'Subjective', 'Objective', 'Assessment', 'Plan']
    assert lines_of(sections[0][1]) == [
        'c/o cough', 'c/o cough since yesterday', 'Sore throat: admits']
    # the named blocks get ECW's headings (the envelope stores none);
    # the category names are sub-groups under their blocks
    assert labels(sections[0][1]) == [
        'Chief complaints', 'History of Present Illness',
        'Review of system']
    assert sublabels(sections[0][1]) == ['General', 'ENT']
    assert lines_of(sections[1][1]) == ['HR: 74, BP: 129/64.']
    assert labels(sections[1][1]) == ['Vitals']
    # the Assessment section shows the bare diagnosis lines only
    assert lines_of(sections[2][1]) == ['Cough in adult - R05.9 (Primary)']
    assert lines_of(sections[3][1]) == [
        'Start Tessalon 100 MG as needed', 'Supportive care.',
        '2 - 3 Days PRN']
    assert labels(sections[3][1]) == ['Treatment', 'Follow Up']
    assert sublabels(sections[3][1]) == ['Cough in adult']


def test_new_shape_meds_and_immunization():
    # CurrentMeds shows the "Taking ..." itemValue lines (the Taking
    # category is a structured duplicate); Immunization/Injection blocks
    # carry their own itemName heading with <SubItems> lines below
    note = envelope(
        subitems('Subjective',
            '<CurrentMeds>'
            '<category><categoryName>Taking</categoryName>'
            '<categoryValue>Naproxen 500 MG Tablet 1 tablet</categoryValue>'
            '<rxData><ndcCode>x</ndcCode></rxData></category>'
            '<itemValue>Taking Naproxen 500 MG Tablet 1 tablet</itemValue>'
            '<itemValue>Medication List reviewed</itemValue>'
            '</CurrentMeds>')
        + subitems('Plan',
            '<Immunization><itemName>Immunizations:</itemName>'
            '<SubItems><itemValue>Fluzone High Dose Quad</itemValue>'
            '<itemDetails>: 0.7 mL (Route : Intramuscular) given</itemDetails>'
            '<ImmId>50420</ImmId></SubItems></Immunization>'))
    sections = parse_note(note)
    (subj, plan) = sections
    assert lines_of(subj[1]) == [
        'Taking Naproxen 500 MG Tablet 1 tablet', 'Medication List reviewed']
    assert labels(subj[1]) == ['Current Medications']
    assert lines_of(plan[1]) == [
        'Fluzone High Dose Quad', ': 0.7 mL (Route : Intramuscular) given']
    assert labels(plan[1]) == ['Immunizations']


def test_demographics_only():
    # old dashboard envelopes hold no <subItems>: nothing to show
    note = envelope('<patient>Doe, Jane</patient><DOB>01/01/1950</DOB>')
    assert parse_note(note) == []


def test_unparseable():
    assert parse_note('not an envelope') is None
    assert parse_note('<return><patient>truncated') is None
    # parses but has no <return> element
    assert parse_note('<envelope><foo/></envelope>') is None
