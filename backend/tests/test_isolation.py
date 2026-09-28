"""Cross-user / cross-company data isolation.

Company-owned data is always resolved from the JWT's user, never from an ID in
the request, so user A has no way to address user B's resources.
"""

from app.main import app
from tests.test_company import ABC_PROFILE, create_company
from tests.test_email_config import SMTP_SETTINGS, create_config

XYZ_PROFILE = {**ABC_PROFILE, "name": "XYZ Corp", "contact_email": "rahul@xyzcorp.com"}
XYZ_SMTP = {**SMTP_SETTINGS, "email": "rahul@xyzcorp.com", "smtp_host": "smtp.xyzcorp.com", "username": "rahul"}


def test_company_profiles_are_isolated(client, auth_headers, other_auth_headers):
    create_company(client, auth_headers)
    # B has no company yet: must get 404, never A's company.
    assert client.get("/api/v1/company", headers=other_auth_headers).status_code == 404

    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert client.get("/api/v1/company", headers=auth_headers).json()["name"] == "ABC Technologies"
    assert client.get("/api/v1/company", headers=other_auth_headers).json()["name"] == "XYZ Corp"


def test_updating_own_company_does_not_touch_other(client, auth_headers, other_auth_headers):
    create_company(client, auth_headers)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    client.put("/api/v1/company", json={**XYZ_PROFILE, "name": "XYZ Renamed"}, headers=other_auth_headers)
    assert client.get("/api/v1/company", headers=auth_headers).json()["name"] == "ABC Technologies"


def test_email_configurations_are_isolated(client, auth_headers, other_auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    assert client.get("/api/v1/email-config", headers=other_auth_headers).status_code == 404

    create_config(client, other_auth_headers, XYZ_SMTP)
    assert client.get("/api/v1/email-config", headers=auth_headers).json()["smtp_host"] == "smtp.abctech.com"
    assert client.get("/api/v1/email-config", headers=other_auth_headers).json()["smtp_host"] == "smtp.xyzcorp.com"


def test_client_supplied_company_id_is_ignored(client, auth_headers, other_auth_headers):
    a = create_company(client, auth_headers)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    # Extra fields such as company_id/user_id are not part of the schema and are ignored.
    response = client.put(
        "/api/v1/company",
        json={**XYZ_PROFILE, "id": a["id"], "company_id": a["id"], "user_id": a["id"]},
        headers=other_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] != a["id"]
    assert client.get("/api/v1/company", headers=auth_headers).json()["name"] == "ABC Technologies"


def test_no_route_accepts_company_or_user_id_path_parameter():
    for route in app.routes:
        path = getattr(route, "path", "")
        assert "{company_id}" not in path and "{user_id}" not in path, path
