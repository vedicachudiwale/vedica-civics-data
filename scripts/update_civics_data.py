import json
import re
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "civics_current.json"


SENATE_URL = (
    "https://www.senate.gov/general/"
    "contact_information/senators_cfm.xml"
)

HOUSE_URL = (
    "https://clerk.house.gov/xml/lists/MemberData.xml"
)

GOVERNORS_URL = "https://www.nga.org/governors/"

WHITE_HOUSE_URL = (
    "https://www.whitehouse.gov/administration/"
)

HOUSE_LEADERSHIP_URL = (
    "https://www.house.gov/leadership"
)

SUPREME_COURT_URL = (
    "https://www.supremecourt.gov/about/about.aspx"
)
HEADERS = {
    "User-Agent": (
        "VedicaCivicsData/1.0 "
        "https://github.com/vedicachudiwale/vedica-civics-data"
    )
}


# State abbreviation + capital.
# Capitals are essentially static, so there is no need
# to scrape another website every day for them.
STATE_INFO = {
    "Alabama": ("AL", "Montgomery"),
    "Alaska": ("AK", "Juneau"),
    "Arizona": ("AZ", "Phoenix"),
    "Arkansas": ("AR", "Little Rock"),
    "California": ("CA", "Sacramento"),
    "Colorado": ("CO", "Denver"),
    "Connecticut": ("CT", "Hartford"),
    "Delaware": ("DE", "Dover"),
    "Florida": ("FL", "Tallahassee"),
    "Georgia": ("GA", "Atlanta"),
    "Hawaii": ("HI", "Honolulu"),
    "Idaho": ("ID", "Boise"),
    "Illinois": ("IL", "Springfield"),
    "Indiana": ("IN", "Indianapolis"),
    "Iowa": ("IA", "Des Moines"),
    "Kansas": ("KS", "Topeka"),
    "Kentucky": ("KY", "Frankfort"),
    "Louisiana": ("LA", "Baton Rouge"),
    "Maine": ("ME", "Augusta"),
    "Maryland": ("MD", "Annapolis"),
    "Massachusetts": ("MA", "Boston"),
    "Michigan": ("MI", "Lansing"),
    "Minnesota": ("MN", "Saint Paul"),
    "Mississippi": ("MS", "Jackson"),
    "Missouri": ("MO", "Jefferson City"),
    "Montana": ("MT", "Helena"),
    "Nebraska": ("NE", "Lincoln"),
    "Nevada": ("NV", "Carson City"),
    "New Hampshire": ("NH", "Concord"),
    "New Jersey": ("NJ", "Trenton"),
    "New Mexico": ("NM", "Santa Fe"),
    "New York": ("NY", "Albany"),
    "North Carolina": ("NC", "Raleigh"),
    "North Dakota": ("ND", "Bismarck"),
    "Ohio": ("OH", "Columbus"),
    "Oklahoma": ("OK", "Oklahoma City"),
    "Oregon": ("OR", "Salem"),
    "Pennsylvania": ("PA", "Harrisburg"),
    "Rhode Island": ("RI", "Providence"),
    "South Carolina": ("SC", "Columbia"),
    "South Dakota": ("SD", "Pierre"),
    "Tennessee": ("TN", "Nashville"),
    "Texas": ("TX", "Austin"),
    "Utah": ("UT", "Salt Lake City"),
    "Vermont": ("VT", "Montpelier"),
    "Virginia": ("VA", "Richmond"),
    "Washington": ("WA", "Olympia"),
    "West Virginia": ("WV", "Charleston"),
    "Wisconsin": ("WI", "Madison"),
    "Wyoming": ("WY", "Cheyenne"),
}


ABBR_TO_STATE = {
    abbreviation: state
    for state, (abbreviation, _) in STATE_INFO.items()
}


