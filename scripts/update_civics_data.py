import json
import re
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "civics_current.json"


# ---------------------------------------------------------
# OFFICIAL / PRIMARY DATA SOURCES
# ---------------------------------------------------------

SENATE_URL = (
    "https://www.senate.gov/general/"
    "contact_information/senators_cfm.xml"
)

HOUSE_URL = (
    "https://clerk.house.gov/xml/lists/MemberData.xml"
)

GOVERNORS_URL = (
    "https://www.nga.org/governors/"
)

WHITE_HOUSE_URL = (
    "https://www.whitehouse.gov/administration/"
)

HOUSE_LEADERSHIP_URL = (
    "https://www.house.gov/leadership"
)

SUPREME_COURT_URL = (
    "https://www.supremecourt.gov/about/biographies.aspx"
)


HEADERS = {
    "User-Agent": (
        "VedicaCivicsData/1.0 "
        "https://github.com/vedicachudiwale/vedica-civics-data"
    )
}


# ---------------------------------------------------------
# STATE INFORMATION
# ---------------------------------------------------------
#
# State capitals are effectively static, so there is no
# reason to scrape them every day.
#

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


# ---------------------------------------------------------
# PRESIDENT PARTY SAFETY FALLBACK
# ---------------------------------------------------------
#
# The updater FIRST tries to identify the party from the
# official White House Administration page.
#
# If the White House page changes and does not expose one
# clear party, this mapping is used as a safety fallback.
#
# If a future President is neither detected nor listed here,
# the workflow FAILS instead of publishing stale/wrong data.
#

