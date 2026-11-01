"""
Comprehensive tests for email OTP authentication.

Tests both approved administrators, OTP flows, and security properties.
"""
import pytest
import os
from datetime import datetime, timedelta
from datetime import timezone as tz

# Set approved emails for tests
os.environ["KIBOLENS_ALLOWED_EMAILS"] = "rayanmohammedrafeeq@gmail.com,rakinmohammedrafeeq@gmail.com"

from app.core.config import get_settings
from app.services.auth import (
    DuplicateEmailError,
    DuplicateUsernameError,
    EmailNotAllowedError,
    InvalidCredentialsError,
    authenticate_by_email,
    provision_administrator,
)
from app.services.email import MockEmailService
from app.services.otp import (
    OTPAlreadyConsumedError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsError,
    OTPResendCooldownError,
    can_resend_otp,
    create_otp_challenge,
    generate_otp,
    verify_otp,
)
from app.models.user import User
from app.models.otp_challenge import OTPChallenge
from sqlalchemy import select

UTC = tz.utc

# Approved administrator emails from requirements
ADMIN_EMAIL_1 = "rayanmohammedrafeeq@gmail.com"
ADMIN_EMAIL_2 = "rakinmohammedrafeeq@gmail.com"
DISALLOWED_EMAIL = "unauthorized@example.com"


class TestAdministratorProvisioning:
    """Test multi-administrator provisioning with allowlist."""
    
    def test_provision_first_administrator(self, database):
        """Can provision first approved administrator."""
        settings = get_settings()
        
        user = provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        assert user.email == ADMIN_EMAIL_1
        assert user.email_normalized == ADMIN_EMAIL_1.lower()
        assert user.username == "rayan"
        assert user.role == "admin"
        assert user.password_hash is not None
        assert user.password_hash != "SecurePassword123!"
    
    def test_provision_second_administrator(self, database):
        """Can provision second approved administrator independently."""
        settings = get_settings()
        
        # Provision first admin
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        # Provision second admin
        user2 = provision_administrator(
            database,
            username="rakin",
            email=ADMIN_EMAIL_2,
            password="AnotherSecure456!",
            settings=settings
        )
        
        assert user2.email == ADMIN_EMAIL_2
        assert user2.email_normalized == ADMIN_EMAIL_2.lower()
        assert user2.username == "rakin"
        assert user2.role == "admin"
        
        # Verify both exist
        admin_count = database.scalar(
            select(User).where(User.role == "admin")
        )
        assert database.query(User).filter(User.role == "admin").count() == 2
    
    def test_reject_disallowed_email(self, database):
        """Reject email not in administrator allowlist."""
        settings = get_settings()
        
        with pytest.raises(EmailNotAllowedError) as exc_info:
            provision_administrator(
                database,
                username="hacker",
                email=DISALLOWED_EMAIL,
                password="SecurePassword123!",
                settings=settings
            )
        
        assert "not in the administrator allowlist" in str(exc_info.value)
    
    def test_reject_duplicate_email(self, database):
        """Reject duplicate email address."""
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        with pytest.raises(DuplicateEmailError) as exc_info:
            provision_administrator(
                database,
                username="rayan2",
                email=ADMIN_EMAIL_1,  # Same email
                password="AnotherPassword!",
                settings=settings
            )
        
        assert "already registered" in str(exc_info.value)
    
    def test_reject_duplicate_username(self, database):
        """Reject duplicate username."""
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        with pytest.raises(DuplicateUsernameError) as exc_info:
            provision_administrator(
                database,
                username="rayan",  # Same username
                email=ADMIN_EMAIL_2,
                password="AnotherPassword!",
                settings=settings
            )
        
        assert "already taken" in str(exc_info.value)
    
    def test_email_normalization(self, database):
        """Email addresses are normalized to lowercase."""
        settings = get_settings()
        
        # Use an email from the allowed list, just with different casing
        user = provision_administrator(
            database,
            username="rayan",
            email="RaYanMohammedRafeeq@Gmail.COM",  # Approved email with mixed case
            password="SecurePassword123!",
            settings=settings
        )
        
        assert user.email_normalized == ADMIN_EMAIL_1.lower()


