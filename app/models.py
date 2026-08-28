"""Wire contract with ONPE.

Field names on the wire are Spanish: that is what docs/INTEGRATION-SPEC.md
committed to, and ONPE builds against it. Python attributes are English per
the project convention, and Pydantic aliases map between the two so neither
side has to bend.

Validation is deliberately strict. A tally sheet whose numbers do not add up
is rejected here, at ingestion, rather than reaching a citizen's screen with
percentages that fail to reach 100%.
"""

from __future__ import annotations

import base64
import binascii
import json
from enum import Enum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Hex64 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Hex40 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
Ubigeo = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class WireModel(BaseModel):
    """Base for everything that crosses the wire with ONPE."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        extra="ignore",
    )


# ─────────────────────────── results (field `info`) ───────────────────────────


class Option(WireModel):
    name: str = Field(alias="nombre", min_length=1)
    votes: int = Field(alias="votos", ge=0)
    party: str | None = Field(default=None, alias="partido")
    order: int | None = Field(default=None, alias="orden", ge=1)
    code: str | None = Field(default=None, alias="codigo")
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class Results(WireModel):
    """Contents of the base64 `info` field.

    Two different denominators are in play, and mixing them is the most
    common integration mistake:

        share of an option  = votes / valid_votes
        turnout             = voters / eligible_voters
    """

    version: str = "1.0"
    polling_station: str = Field(alias="mesa", min_length=1)
    eligible_voters: int = Field(alias="electores_habiles", ge=0)
    voters: int = Field(alias="votantes", ge=0)
    valid_votes: int = Field(alias="votos_validos", ge=0)
    null_votes: int = Field(alias="votos_nulos", ge=0)
    blank_votes: int = Field(alias="votos_blancos", ge=0)
    options: list[Option] = Field(alias="opciones", min_length=1)

    @model_validator(mode="after")
    def check_totals(self) -> Self:
        """The three balances from the specification, section 5.4."""
        counted = sum(option.votes for option in self.options)
        if counted != self.valid_votes:
            raise ValueError(
                f"options add up to {counted}, valid_votes says {self.valid_votes}"
            )

        cast = self.valid_votes + self.null_votes + self.blank_votes
        if cast != self.voters:
            raise ValueError(
                f"valid + null + blank is {cast}, voters says {self.voters}"
            )

        if self.voters > self.eligible_voters:
            raise ValueError(
                f"voters ({self.voters}) exceeds "
                f"eligible_voters ({self.eligible_voters})"
            )
        return self

    @property
    def turnout(self) -> float:
        """Percentage of eligible voters who cast a ballot."""
        if not self.eligible_voters:
            return 0.0
        return self.voters / self.eligible_voters * 100

    def share(self, option: Option) -> float:
        """Percentage of VALID votes obtained by an option."""
        if not self.valid_votes:
            return 0.0
        return option.votes / self.valid_votes * 100


# ─────────────────────── identification (field `data`) ───────────────────────


class Process(WireModel):
    code: str = Field(alias="codigo", min_length=1, max_length=32)
    name: str = Field(alias="nombre", min_length=1)
    kind: str | None = Field(default=None, alias="tipo")


class Location(WireModel):
    """Where the polling station was set up.

    Coordinates travel at the top level of the registration request, not
    inside `data`, so they are attached afterwards by the service layer.
    The viewer only offers "open in maps" when both are present: a ubigeo
    identifies a district, not a school, and a pin on a district centroid
    would tell the citizen something false about where they voted.
    """

    venue: str | None = Field(default=None, alias="local")
    address: str | None = Field(default=None, alias="direccion")
    district: str | None = Field(default=None, alias="distrito")
    province: str | None = Field(default=None, alias="provincia")
    department: str | None = Field(default=None, alias="departamento")
    ubigeo: Ubigeo | None = None

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def reject_null_island(self) -> Self:
        """(0, 0) is a valid coordinate off the coast of Africa.

        Senders use it to mean "no location". Treat it as absent instead of
        dropping a pin in the Gulf of Guinea.
        """
        if self.latitude == 0 and self.longitude == 0:
            self.latitude = None
            self.longitude = None
        return self

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def is_displayable(self) -> bool:
        """Any one of these is enough to render the location block."""
        return bool(self.venue or self.district or self.ubigeo)


class SheetInfo(WireModel):
    kind: str | None = Field(default=None, alias="tipo")
    pages: int | None = Field(default=None, alias="paginas", ge=1)


class RecordData(WireModel):
    """Contents of the base64 `data` field."""

    version: str = "1.0"
    polling_station: str = Field(alias="mesa", min_length=1)
    folio: str | None = None
    process: Process = Field(alias="proceso")
    location: Location | None = Field(default=None, alias="ubicacion")
    sheet: SheetInfo | None = Field(default=None, alias="acta")


# ────────────────────────────── base64 helpers ───────────────────────────────


def decode_payload(encoded: str, model: type[WireModel]) -> WireModel:
    """Decode a base64 field (`info` or `data`) into its model.

    Raises ValueError with a message that names the failing stage, so an
    operator can tell "not base64" from "not JSON" from "fails validation".
    """
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"not valid base64: {exc}") from exc

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc

    return model.model_validate(payload)


def encode_payload(model: WireModel) -> str:
    """Serialise a model back to the base64 wire form, Spanish keys included."""
    raw = model.model_dump_json(by_alias=True, exclude_none=True)
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


# ────────────────────────────── attestation ──────────────────────────────────


class RecordStatus(str, Enum):
    VERIFIED = "verified"
    ALTERED = "altered"
    PENDING = "pending"
    NOT_FOUND = "not_found"


class Anchor(WireModel):
    """One network where the evidence was recorded."""

    key: str
    label: str
    network: str
    value: str
    url: str
    logo: str | None = None
    action: str | None = None
    is_root: bool = False


class Attestation(WireModel):
    evidence: Hex64
    trx_id: Hex40
    block_number: str | None = None
    block_hash: str | None = None
    sealed_at: str | None = None
    anchored_at: str | None = None
    anchors: list[Anchor] = Field(default_factory=list)
