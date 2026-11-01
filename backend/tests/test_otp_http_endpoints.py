"""
HTTP endpoint tests for OTP authentication flow.

These tests verify the complete login → OTP → verification flow through the API.
"""
from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc

import pytest
from app.core.config import get_settings
from app.services.auth import provision_administrator
from app.services.email import MockEmailService
from app.services.otp import create_otp_challenge, generate_otp
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


# Test administrator emails (configured in conftest.py)
ADMIN_EMAIL_1 = "admin@example.com"
ADMIN_EMAIL_2 = "other@example.com"


class TestOTPHTTPEndpoints:
    """Test OTP authentication through HTTP endpoints."""
    
    def test_complete_otp_flow_success(self, client: TestClient, database: Session):
        """Complete successful OTP authentication flow."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Step 1: Login with email/password
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL_1, "password": "TestPassword123!"}
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert login_data["requires_otp"] == True
        assert "masked_email" in login_data
        
        # Verify no session created yet
        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 401
        
        # Get the OTP that would have been sent
        # In test environment, MockEmailService is used
        # We need to get the OTP from the database challenge
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # Get the OTP challenge
        from app.models.otp_challenge import OTPChallenge
        challenge = database.scalar(
            select(OTPChallenge)
            .where(OTPChallenge.user_id == user.id)
            .order_by(OTPChallenge.created_at.desc())
        )
        assert challenge is not None
        
        # Generate a valid OTP that matches the challenge
        # We need to use the same OTP that was used to create the challenge
        # For testing, we'll create a new challenge with a known OTP
        otp = "123456"
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Step 2: Verify OTP
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp}
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert "user" in verify_data
        assert "csrf_token" in verify_data
        assert verify_data["user"]["email"] == ADMIN_EMAIL_1
        
        # Step 3: Verify session created
        me_response = client.get("/api/v1/auth/me", cookies=client.cookies)
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["email"] == ADMIN_EMAIL_1
    
    def test_wrong_otp_rejected(self, client: TestClient, database: Session):
        """Wrong OTP is rejected."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Step 1: Login
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL_1, "password": "TestPassword123!"}
        )
        assert login_response.status_code == 200
        
        # Step 2: Try wrong OTP
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": "000000"}
        )
        assert verify_response.status_code == 401
        assert "Invalid verification code" in verify_response.json()["detail"]
        
        # Verify no session created
        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 401
    
    def test_expired_otp_rejected(self, client: TestClient, database: Session):
        """Expired OTP is rejected."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Get user
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # Create expired OTP challenge
        otp = "123456"
        from app.models.otp_challenge import OTPChallenge
        challenge = OTPChallenge(
            user_id=user.id,
            otp_digest="dummy",  # Will be overwritten by create_otp_challenge
            expires_at=datetime.now(UTC) - timedelta(seconds=1),  # Already expired
            consumed=False,
            attempts=0,
        )
        # Use the service to create properly
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Manually expire it
        challenge = database.scalar(
            select(OTPChallenge)
            .where(OTPChallenge.user_id == user.id)
            .order_by(OTPChallenge.created_at.desc())
        )
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
        
        # Try to verify expired OTP
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp}
        )
        assert verify_response.status_code == 401
        assert "expired" in verify_response.json()["detail"].lower()
    
    def test_consumed_otp_rejected(self, client: TestClient, database: Session):
        """Already-consumed OTP is rejected (replay attack)."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Get user
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # Create OTP challenge
        otp = "123456"
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # First verification succeeds
        verify_response1 = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp}
        )
        assert verify_response1.status_code == 200
        
        # Second verification with same OTP fails (OTP is consumed)
        verify_response2 = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp}
        )
        assert verify_response2.status_code == 401
        # Generic error for security - should not find the consumed challenge
    
    def test_max_attempts_exceeded(self, client: TestClient, database: Session):
        """OTP rejected after max attempts."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Get user
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # Create OTP challenge
        otp = "123456"
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Exhaust attempts with wrong OTP (avoid rate limiter by using direct OTP service)
        from app.services.otp import verify_otp as verify_otp_service, OTPInvalidError, OTPMaxAttemptsError
        
        for _ in range(settings.otp_max_attempts):
            try:
                verify_otp_service(database, str(user.id), "000000", settings)
            except OTPInvalidError:
                pass  # Expected
        
        # Now try through HTTP endpoint - should fail due to max attempts
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp}
        )
        assert verify_response.status_code == 401
        # Could be rate limited or max attempts - both are valid security responses
    
    def test_new_login_invalidates_previous_otp(self, client: TestClient, database: Session):
        """Requesting a new OTP invalidates the previous challenge."""
        settings = get_settings()
        
        # Provision admin
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,
            password="TestPassword123!",
            settings=settings
        )
        
        # Get user
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # First OTP
        otp1 = "111111"
        create_otp_challenge(database, str(user.id), otp1, settings)
        
        # Second OTP (invalidates first)
        otp2 = "222222"
        create_otp_challenge(database, str(user.id), otp2, settings)
        
        # First OTP should fail
        verify_response1 = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp1}
        )
        assert verify_response1.status_code == 401
        
        # Second OTP should succeed
        verify_response2 = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": ADMIN_EMAIL_1, "otp": otp2}
        )
        assert verify_response2.status_code == 200
    
    def test_unknown_email_rejected_generically(self, client: TestClient, database: Session):
        """Unknown email returns generic error (prevents enumeration)."""
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": "unknown@example.com", "otp": "123456"}
        )
        assert verify_response.status_code == 401
        # Should not reveal whether email exists
        assert "Invalid verification code" in verify_response.json()["detail"]
    
    def test_case_insensitive_email_lookup(self, client: TestClient, database: Session):
        """Email lookup is case-insensitive."""
        settings = get_settings()
        
        # Provision admin with lowercase email
        provision_administrator(
            database,
            username="testadmin",
            email=ADMIN_EMAIL_1,  # admin@example.com
            password="TestPassword123!",
            settings=settings
        )
        
        # Get user
        from app.models.user import User
        from sqlalchemy import select
        user = database.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL_1.lower()))
        
        # Create OTP
        otp = "123456"
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Verify with different case
        verify_response = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": "ADMIN@EXAMPLE.COM", "otp": otp}
        )
        assert verify_response.status_code == 200
