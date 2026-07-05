from backend.api.schemas import UserProfileUpdateRequest


def test_profile_update_blank_fields_become_none():
    request = UserProfileUpdateRequest(
        display_name="",
        avatar_url=" ",
        username="",
        full_name="",
        age="",
        role_title="",
        company="",
        bio="",
    )

    assert request.display_name is None
    assert request.avatar_url is None
    assert request.username is None
    assert request.full_name is None
    assert request.age is None
    assert request.role_title is None
    assert request.company is None
    assert request.bio is None


def test_profile_update_keeps_valid_values():
    request = UserProfileUpdateRequest(
        display_name="Jane",
        username="jane_analyst",
        age="29",
    )

    assert request.display_name == "Jane"
    assert request.username == "jane_analyst"
    assert request.age == 29