PRESIDENT_PARTY_BY_NAME = {
    "Donald J. Trump": "Republican",
}


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def download(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response


def clean_text(tag):

    return " ".join(
        tag.stripped_strings
    ).strip()


# ---------------------------------------------------------
# NATIONAL OFFICIALS
# ---------------------------------------------------------

def get_national_officials():

    # -----------------------------------------------------
    # PRESIDENT + VICE PRESIDENT
    # -----------------------------------------------------

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
        ["h1", "h2", "h3", "h4"]
    ):

        text = clean_text(
            heading
        )

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


    # -----------------------------------------------------
    # PRESIDENT'S POLITICAL PARTY
    # -----------------------------------------------------

    page_text = " ".join(
        soup.stripped_strings
    )


    detected_parties = []


    for party in (
        "Republican",
        "Democratic"
    ):

        if re.search(
            rf"\b{party}\s+Party\b",
            page_text,
            flags=re.IGNORECASE
        ):

            detected_parties.append(
                party
            )


    # Only trust the page automatically when exactly
    # one recognized major party appears.
    if len(detected_parties) == 1:

        president_party = (
            detected_parties[0]
        )

    else:

        president_party = (
            PRESIDENT_PARTY_BY_NAME.get(
                president
            )
        )


    if not president_party:

        raise RuntimeError(
            "Could not safely determine "
            "the President's political party "
            f"for {president}. "
            "Update PRESIDENT_PARTY_BY_NAME "
            "before publishing."
        )


    # -----------------------------------------------------
    # SPEAKER OF THE HOUSE
    # -----------------------------------------------------

    response = download(
        HOUSE_LEADERSHIP_URL
    )

    house_soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    speaker = None


    speaker_title = house_soup.find(

        lambda tag:

            tag.name in {
                "h1",
                "h2",
                "h3",
                "h4"
            }

            and clean_text(tag)
            == "Speaker of the House"
    )


    if speaker_title is not None:

        next_heading = (
            speaker_title.find_next(
                [
                    "h1",
                    "h2",
                    "h3",
                    "h4"
                ]
            )
        )


        if next_heading is not None:

            speaker_text = clean_text(
                next_heading
            )


            if speaker_text.startswith(
                "Rep. "
            ):

                speaker = speaker_text[
                    len("Rep. "):
                ].strip()


    if not speaker:

        raise RuntimeError(
            "Could not determine "
            "current Speaker of the House."
        )


    # -----------------------------------------------------
    # CHIEF JUSTICE
    # -----------------------------------------------------

    response = download(
        SUPREME_COURT_URL
    )


    court_soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    chief_justice = None


    marker = (
        ", Chief Justice "
        "of the United States,"
    )


    for text in (
        court_soup.stripped_strings
    ):

        if marker in text:

            chief_justice = text.split(
                marker,
                1
            )[0].strip()

            break


    if not chief_justice:

        raise RuntimeError(
            "Could not determine "
            "current Chief Justice."
        )


    return {
        "president":
            president,

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
# GOVERNORS
# ---------------------------------------------------------

def get_governors():

    response = download(
        GOVERNORS_URL
    )


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    governors = {}


    for link in soup.find_all("a"):

        text = clean_text(
            link
        )


        for state in STATE_INFO:

            prefix = (
                f"{state} Gov. "
            )


            if text.startswith(
                prefix
            ):

                name = text[
                    len(prefix):
                ].strip()


                if name:

                    governors[
                        state
                    ] = name


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

    response = download(
        SENATE_URL
    )


    root = ET.fromstring(
        response.content
    )


    senators = {

        state: []

        for state in STATE_INFO
    }


    for member in root.findall(
        ".//member"
    ):

        first_name = (
            member.findtext(
                "first_name"
            )
            or ""
        ).strip()


        last_name = (
            member.findtext(
                "last_name"
            )
            or ""
        ).strip()


        abbreviation = (
            member.findtext(
                "state"
            )
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
                f"{first_name} "
                f"{last_name}"
            )


            senators[
                state
            ].append(
                full_name
            )


    # Require at least one Senator per state.
    # This allows temporary vacancies without
    # destroying the whole update.
    missing = [

        state

        for state, names
        in senators.items()

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

def normalize_district(
    value
):

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
            int(
                match.group()
            )
        )


    return None


def get_representatives():

    response = download(
        HOUSE_URL
    )


    root = ET.fromstring(
        response.content
    )


    representatives = {

        state: {}

        for state in STATE_INFO
    }


    total_members = 0


    for member in root.findall(
        ".//member"
    ):

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

            info.findtext(
                "district"
            )
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


    # Safety check.
    #
    # Vacancies mean there may be fewer than 435,
    # but a result under 400 almost certainly
    # means the feed/parser broke.
    if total_members < 400:

        raise RuntimeError(
            "House data returned only "
            f"{total_members} members. "
            "Update cancelled."
        )


    return representatives


# ---------------------------------------------------------
# FINAL DATA VALIDATION
# ---------------------------------------------------------

def validate_output(
    data
):

    # Schema
    if data.get(
        "schemaVersion"
    ) != 1:

        raise RuntimeError(
            "Unexpected schema version."
        )


    # National data
    national = (
        data.get("national")
        or {}
    )


    required_national = [
        "president",
        "presidentParty",
        "vicePresident",
        "speakerOfTheHouse",
        "chiefJustice"
    ]


    missing_national = [

        key

        for key
        in required_national

        if not national.get(
            key
        )
    ]


    if missing_national:

        raise RuntimeError(
            "Missing national fields: "
            + ", ".join(
                missing_national
            )
        )


    # States
    states = (
        data.get("states")
        or {}
    )


    if len(states) != 50:

        raise RuntimeError(
            "Expected 50 states, found "
            f"{len(states)}."
        )


    for state in STATE_INFO:

        state_data = states.get(
            state
        )


        if not state_data:

            raise RuntimeError(
                f"Missing state data "
                f"for {state}."
            )


        if not state_data.get(
            "capital"
        ):

            raise RuntimeError(
                f"Missing capital "
                f"for {state}."
            )


        if not state_data.get(
            "governor"
        ):

            raise RuntimeError(
                f"Missing governor "
                f"for {state}."
            )


        if not state_data.get(
            "senators"
        ):

            raise RuntimeError(
                f"Missing senators "
                f"for {state}."
            )


# ---------------------------------------------------------
# BUILD JSON
# ---------------------------------------------------------

def main():

    print(
        "Downloading national officials..."
    )

    national = (
        get_national_officials()
    )


    print(
        "Downloading governors..."
    )

    governors = (
        get_governors()
    )


    print(
        "Downloading senators..."
    )

    senators = (
        get_senators()
    )


    print(
        "Downloading House members..."
    )

    representatives = (
        get_representatives()
    )


    states = {}


    for state, (
        _,
        capital
    ) in STATE_INFO.items():

        states[state] = {

            "capital":
                capital,

            "governor":
                governors[
                    state
                ],

            "senators":
                senators[
                    state
                ],

            "representatives":
                representatives[
                    state
                ]
        }


    updated = {

        "schemaVersion":
            1,


        "lastUpdated":
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z"
            ),


        "national":
            national,


        "states":
            states,


        "sources": {

            "presidentVicePresident":
                WHITE_HOUSE_URL,

            "presidentParty":
                WHITE_HOUSE_URL,

            "speakerOfTheHouse":
                HOUSE_LEADERSHIP_URL,

            "chiefJustice":
                SUPREME_COURT_URL,

            "governors":
                GOVERNORS_URL,

            "senators":
                SENATE_URL,

            "representatives":
                HOUSE_URL
        }
    }


    # Validate EVERYTHING before touching
    # the existing good JSON file.
    validate_output(
        updated
    )


    # Write to a temporary file first.
    #
    # This prevents a failed update from
    # corrupting civics_current.json.
    temp_file = (
        OUTPUT_FILE.with_suffix(
            ".json.tmp"
        )
    )


    with temp_file.open(
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


    # Only replace the production file
    # after the complete update succeeds.
    temp_file.replace(
        OUTPUT_FILE
    )


    print(
        "civics_current.json updated."
    )


if __name__ == "__main__":

    main()
