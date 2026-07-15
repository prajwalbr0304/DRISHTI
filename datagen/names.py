"""Name synthesis helpers built on the Karnataka name pools."""
from __future__ import annotations

from . import reference as ref
from .rng import RNG


def person_name(rng: RNG, gender: int) -> str:
    if gender == ref.GENDER_FEMALE:
        first = rng.choice(ref.FEMALE_NAMES)
    else:
        first = rng.choice(ref.MALE_NAMES)
    return f"{first} {rng.choice(ref.SURNAMES)}"


def gang_name(rng: RNG) -> str:
    return f"{rng.choice(ref.GANG_ADJ)} {rng.choice(ref.GANG_NOUN)}"


def vehicle_plate(rng: RNG) -> str:
    rto = rng.choice(ref.KA_RTO)
    series = chr(int(rng.integers(65, 91))) + chr(int(rng.integers(65, 91)))
    num = int(rng.integers(1000, 10000))
    return f"{rto}{series}{num}"


def phone_number(rng: RNG) -> str:
    return "9" + "".join(str(int(d)) for d in rng.integers(0, 10, 9))
