import re
from datetime import datetime

from config import DIR, warn
from save_block import BLOCK_CONSTANTS


ENCOUNTER_CONSTANTS = {
    'facilityId': '2',
    'facilityName': 'Bay Area Union Health Center',
    'resources': '122',
    'doctorId': '122',
    'userId': 0,
    'deptId': '0',
    'encLock': '0',
    'encType': '1',
    'POS': '11',
    'RTServiceAuthorization': '0',
    'transitionOfCare': '0',
    'ShowInsEligOnAppt': True,
    'doctorName': 'LING, JIE ',
}
APPT_CARD_CONSTANTS = {
    'facilityRegion': 'America/Los_Angeles',
    'textEnabled': '0',
}
# the entry 'status' field is a hex color, constant per visitId
STATUS_COLOR = {
    'C reminder': '#66CCCC',
    'Reminder': '#CC9900',
    'ANN VISIT': '#666666',
    'A_Vacc': '#3300FF',
    '2 book': '#CCCCCC',
    'A_NP': '#FF9900',
    'Self Pay': '#FFFF00',
}
KNOWN_ELIGIBILITY = {'0', '1', '2', '3', '5', '7'}


def check_schedule(entry: dict, date: str) -> None:
    """Check the constant/predictable fields of one get_encounters_json() entry
    (an encounter, or a calendar block if it has blockType).

    Each failure is appended to WARN_LOG.
    """
    label = entry.get('encounterId') or entry.get('id')
    problems = []
    if 'encounterId' in entry:
        appt = entry.get('apptCard', {})
        problems += [f'{k}={entry.get(k)!r} != {v!r}'
                     for k, v in ENCOUNTER_CONSTANTS.items() if entry.get(k) != v]
        problems += [f'apptCard.{k}={appt.get(k)!r} != {v!r}'
                     for k, v in APPT_CARD_CONSTANTS.items() if appt.get(k) != v]
        if appt.get('facilityTimezone') not in ['PDT', 'PST']:
            problems.append(f"apptCard.facilityTimezone={appt.get('facilityTimezone')!r}")
        if (entry.get('groupId') or '') != '':
            problems.append(f"groupId={entry.get('groupId')!r}")
        if entry.get('id') != f"enc:{entry.get('encounterId')}":
            problems.append(f"id={entry.get('id')!r}")
        if (appt.get('encounterId'), appt.get('patientId')) != (entry.get('encounterId'), entry.get('patId')):
            problems.append(f"apptCard ids ({appt.get('encounterId')}, {appt.get('patientId')}) != ({entry.get('encounterId')}, {entry.get('patId')})")
        if appt.get('dateTime') != entry.get('start'):
            problems.append(f"apptCard.dateTime={appt.get('dateTime')!r} != start={entry.get('start')!r}")
        if appt.get('provider') != entry.get('doctorName'):
            problems.append(f"apptCard.provider={appt.get('provider')!r} != doctorName={entry.get('doctorName')!r}")
        if appt.get('generalNotes') != entry.get('generalNotes'):
            problems.append('apptCard.generalNotes != generalNotes')
        if appt.get('visitStatus') != entry.get('pStatus'):
            problems.append(f"apptCard.visitStatus={appt.get('visitStatus')!r} != pStatus={entry.get('pStatus')!r}")
        if entry.get('eligibilityStatus') not in KNOWN_ELIGIBILITY:
            problems.append(f"eligibilityStatus={entry.get('eligibilityStatus')!r}")
        if 'patientImageFilePath' in entry and entry['patientImageFilePath'] != f"{entry.get('patId')}.jpg":
            problems.append(f"patientImageFilePath={entry['patientImageFilePath']!r}")
        expected = STATUS_COLOR.get(entry.get('visitId'))
        if expected is None:
            problems.append(f"unknown visitId={entry.get('visitId')!r}")
        elif entry.get('status') != expected:
            problems.append(f"status={entry.get('status')!r} != {expected!r} for visitId={entry.get('visitId')!r}")
        try:
            start = datetime.strptime(entry['start'], '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(entry['end'], '%Y-%m-%d %H:%M:%S')
        except (KeyError, TypeError, ValueError):
            problems.append(f"unparseable start/end: {entry.get('start')!r} / {entry.get('end')!r}")
        else:
            try:
                duration = int(appt.get('duration'))
            except (TypeError, ValueError):
                problems.append(f"unparseable duration={appt.get('duration')!r}")
            else:
                if (end - start).total_seconds() != duration * 60:
                    problems.append(f"end-start != duration ({entry['start']} .. {entry['end']}, {duration} min)")
    else:
        # calendar block
        problems += [f'{k}={entry.get(k)!r} != {v!r}'
                     for k, v in BLOCK_CONSTANTS.items() if entry.get(k) != v]
        if not re.fullmatch(r'blk:\d+:122', entry.get('id', '')):
            problems.append(f"id={entry.get('id')!r}")
        if entry.get('startDate') != (entry.get('start') or '')[:10]:
            problems.append(f"startDate={entry.get('startDate')!r} != start={entry.get('start')!r}")
    for p in problems:
        warn(f'schedule {date} {label}: {p}')
