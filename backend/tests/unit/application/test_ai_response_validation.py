import pytest

from app.application.services.ai_response_validation import validate_ai_payload
from app.domain.catalog.exceptions import AIResponseValidationError

VALID = {
    "products": [
        {
            "item_number": "1",
            "name": "Cable de cobre",
            "description": "Conductor 2 AWG",
            "quantity": 100,
            "unit": "m",
            "suggested_category": "Eléctrico",
            "technical_specifications": [{"name": "Calibre", "value": "2 AWG"}],
            "observations": None,
            "confidence": 0.94,
            "evidence": [
                {
                    "page": 1,
                    "fragment": "Cable de cobre 2 AWG",
                    "confidence": 0.96,
                    "coordinates": None,
                }
            ],
        }
    ]
}


def test_valid_ai_json_is_parsed() -> None:
    parsed = validate_ai_payload(VALID)
    assert parsed.products[0].name == "Cable de cobre"
    assert parsed.products[0].technical_specifications[0].value == "2 AWG"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["products"][0].pop("name"),
        lambda payload: payload["products"][0].update(confidence=2),
        lambda payload: payload["products"][0].update(evidence=[]),
        lambda payload: payload["products"][0].update(extra="forbidden"),
    ],
)
def test_invalid_or_incomplete_ai_json_is_rejected(mutation) -> None:
    import copy

    payload = copy.deepcopy(VALID)
    mutation(payload)
    with pytest.raises(AIResponseValidationError):
        validate_ai_payload(payload)