class TestAuthentication:
    """Test email-based authentication."""
    
    def test_authenticate_by_email(self, database):
        """Can authenticate using email and password."""
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        assert user.email == ADMIN_EMAIL_1
    
    def test_authenticate_case_insensitive_email(self, database):
        """Email authentication is case-insensitive."""
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        # Try with different casing
        user = authenticate_by_email(
            database, 
            ADMIN_EMAIL_1.upper(), 
            "SecurePassword123!"
        )
        assert user.email == ADMIN_EMAIL_1
    
    def test_reject_wrong_password(self, database):
        """Reject invalid password."""
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        with pytest.raises(InvalidCredentialsError):
            authenticate_by_email(database, ADMIN_EMAIL_1, "WrongPassword!")
    
    def test_reject_unknown_email(self, database):
        """Reject unknown email address."""
        with pytest.raises(InvalidCredentialsError):
            authenticate_by_email(database, "unknown@example.com", "AnyPassword!")


class TestOTPGeneration:
    """Test OTP generation and storage."""
    
    def test_generate_otp_format(self):
        """OTP is 6 digits."""
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()
    
    def test_generate_otp_uniqueness(self):
        """Generated OTPs are different (statistical test)."""
        otps = {generate_otp() for _ in range(100)}
        # Should have many unique values (allowing for some collisions)
        assert len(otps) > 80
    
    def test_create_otp_challenge(self, database):
        """Can create OTP challenge."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        challenge = create_otp_challenge(database, str(user.id), otp, settings)
        
        assert challenge.user_id == user.id
        assert challenge.consumed == False
        assert challenge.attempts == 0
        assert challenge.invalidated_at is None
        # Ensure both datetimes are timezone-aware for comparison
        assert challenge.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)
        
        # OTP is stored as digest, not plaintext
        assert challenge.otp_digest != otp
    
    def test_invalidate_old_challenges(self, database):
        """Creating new OTP invalidates old ones."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp1 = generate_otp()
        challenge1 = create_otp_challenge(database, str(user.id), otp1, settings)
        
        otp2 = generate_otp()
        challenge2 = create_otp_challenge(database, str(user.id), otp2, settings)
        
        # Refresh first challenge
        database.refresh(challenge1)
        
        # Old challenge should be invalidated
        assert challenge1.invalidated_at is not None
        assert challenge2.invalidated_at is None