def download(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response


# ---------------------------------------------------------
# GOVERNORS
# ---------------------------------------------------------

def get_governors():

    response = download(GOVERNORS_URL)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    governors = {}

    for link in soup.find_all("a"):

        text = " ".join(
            link.stripped_strings
        ).strip()

        for state in STATE_INFO:

            prefix = f"{state} Gov. "

            if text.startswith(prefix):

                name = text[len(prefix):].strip()

                if name:
                    governors[state] = name

                break

    missing = [
        state
        for state in STATE_INFO
        if state not in governors
    ]

    if missing:
        raise RuntimeError(
            "Could not find governors for: "
            + ", ".join(missing)
        )

    return governors


# ---------------------------------------------------------
# SENATORS
# ---------------------------------------------------------

def get_senators():

    response = download(SENATE_URL)

    root = ET.fromstring(
        response.content
    )

    senators = {
        state: []
        for state in STATE_INFO
    }

    for member in root.findall(".//member"):

        first_name = (
            member.findtext("first_name")
            or ""
        ).strip()

        last_name = (
            member.findtext("last_name")
            or ""
        ).strip()

        abbreviation = (
            member.findtext("state")
            or ""
        ).strip()

        state = ABBR_TO_STATE.get(
            abbreviation
        )

        if (
            state
            and first_name
            and last_name
        ):

            full_name = (
                f"{first_name} {last_name}"
            )

            senators[state].append(
                full_name
            )

    missing = [
        state
        for state, names in senators.items()
        if len(names) == 0
    ]

    if missing:
        raise RuntimeError(
            "Could not find senators for: "
            + ", ".join(missing)
        )

    return senators


# ---------------------------------------------------------
# REPRESENTATIVES
# ---------------------------------------------------------

def normalize_district(value):

    value = value.strip()

    if not value:
        return None

    lowered = value.lower()

    if (
        "at large" in lowered
        or "at-large" in lowered
    ):
        return "At-Large"

    match = re.search(
        r"\d+",
        value
    )

    if match:
        return str(
            int(match.group())
        )

    return None


def get_representatives():

    response = download(HOUSE_URL)

    root = ET.fromstring(
        response.content
    )

    representatives = {
        state: {}
        for state in STATE_INFO
    }

    total_members = 0

    for member in root.findall(".//member"):

        info = member.find(
            ".//member-info"
        )

        if info is None:
            continue

        state = (
            info.findtext(
                ".//state-fullname"
            )
            or ""
        ).strip()
        district = normalize_district(
            info.findtext("district")
            or ""
        )

        name = (
            info.findtext(
                "official-name"
            )
            or ""
        ).strip()

        if (
            state in representatives
            and district
            and name
        ):

            representatives[
                state
            ][district] = name

            total_members += 1

    # Safety check so a broken House feed
    # cannot wipe out our data.
    if total_members < 400:

        raise RuntimeError(
            "House data returned only "
            f"{total_members} members. "
            "Update cancelled."
        )

    return representatives
# ---------------------------------------------------------
# NATIONAL OFFICIALS
# ---------------------------------------------------------

def get_national_officials(old_national):

    # -------------------------
    # President + Vice President
    # -------------------------

    response = download(
        WHITE_HOUSE_URL
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    president = None
    vice_president = None

    for heading in soup.find_all(
        ["h1", "h2", "h3"]
    ):

        text = " ".join(
            heading.stripped_strings
        ).strip()

        if (
            text.startswith("President ")
            and not text.startswith(
                "Vice President "
            )
        ):

            president = text[
                len("President "):
            ].strip()

        elif text.startswith(
            "Vice President "
        ):

            vice_president = text[
                len("Vice President "):
            ].strip()


    if not president:
        raise RuntimeError(
            "Could not determine "
            "current President."
        )

    if not vice_president:
        raise RuntimeError(
            "Could not determine "
            "current Vice President."
        )


    # -------------------------
    # Speaker of the House
    # -------------------------

    response = download(
        HOUSE_LEADERSHIP_URL
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    speaker = None

    for heading in soup.find_all(
        ["h1", "h2", "h3", "h4"]
    ):

        text = " ".join(
            heading.stripped_strings
        ).strip()

        if text.startswith("Rep. "):

            previous_text = " ".join(
                heading.find_previous(
                    ["h1", "h2", "h3", "h4"]
                ).stripped_strings
            ).strip()

            if (
                previous_text
                == "Speaker of the House"
            ):

                speaker = text[
                    len("Rep. "):
                ].strip()

                break


    if not speaker:
        raise RuntimeError(
            "Could not determine "
            "current Speaker of the House."
        )


    # -------------------------
    # Chief Justice
    # -------------------------

    response = download(
        SUPREME_COURT_URL
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    page_text = " ".join(
        soup.stripped_strings
    )

    match = re.search(
        r"Chief Justice of the United States\s+"
        r"(.+?)\s+Associate Justices",
        page_text
    )

    if not match:
        raise RuntimeError(
            "Could not determine "
            "current Chief Justice."
        )

    chief_justice = (
        match.group(1).strip()
    )


    # presidentParty stays from the existing
    # JSON for now. We will automate it next.
    president_party = old_national.get(
        "presidentParty"
    )

    if not president_party:
        raise RuntimeError(
            "President party is missing."
        )


    return {
        "president": president,
        "presidentParty":
            president_party,
        "vicePresident":
            vice_president,
        "speakerOfTheHouse":
            speaker,
        "chiefJustice":
            chief_justice
    }

# ---------------------------------------------------------
# BUILD JSON
# ---------------------------------------------------------

def main():

    if not OUTPUT_FILE.exists():

        raise RuntimeError(
            "civics_current.json "
            "does not exist."
        )

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        old_data = json.load(file)


    # Keep the national values already
    # stored in the external file.
    old_national = old_data.get(
    "national"
)

if not old_national:
    raise RuntimeError(
        "National officials are missing "
        "from civics_current.json."
    )


print(
    "Downloading national officials..."
)

national = get_national_officials(
    old_national
)


    print("Downloading governors...")
    governors = get_governors()

    print("Downloading senators...")
    senators = get_senators()

    print("Downloading House members...")
    representatives = get_representatives()


    states = {}

    for state, (_, capital) in STATE_INFO.items():

        states[state] = {
            "capital": capital,
            "governor": governors[state],
            "senators": senators[state],
            "representatives":
                representatives[state]
        }


    updated = {
        "schemaVersion": 1,

        "lastUpdated":
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z"
            ),

        "national": national,

        "states": states,

        "sources": {
            "governors":
                GOVERNORS_URL,

            "senators":
                SENATE_URL,

            "representatives":
                HOUSE_URL
        }
    }


    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            updated,
            file,
            indent=2,
            ensure_ascii=False
        )

        file.write("\n")


    print(
        "civics_current.json updated."
    )


if __name__ == "__main__":
    main()
