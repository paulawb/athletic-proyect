from app.application.dto.athlete_dto import AthleteResponseDTO
from app.domain.services.athlete_code import athlete_code, athlete_id_from_code


def test_athlete_code_round_trip():
    assert athlete_code(7) == "ATL-0007"
    assert athlete_id_from_code("atl-0007") == 7
    assert athlete_id_from_code("Juan") is None


def test_athlete_response_never_exposes_names():
    payload = AthleteResponseDTO(id=3, identification="1", age=17, gender="M").model_dump()

    assert payload["code"] == "ATL-0003"
    assert "first_name" not in payload and "last_name" not in payload