class TestOTPVerification:
    """Test OTP verification and security."""
    
    def test_verify_valid_otp(self, database):
        """Can verify valid OTP."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        challenge = verify_otp(database, str(user.id), otp, settings)
        assert challenge.consumed == True
    
    def test_reject_wrong_otp(self, database):
        """Reject incorrect OTP."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        with pytest.raises(OTPInvalidError):
            verify_otp(database, str(user.id), "000000", settings)
    
    def test_reject_expired_otp(self, database):
        """Reject expired OTP."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        challenge = create_otp_challenge(database, str(user.id), otp, settings)
        
        # Manually expire the challenge
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
        
        with pytest.raises(OTPExpiredError):
            verify_otp(database, str(user.id), otp, settings)
    
    def test_reject_replayed_otp(self, database):
        """Reject already-consumed OTP (replay attack)."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # First verification succeeds
        verify_otp(database, str(user.id), otp, settings)
        
        # Second verification with same OTP fails
        with pytest.raises(OTPInvalidError):
            verify_otp(database, str(user.id), otp, settings)
    
    def test_max_attempts(self, database):
        """Reject OTP after maximum failed attempts."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Use up all attempts
        for _ in range(settings.otp_max_attempts):
            try:
                verify_otp(database, str(user.id), "000000", settings)
            except OTPInvalidError:
                pass
        
        # Next attempt should fail with max attempts error
        with pytest.raises(OTPMaxAttemptsError):
            verify_otp(database, str(user.id), otp, settings)


class TestOTPResend:
    """Test OTP resend and cooldown."""
    
    def test_can_resend_initially(self, database):
        """Can send first OTP immediately."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        can_send, seconds = can_resend_otp(database, str(user.id), settings)
        assert can_send == True
        assert seconds == 0
    
    def test_resend_cooldown(self, database):
        """Enforce cooldown between OTP sends."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # Create first OTP
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Immediate resend should be blocked
        can_send, seconds = can_resend_otp(database, str(user.id), settings)
        assert can_send == False
        assert seconds > 0
        assert seconds <= settings.otp_resend_cooldown_seconds
    
    def test_resend_after_cooldown(self, database):
        """Can resend after cooldown expires."""
        settings = get_settings()
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # Create first OTP
        otp = generate_otp()
        challenge = create_otp_challenge(database, str(user.id), otp, settings)
        
        # Manually set created_at to past
        challenge.created_at = datetime.now(UTC) - timedelta(
            seconds=settings.otp_resend_cooldown_seconds + 1
        )
        database.commit()
        
        # Should be able to resend now
        can_send, seconds = can_resend_otp(database, str(user.id), settings)
        assert can_send == True
        assert seconds == 0


class TestEmailService:
    """Test email service integration."""
    
    def test_mock_email_service(self):
        """MockEmailService records emails."""
        service = MockEmailService()
        
        service.send_otp_email("test@example.com", "123456")
        
        assert len(service.sent_emails) == 1
        assert service.sent_emails[0]["to"] == "test@example.com"
        assert service.sent_emails[0]["otp"] == "123456"
    
    def test_get_last_otp(self):
        """Can retrieve last OTP sent to an address."""
        service = MockEmailService()
        
        service.send_otp_email("test@example.com", "111111")
        service.send_otp_email("other@example.com", "222222")
        service.send_otp_email("test@example.com", "333333")
        
        assert service.get_last_otp("test@example.com") == "333333"
        assert service.get_last_otp("other@example.com") == "222222"
        assert service.get_last_otp("unknown@example.com") is None


class TestEndToEndOTPFlow:
    """End-to-end integration tests for both administrators."""
    
    def test_full_otp_flow_admin1(self, database):
        """Complete OTP authentication for first administrator."""
        settings = get_settings()
        email_service = MockEmailService()
        
        # 1. Provision administrator
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        # 2. Authenticate with password
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # 3. Generate and send OTP
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        email_service.send_otp_email(user.email, otp)
        
        # 4. Verify OTP from email
        sent_otp = email_service.get_last_otp(ADMIN_EMAIL_1)
        assert sent_otp == otp
        
        challenge = verify_otp(database, str(user.id), sent_otp, settings)
        assert challenge.consumed == True
    
    def test_full_otp_flow_admin2(self, database):
        """Complete OTP authentication for second administrator."""
        settings = get_settings()
        email_service = MockEmailService()
        
        # 1. Provision administrator
        provision_administrator(
            database,
            username="rakin",
            email=ADMIN_EMAIL_2,
            password="AnotherSecure456!",
            settings=settings
        )
        
        # 2. Authenticate with password
        user = authenticate_by_email(database, ADMIN_EMAIL_2, "AnotherSecure456!")
        
        # 3. Generate and send OTP
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        email_service.send_otp_email(user.email, otp)
        
        # 4. Verify OTP
        sent_otp = email_service.get_last_otp(ADMIN_EMAIL_2)
        challenge = verify_otp(database, str(user.id), sent_otp, settings)
        assert challenge.consumed == True
    
    def test_independent_otp_sessions(self, database):
        """Both administrators can have simultaneous independent OTP sessions."""
        settings = get_settings()
        email_service = MockEmailService()
        
        # Provision both administrators
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        provision_administrator(
            database,
            username="rakin",
            email=ADMIN_EMAIL_2,
            password="AnotherSecure456!",
            settings=settings
        )
        
        # Both authenticate and get OTPs
        user1 = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        user2 = authenticate_by_email(database, ADMIN_EMAIL_2, "AnotherSecure456!")
        
        otp1 = generate_otp()
        otp2 = generate_otp()
        
        create_otp_challenge(database, str(user1.id), otp1, settings)
        create_otp_challenge(database, str(user2.id), otp2, settings)
        
        # Both can verify independently
        verify_otp(database, str(user1.id), otp1, settings)
        verify_otp(database, str(user2.id), otp2, settings)



class TestPasswordOnlyAuthenticationPrevention:
    """
    Regression tests proving password-only authentication NEVER creates sessions.
    
    SECURITY REQUIREMENT: No endpoint may create authenticated session with password alone.
    OTP verification is mandatory for all session creation.
    """
    
    def test_password_verification_does_not_create_session(self, database, client):
        """
        CRITICAL: Verify that successful password authentication does NOT create a session.
        
        This is the core security requirement - password alone must never be sufficient.
        """
        settings = get_settings()
        
        # Provision administrator
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        # Attempt login with correct password
        response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL_1, "password": "SecurePassword123!"}
        )
        
        # Should return 200 with OTP required response
        assert response.status_code == 200
        data = response.json()
        assert data["requires_otp"] == True
        assert "masked_email" in data
        
        # CRITICAL: Verify NO session was created
        # Attempt to access protected endpoint should fail
        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 401, "Password-only auth must NOT create session"
        
        # Verify no session cookie was set
        assert "kibolens_session" not in client.cookies
    
    def test_no_legacy_password_only_endpoint_exists(self, client):
        """
        Ensure no password-only authentication endpoint exists.
        
        Any endpoint that accepts username/password and creates session is a security bypass.
        """
        # Try common legacy endpoint patterns
        legacy_endpoints = [
            "/api/v1/auth/login-legacy",
            "/api/v1/auth/login-password",
            "/api/v1/auth/simple-login",
        ]
        
        for endpoint in legacy_endpoints:
            response = client.post(
                endpoint,
                json={"username": "admin", "password": "password"}
            )
            # Should be 404 (not found) or 405 (method not allowed)
            assert response.status_code in [404, 405], \
                f"Legacy endpoint {endpoint} should not exist"
    
    def test_session_creation_requires_otp_verification(self, database):
        """
        Verify that create_session is only called after successful OTP verification.
        
        This tests the code path - session creation must only occur in verify-otp endpoint.
        """
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # Generate and verify OTP
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Before OTP verification, no session should exist
        from app.models.session import UserSession
        sessions_before = database.query(UserSession).count()
        assert sessions_before == 0
        
        # Verify OTP
        verify_otp(database, str(user.id), otp, settings)
        
        # After OTP verification, session creation is allowed
        # (but still requires explicit create_session call in endpoint)
        # The verify_otp function itself does NOT create sessions
        sessions_after = database.query(UserSession).count()
        assert sessions_after == 0, "verify_otp must not create sessions directly"
    
    def test_multiple_login_attempts_without_otp_never_create_session(self, database, client):
        """
        Ensure repeated password authentication attempts never bypass OTP requirement.
        """
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        # Try login multiple times with correct password
        for _ in range(3):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": ADMIN_EMAIL_1, "password": "SecurePassword123!"}
            )
            assert response.status_code == 200
            assert response.json()["requires_otp"] == True
            
            # Each time, verify no session was created
            me_response = client.get("/api/v1/auth/me")
            assert me_response.status_code == 401
    
    def test_expired_otp_prevents_session_creation(self, database):
        """
        Verify that expired OTP cannot be used to create session.
        """
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # Create OTP and manually expire it
        otp = generate_otp()
        challenge = create_otp_challenge(database, str(user.id), otp, settings)
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
        
        # Attempt to verify expired OTP
        with pytest.raises(OTPExpiredError):
            verify_otp(database, str(user.id), otp, settings)
        
        # Verify no session exists
        from app.models.session import UserSession
        assert database.query(UserSession).count() == 0
    
    def test_wrong_otp_prevents_session_creation(self, database):
        """
        Verify that incorrect OTP cannot create session.
        """
        settings = get_settings()
        
        provision_administrator(
            database,
            username="rayan",
            email=ADMIN_EMAIL_1,
            password="SecurePassword123!",
            settings=settings
        )
        
        user = authenticate_by_email(database, ADMIN_EMAIL_1, "SecurePassword123!")
        
        # Create valid OTP
        otp = generate_otp()
        create_otp_challenge(database, str(user.id), otp, settings)
        
        # Attempt verification with wrong OTP
        with pytest.raises(OTPInvalidError):
            verify_otp(database, str(user.id), "000000", settings)
        
        # Verify no session exists
        from app.models.session import UserSession
        assert database.query(UserSession).count() == 0
