import pytest
from fastapi import HTTPException

from app.presentation.api.v1.ownership import (
    owned_analysis_query,
    require_owned_athlete,
)


class MissingRecordSession:
    statement = None

    async def scalar(self, statement):
        self.statement = statement
        return None


@pytest.mark.parametrize("owner_id", [1, 27])
async def test_athlete_access_query_requires_matching_owner(owner_id: int) -> None:
    session = MissingRecordSession()

    with pytest.raises(HTTPException) as error:
        await require_owned_athlete(session, athlete_id=82, owner_id=owner_id)

    assert error.value.status_code == 404
    sql = str(session.statement)
    assert "athletes.owner_user_id" in sql
    assert owner_id in session.statement.compile().params.values()


def test_analysis_scope_follows_video_test_and_athlete_owner() -> None:
    query = owned_analysis_query(owner_id=27)
    sql = str(query)

    assert "JOIN videos" in sql
    assert "JOIN tests" in sql
    assert "JOIN athletes" in sql
    assert "athletes.owner_user_id" in sql
    assert 27 in query.compile().params.values()
