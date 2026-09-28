COMPANY = "/api/v1/company"

ABC_PROFILE = {
    "name": "ABC Technologies",
    "description": "AI-powered CRM solutions for small and medium-sized businesses.",
    "website": "www.abctech.com",
    "industry": "Software",
    "location": "Bengaluru, India",
    "contact_person": "Anjali Sharma",
    "contact_email": "anjali@abctech.com",
    "contact_phone": "+91 98765 43210",
    "address": "12 MG Road, Bengaluru",
    "services": [
        {"name": "CRM", "description": "Customer relationship management"},
        {"name": "Sales automation"},
        {"name": "Analytics"},
    ],
    "target_customers": [{"segment": "Small and medium-sized businesses"}],
    "value_propositions": [{"statement": "Reduce manual sales work and improve productivity."}],
    "social_links": [{"platform": "LinkedIn", "url": "https://www.linkedin.com/company/abctech"}],
}


def create_company(client, headers, profile=None):
    response = client.post(COMPANY, json=profile or ABC_PROFILE, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_company(client, auth_headers):
    body = create_company(client, auth_headers)
    assert body["name"] == "ABC Technologies"
    assert body["website"] == "https://www.abctech.com/"
    assert [s["name"] for s in body["services"]] == ["CRM", "Sales automation", "Analytics"]
    assert body["target_customers"][0]["segment"] == "Small and medium-sized businesses"
    assert body["value_propositions"][0]["statement"].startswith("Reduce manual")
    assert body["social_links"][0]["platform"] == "LinkedIn"
    assert "user_id" not in body


def test_me_reports_company_after_creation(client, auth_headers):
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["has_company"] is False
    create_company(client, auth_headers)
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["has_company"] is True


def test_get_company(client, auth_headers):
    assert client.get(COMPANY, headers=auth_headers).status_code == 404
    create_company(client, auth_headers)
    response = client.get(COMPANY, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["contact_email"] == "anjali@abctech.com"


def test_cannot_create_second_company(client, auth_headers):
    create_company(client, auth_headers)
    response = client.post(COMPANY, json=ABC_PROFILE, headers=auth_headers)
    assert response.status_code == 409


def test_update_company_replaces_lists(client, auth_headers):
    create_company(client, auth_headers)
    updated = {
        **ABC_PROFILE,
        "name": "ABC Tech",
        "services": [{"name": "CRM"}],
        "social_links": ABC_PROFILE["social_links"],  # identical URL re-added is fine
    }
    response = client.put(COMPANY, json=updated, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "ABC Tech"
    assert [s["name"] for s in body["services"]] == ["CRM"]
    assert len(body["social_links"]) == 1


def test_update_without_company_is_404(client, auth_headers):
    assert client.put(COMPANY, json=ABC_PROFILE, headers=auth_headers).status_code == 404


def test_company_validation(client, auth_headers):
    cases = [
        {**ABC_PROFILE, "name": ""},
        {**ABC_PROFILE, "name": "   "},
        {**ABC_PROFILE, "description": ""},
        {**ABC_PROFILE, "contact_email": "not-an-email"},
        {**ABC_PROFILE, "website": "ftp://abctech.com"},
        {**ABC_PROFILE, "website": "https://"},
        {**ABC_PROFILE, "contact_phone": "call me"},
        {**ABC_PROFILE, "name": "x" * 201},
        {**ABC_PROFILE, "social_links": [{"platform": "X", "url": "javascript:alert(1)"}]},
    ]
    for payload in cases:
        response = client.post(COMPANY, json=payload, headers=auth_headers)
        assert response.status_code == 422, payload


def test_company_requires_authentication(client):
    assert client.get(COMPANY).status_code == 401
    assert client.post(COMPANY, json=ABC_PROFILE).status_code == 401
    assert client.put(COMPANY, json=ABC_PROFILE).status_code == 401
