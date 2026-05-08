"""Test fixtures — mock data for unit / integration tests."""
import json

MOCK_USER = {
    "email": "test@govgrant.in",
    "password": "testpass123",
    "name": "Test User",
}

MOCK_PROFILE = {
    "name": "GreenLeaf Organics",
    "type": "private_limited",
    "sector": "food_processing",
    "state": "Maharashtra",
    "city": "Pune",
    "team_size": 12,
    "revenue_inr": 8000000,
    "funding_purpose": "technology_upgrade",
}

MOCK_RANKED_SCHEME = {
    "scheme_name": "PM FME Scheme",
    "match_score": 92,
    "rank": 1,
    "reason": "Directly targets food processing MSMEs",
    "urgency_score": 8.5,
    "composite_rank": 1,
    "portal_url": "https://pmfme.mofpi.gov.in/",
    "deadline": "2025-12-31",
    "grant_amount": "₹10,00,000",
}

MOCK_DOCUMENTS = [
    {"name": "Aadhaar Card", "description": "Of all directors", "mandatory": True},
    {"name": "PAN Card", "description": "Company and promoters", "mandatory": True},
    {"name": "Certificate of Incorporation", "description": "MCA cert", "mandatory": True},
]

MOCK_COVER_SUMMARY = (
    "We are GreenLeaf Organics, a private limited food processing company "
    "based in Pune, Maharashtra..."
)
