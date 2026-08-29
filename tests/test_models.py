"""The three balances from specification section 5.4.

These are the checks that stop a malformed tally sheet from reaching a
citizen's screen with percentages that do not reach 100%.
"""

import base64
import json

import pytest
from pydantic import ValidationError

from app.models import Location, RecordData, Results, decode_payload

VALID = {
    "version": "1.0",
    "mesa": "035253",
    "electores_habiles": 287,
    "votantes": 241,
    "votos_validos": 223,
    "votos_nulos": 7,
    "votos_blancos": 11,
    "opciones": [
        {"orden": 1, "nombre": "Movimiento Regional Unidad", "partido": "M.R.U.", "votos": 86},
        {"orden": 2, "nombre": "Alianza Civica del Litoral", "partido": "ACL", "votos": 62},
        {"orden": 3, "nombre": "Frente Vecinal Independiente", "partido": "FVI", "votos": 44},
        {"orden": 4, "nombre": "Partido del Progreso Local", "partido": "PPL", "votos": 31},
    ],
}


def test_valid_sheet_is_accepted():
    results = Results.model_validate(VALID)
    assert results.valid_votes == 223
    assert len(results.options) == 4


def test_options_must_add_up_to_valid_votes():
    broken = {**VALID, "opciones": [{**VALID["opciones"][0], "votos": 87}, *VALID["opciones"][1:]]}
    with pytest.raises(ValidationError, match="valid_votes"):
        Results.model_validate(broken)


def test_valid_null_and_blank_must_add_up_to_voters():
    with pytest.raises(ValidationError, match="voters"):
        Results.model_validate({**VALID, "votos_nulos": 8})


def test_voters_cannot_exceed_eligible_voters():
    with pytest.raises(ValidationError, match="exceeds"):
        Results.model_validate({**VALID, "electores_habiles": 200})


def test_share_uses_valid_votes_not_voters():
    """The denominator that caused the original specification error."""
    results = Results.model_validate(VALID)
    winner = results.options[0]
    assert round(results.share(winner), 2) == 38.57   # 86 / 223
    assert round(86 / results.voters * 100, 2) == 35.68  # what it must NOT be


def test_turnout_uses_eligible_voters():
    results = Results.model_validate(VALID)
    assert round(results.turnout, 1) == 84.0          # 241 / 287


def test_null_island_coordinates_are_treated_as_absent():
    """(0, 0) means 'no location', not a pin off the coast of Africa."""
    location = Location.model_validate({"local": "I.E. 1120", "latitude": 0, "longitude": 0})
    assert not location.has_coordinates
    assert location.is_displayable


def test_location_needs_something_to_be_displayable():
    assert not Location.model_validate({}).is_displayable
    assert Location.model_validate({"ubigeo": "150132"}).is_displayable


def test_ubigeo_keeps_leading_zeros():
    """Sent as a number, 010101 becomes 10101 and stops resolving."""
    assert Location.model_validate({"ubigeo": "010101"}).ubigeo == "010101"
    with pytest.raises(ValidationError):
        Location.model_validate({"ubigeo": "10101"})


def test_decode_payload_names_the_failing_stage():
    with pytest.raises(ValueError, match="base64"):
        decode_payload("not base64!!", Results)

    not_json = base64.b64encode(b"plain text").decode()
    with pytest.raises(ValueError, match="JSON"):
        decode_payload(not_json, Results)


def test_record_data_round_trip():
    payload = {
        "version": "1.0",
        "mesa": "035253",
        "folio": "A-035253-6",
        "proceso": {"codigo": "EMC-2026", "nombre": "Elecciones Municipales 2026"},
        "ubicacion": {"local": "I.E. 1120 Pedro A. Labarthe", "ubigeo": "150132"},
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    data = decode_payload(encoded, RecordData)
    assert data.process.code == "EMC-2026"
    assert data.location.venue.startswith("I.E. 1120")


# ── injection ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("station", [
    "<img src=x onerror=alert(1)>",
    '"><script>fetch("//evil")</script>',
    "035253\r\nSet-Cookie: a=b",          # header injection via the filename
    "../../etc/passwd",
    "035253' OR '1'='1",
    "javascript:alert(1)",
    "a" * 40,
])
def test_hostile_station_is_rejected_at_ingestion(station):
    """The station reaches the screen, a filename and the Open Graph tags.

    Constraining it here closes all three at once instead of trusting every
    exit point to remember to escape.
    """
    payload = {"version": "1.0", "mesa": station,
               "proceso": {"codigo": "X", "nombre": "Y"}}
    with pytest.raises(ValidationError):
        RecordData.model_validate(payload)


@pytest.mark.parametrize("station", ["035253", "Mesa 12", "A-0001"])
def test_ordinary_stations_still_pass(station):
    payload = {"version": "1.0", "mesa": station,
               "proceso": {"codigo": "X", "nombre": "Y"}}
    assert RecordData.model_validate(payload).polling_station == station
