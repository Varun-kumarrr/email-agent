from app.schemas.signature import EXAMPLE_SIGNATURE
from tests.test_company import create_company
from tests.test_isolation import XYZ_PROFILE

SIGNATURE = "/api/v1/signature"
PAYLOAD = {"signature_text": EXAMPLE_SIGNATURE, "enabled": True, "append_automatically": True}


def test_signature_crud(client, auth_headers):
    create_company(client, auth_headers)
    assert client.get(SIGNATURE, headers=auth_headers).status_code == 404

    created = client.post(SIGNATURE, json=PAYLOAD, headers=auth_headers)
    assert created.status_code == 201
    assert created.json()["signature_text"].startswith("Best Regards,\nAnjali")

    assert client.post(SIGNATURE, json=PAYLOAD, headers=auth_headers).status_code == 409

    updated = client.put(
        SIGNATURE,
        json={"signature_text": "Thanks,\nAnjali", "enabled": True, "append_automatically": False},
        headers=auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["append_automatically"] is False

    fetched = client.get(SIGNATURE, headers=auth_headers).json()
    assert fetched["signature_text"] == "Thanks,\nAnjali"

    assert client.delete(SIGNATURE, headers=auth_headers).status_code == 204
    assert client.get(SIGNATURE, headers=auth_headers).status_code == 404


def test_signature_validation(client, auth_headers):
    create_company(client, auth_headers)
    for text in ["", "   ", "x" * 2001]:
        response = client.post(SIGNATURE, json={**PAYLOAD, "signature_text": text}, headers=auth_headers)
        assert response.status_code == 422


def test_signature_requires_company_and_auth(client, auth_headers):
    assert client.get(SIGNATURE).status_code == 401
    assert client.post(SIGNATURE, json=PAYLOAD, headers=auth_headers).status_code == 404


def test_signatures_are_isolated(client, auth_headers, other_auth_headers):
    create_company(client, auth_headers)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    client.post(SIGNATURE, json=PAYLOAD, headers=auth_headers)

    assert client.get(SIGNATURE, headers=other_auth_headers).status_code == 404
    # B updating/deleting affects only B (who has none) — never A's signature.
    assert client.put(SIGNATURE, json=PAYLOAD, headers=other_auth_headers).status_code == 404
    assert client.delete(SIGNATURE, headers=other_auth_headers).status_code == 404
    assert client.get(SIGNATURE, headers=auth_headers).status_code == 200
