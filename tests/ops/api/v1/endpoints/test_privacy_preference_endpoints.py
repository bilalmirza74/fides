from datetime import timedelta
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
from starlette.status import HTTP_200_OK, HTTP_403_FORBIDDEN
from starlette.testclient import TestClient

from fides.api.ops.api.v1.scope_registry import (
    CONSENT_READ,
    CURRENT_PRIVACY_PREFERENCE_READ,
    PRIVACY_PREFERENCE_HISTORY_READ,
)
from fides.api.ops.api.v1.urn_registry import (
    CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY,
    CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID,
    CURRENT_PRIVACY_PREFERENCES,
    HISTORICAL_PRIVACY_PREFERENCES,
    V1_URL_PREFIX,
)
from fides.api.ops.models.privacy_preference import (
    PrivacyPreferenceHistory,
    UserConsentPreference,
)
from fides.api.ops.models.privacy_request import (
    ConsentRequest,
    ExecutionLogStatus,
    PrivacyRequestStatus,
    ProvidedIdentity,
)
from fides.api.ops.schemas.privacy_notice import PrivacyNoticeHistorySchema
from fides.core.config import CONFIG
from tests.conftest import generate_auth_header, generate_role_header_for_user


class TestSavePrivacyPreferencesPrivacyCenter:
    @pytest.fixture(scope="function")
    def verification_code(self) -> str:
        return "abcd"

    @pytest.fixture(scope="function")
    def request_body(self, privacy_notice, verification_code, consent_policy):
        return {
            "browser_identity": {"ga_client_id": "test"},
            "code": verification_code,
            "preferences": [
                {
                    "privacy_notice_history_id": privacy_notice.histories[0].id,
                    "preference": "opt_out",
                }
            ],
            "policy_key": consent_policy.key,
            "request_origin": "privacy_center",
            "url_recorded": "example.com/privacy_center",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_2)...",
            "user_geography": "us_ca",
        }

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_save_privacy_preferences_no_consent_request_id(
        self, api_client, request_body
    ):
        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id='non_existent_consent_id')}",
            json=request_body,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_save_privacy_preferences_no_consent_code(
        self, provided_identity_and_consent_request, api_client, privacy_notice
    ):
        _, consent_request = provided_identity_and_consent_request

        data = {
            "browser_identity": {"ga_client_id": "test_ga_client_id"},
            "code": "12345",
            "preferences": [
                {
                    "privacy_notice_history_id": privacy_notice.histories[0].id,
                    "preference": "opt_out",
                }
            ],
            "request_origin": "privacy_center",
            "url_recorded": "example.com/privacy_center",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_2)...",
            "user_geography": "us_ca",
        }

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=data,
        )
        assert response.status_code == 400
        assert "code expired" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_set_privacy_preferences_invalid_code(
        self,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        request_body,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["code"] = "non_matching_code"
        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert response.status_code == 403
        assert "Incorrect identification" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required", "automatically_approved"
    )
    @mock.patch(
        "fides.api.ops.service.privacy_request.request_runner_service.run_privacy_request.delay"
    )
    def test_verify_then_set_privacy_preferences(
        self,
        run_privacy_request_mock,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        db: Session,
        request_body,
        privacy_notice,
        system,
    ):
        """Verify code and then return privacy preferences"""
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )
        assert response.status_code == 200
        # Assert no existing privacy preferences exist for this identity
        assert response.json() == {"items": [], "total": 0, "page": 1, "size": 50}

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

        response_json = response.json()[0]
        created_privacy_preference_history_id = response_json[
            "privacy_preference_history_id"
        ]
        privacy_preference_history = (
            db.query(PrivacyPreferenceHistory)
            .filter(
                PrivacyPreferenceHistory.id == created_privacy_preference_history_id
            )
            .first()
        )
        assert response_json["preference"] == "opt_out"

        assert (
            response_json["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(privacy_notice.histories[0]).dict()
        )
        db.refresh(consent_request)
        assert consent_request.privacy_request_id

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        response_json = response.json()["items"][0]
        assert response_json["id"] is not None
        assert response_json["preference"] == "opt_out"
        assert (
            response_json["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(privacy_notice.histories[0]).dict()
        )

        privacy_preference_history.delete(db=db)
        assert run_privacy_request_mock.called

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_set_privacy_preferences_invalid_code_respects_attempt_count(
        self,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        request_body,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["code"] = "987632"  # Bad code

        for _ in range(0, CONFIG.security.identity_verification_attempt_limit):
            response = api_client.patch(
                f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
                json=request_body,
            )
            assert response.status_code == 403
            assert "Incorrect identification" in response.json()["detail"]

        assert (
            consent_request._get_cached_verification_code_attempt_count()
            == CONFIG.security.identity_verification_attempt_limit
        )

        request_body["code"] = verification_code
        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"] == f"Attempt limit hit for '{consent_request.id}'"
        )
        assert consent_request.get_cached_verification_code() is None
        assert consent_request._get_cached_verification_code_attempt_count() == 0

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    def test_set_privacy_preferences_no_email_provided(
        self,
        mock_verify_identity: MagicMock,
        db,
        api_client,
        verification_code,
        request_body,
    ):
        provided_identity_data = {
            "privacy_request_id": None,
            "field_name": "email",
            "hashed_value": None,
            "encrypted_value": None,
        }
        provided_identity = ProvidedIdentity.create(db, data=provided_identity_data)

        consent_request_data = {
            "provided_identity_id": provided_identity.id,
        }
        consent_request = ConsentRequest.create(db, data=consent_request_data)
        consent_request.cache_identity_verification_code(verification_code)

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )

        assert response.status_code == 404
        assert mock_verify_identity.called
        assert "missing" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_set_privacy_preferences_no_privacy_preferences_present(
        self,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        request_body,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["preferences"] = None

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert response.status_code == 422

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_set_privacy_preferences_invalid_privacy_notice_history_id(
        self,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        request_body,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["preferences"][0]["privacy_notice_history_id"] = "bad_id"

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert (
            response.status_code == 400
        ), "Gets picked up by the duplicate privacy notice check"

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_set_duplicate_preferences_for_the_same_notice_in_one_request(
        self,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
        request_body,
        privacy_notice,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["preferences"].append(
            {
                "privacy_notice_history_id": privacy_notice.histories[0].id,
                "preference": "opt_in",
            }
        )

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert (
            response.status_code == 400
        ), "Gets picked up by the duplicate privacy notice check"

    @pytest.mark.usefixtures(
        "subject_identity_verification_required", "automatically_approved"
    )
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    @mock.patch(
        "fides.api.ops.service.privacy_request.request_runner_service.run_privacy_request.delay"
    )
    def test_set_privacy_preferences(
        self,
        mock_run_privacy_request: MagicMock,
        mock_verify_identity: MagicMock,
        provided_identity_and_consent_request,
        db,
        api_client,
        verification_code,
        consent_policy,
        request_body,
        privacy_notice,
        privacy_notice_us_ca_provide,
        system,
    ):
        provided_identity, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["preferences"].append(
            {
                "privacy_notice_history_id": privacy_notice_us_ca_provide.histories[
                    0
                ].id,
                "preference": "opt_in",
            }
        )

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

        response_json = response.json()

        first_privacy_preference_history_created = (
            db.query(PrivacyPreferenceHistory)
            .filter(
                PrivacyPreferenceHistory.id
                == response_json[0]["privacy_preference_history_id"]
            )
            .first()
        )
        assert response_json[0]["preference"] == "opt_out"

        assert (
            response_json[0]["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(privacy_notice.histories[0]).dict()
        )

        second_privacy_preference_history_created = (
            db.query(PrivacyPreferenceHistory)
            .filter(
                PrivacyPreferenceHistory.id
                == response_json[1]["privacy_preference_history_id"]
            )
            .first()
        )
        assert response_json[1]["preference"] == "opt_in"
        assert (
            response_json[1]["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(
                privacy_notice_us_ca_provide.histories[0]
            ).dict()
        )
        assert verification_code in mock_verify_identity.call_args_list[0].args

        db.refresh(first_privacy_preference_history_created)
        db.refresh(second_privacy_preference_history_created)

        assert first_privacy_preference_history_created.privacy_request_id is not None
        assert second_privacy_preference_history_created.privacy_request_id is not None

        identity = (
            first_privacy_preference_history_created.privacy_request.get_persisted_identity()
        )
        assert identity.email == "test@email.com", (
            "Identity pulled from Privacy Request Provided Identity and used to "
            "create a Privacy Request provided identity "
        )
        assert identity.phone_number is None
        assert identity.ga_client_id == "test", (
            "Browser identity pulled from Privacy Request Provided Identity and persisted "
            "to a Privacy Request provided identity"
        )

        privacy_request = first_privacy_preference_history_created.privacy_request
        assert privacy_request.status == PrivacyRequestStatus.pending
        assert privacy_request.privacy_preferences == [
            first_privacy_preference_history_created,
            second_privacy_preference_history_created,
        ], "Same privacy request created to propagate both preferences"

        db.refresh(consent_request)
        assert (
            consent_request.privacy_request_id == privacy_request.id
        ), "Privacy request id also saved on Consent request for record keeping"
        assert mock_run_privacy_request.called

        current_privacy_preference_one = (
            first_privacy_preference_history_created.current_privacy_preference
        )
        current_privacy_preference_two = (
            second_privacy_preference_history_created.current_privacy_preference
        )
        assert (
            current_privacy_preference_one.preference == UserConsentPreference.opt_out
        ), "History preferences saved to latest preferences"
        assert (
            current_privacy_preference_two.preference == UserConsentPreference.opt_in
        ), "History preferences saved to latest preferences"

        first_privacy_preference_history_created.delete(db)
        second_privacy_preference_history_created.delete(db)

    @pytest.mark.usefixtures(
        "subject_identity_verification_required", "automatically_approved"
    )
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    @mock.patch(
        "fides.api.ops.service.privacy_request.request_runner_service.run_privacy_request.delay"
    )
    def test_set_privacy_preferences_bad_policy_key(
        self,
        mock_run_privacy_request: MagicMock,
        mock_verify_identity: MagicMock,
        provided_identity_and_consent_request,
        db,
        api_client,
        verification_code,
        request_body,
        privacy_notice,
    ):
        """Even though privacy request creation fails, privacy preferences are still saved"""
        provided_identity, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        request_body["policy_key"] = "bad_policy_key"

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"] == "Policy with key bad_policy_key does not exist"
        )

        privacy_preference_history_created = (
            db.query(PrivacyPreferenceHistory)
            .filter(
                PrivacyPreferenceHistory.privacy_notice_history_id
                == privacy_notice.privacy_notice_history_id
            )
            .first()
        )
        assert (
            privacy_preference_history_created.preference
            == UserConsentPreference.opt_out
        )

        assert verification_code in mock_verify_identity.call_args_list[0].args
        assert privacy_preference_history_created.privacy_request_id is None
        db.refresh(consent_request)
        assert consent_request.privacy_request_id is None
        assert not mock_run_privacy_request.called

        current_privacy_preference_one = (
            privacy_preference_history_created.current_privacy_preference
        )

        assert (
            current_privacy_preference_one.preference == UserConsentPreference.opt_out
        ), "Historical preferences upserted to latest consent preferences"

        privacy_preference_history_created.delete(db)

    @pytest.mark.usefixtures("automatically_approved")
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    @mock.patch(
        "fides.api.ops.service.privacy_request.request_runner_service.run_privacy_request.delay"
    )
    def test_set_privacy_preferences_without_verification_required(
        self,
        run_privacy_request_mock,
        mock_verify_identity: MagicMock,
        provided_identity_and_consent_request,
        db,
        api_client,
        privacy_notice,
        request_body,
        verification_code,
        system,
    ):
        provided_identity, consent_request = provided_identity_and_consent_request

        response = api_client.patch(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_WITH_ID.format(consent_request_id=consent_request.id)}",
            json=request_body,
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

        response_json = response.json()[0]
        created_privacy_preference_history_id = response_json[
            "privacy_preference_history_id"
        ]
        privacy_preference_history = (
            db.query(PrivacyPreferenceHistory)
            .filter(
                PrivacyPreferenceHistory.id == created_privacy_preference_history_id
            )
            .first()
        )
        assert response_json["preference"] == "opt_out"

        assert (
            response_json["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(privacy_notice.histories[0]).dict()
        )

        db.refresh(consent_request)
        assert consent_request.privacy_request_id

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        response_json = response.json()["items"][0]
        assert response_json["id"] is not None
        assert response_json["preference"] == "opt_out"
        assert (
            response_json["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(privacy_notice.histories[0]).dict()
        )

        privacy_preference_history.delete(db=db)
        assert not mock_verify_identity.called
        assert run_privacy_request_mock.called


class TestPrivacyPreferenceVerify:
    @pytest.fixture(scope="function")
    def verification_code(self) -> str:
        return "abcd"

    def test_consent_verify_no_consent_request_id(
        self,
        api_client,
    ):
        data = {"code": "12345"}

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id='non_existent_consent_id')}",
            json=data,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_consent_verify_no_consent_code(
        self, provided_identity_and_consent_request, api_client
    ):
        data = {"code": "12345"}

        _, consent_request = provided_identity_and_consent_request
        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json=data,
        )
        assert response.status_code == 400
        assert "code expired" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_consent_verify_invalid_code(
        self, provided_identity_and_consent_request, api_client
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code("abcd")

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": "1234"},
        )
        assert response.status_code == 403
        assert "Incorrect identification" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    def test_consent_verify_no_email_provided(
        self,
        mock_verify_identity: MagicMock,
        db,
        api_client,
        verification_code,
    ):
        provided_identity_data = {
            "privacy_request_id": None,
            "field_name": "email",
            "hashed_value": None,
            "encrypted_value": None,
        }
        provided_identity = ProvidedIdentity.create(db, data=provided_identity_data)

        consent_request_data = {
            "provided_identity_id": provided_identity.id,
        }
        consent_request = ConsentRequest.create(db, data=consent_request_data)
        consent_request.cache_identity_verification_code(verification_code)

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )

        assert response.status_code == 404
        assert verification_code in mock_verify_identity.call_args_list[0].args
        assert "missing" in response.json()["detail"]

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    @patch("fides.api.ops.models.privacy_request.ConsentRequest.verify_identity")
    def test_consent_verify_no_privacy_preferences_present(
        self,
        mock_verify_identity: MagicMock,
        provided_identity_and_consent_request,
        api_client,
        verification_code,
    ):
        _, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )
        assert response.status_code == 200
        assert verification_code in mock_verify_identity.call_args_list[0].args
        assert response.json() == {"items": [], "total": 0, "page": 1, "size": 50}

    @pytest.mark.usefixtures(
        "subject_identity_verification_required",
    )
    def test_consent_verify_consent_preferences(
        self,
        provided_identity_and_consent_request,
        db,
        api_client,
        verification_code,
        privacy_preference_history,
    ):
        provided_identity, consent_request = provided_identity_and_consent_request
        consent_request.cache_identity_verification_code(verification_code)

        response = api_client.post(
            f"{V1_URL_PREFIX}{CONSENT_REQUEST_PRIVACY_PREFERENCES_VERIFY.format(consent_request_id=consent_request.id)}",
            json={"code": verification_code},
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

        # Getting current preferences returns the latest CurrentPrivacyPreferences, not the PrivacyPreferenceHistory records
        current_preference_record = (
            privacy_preference_history.current_privacy_preference
        )
        data = response.json()["items"][0]
        assert data["id"] == current_preference_record.id
        assert (
            data["preference"]
            == "opt_out"
            == privacy_preference_history.preference.value
        )
        assert (
            data["privacy_notice_history"]
            == PrivacyNoticeHistorySchema.from_orm(
                privacy_preference_history.privacy_notice_history
            ).dict()
        )
        db.refresh(consent_request)
        assert consent_request.identity_verified_at is not None


class TestHistoricalPreferences:
    @pytest.fixture(scope="function")
    def url(self) -> str:
        return V1_URL_PREFIX + HISTORICAL_PRIVACY_PREFERENCES

    def test_get_historical_preferences_not_authenticated(
        self, api_client: TestClient, url
    ) -> None:
        response = api_client.get(url, headers={})
        assert 401 == response.status_code

    def test_get_historical_preferences_incorrect_scope(
        self, api_client: TestClient, url, generate_auth_header
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONSENT_READ])
        response = api_client.get(url, headers=auth_header)
        assert 403 == response.status_code

    @pytest.mark.parametrize(
        "role,expected_status",
        [
            ("owner", HTTP_200_OK),
            ("contributor", HTTP_200_OK),
            ("viewer_and_approver", HTTP_403_FORBIDDEN),
            ("viewer", HTTP_403_FORBIDDEN),
            ("approver", HTTP_403_FORBIDDEN),
        ],
    )
    def test_get_historical_preferences_roles(
        self, role, expected_status, api_client: TestClient, url, generate_role_header
    ) -> None:
        auth_header = generate_role_header(roles=[role])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == expected_status

    def test_get_historical_preferences(
        self,
        db,
        api_client: TestClient,
        url,
        user,
        generate_auth_header,
        privacy_preference_history,
        privacy_request_with_consent_policy,
        system,
    ) -> None:
        privacy_preference_history.privacy_request_id = (
            privacy_request_with_consent_policy.id
        )
        privacy_preference_history.relevant_systems = privacy_preference_history.privacy_notice_history.calculate_relevant_systems(
            db
        )
        privacy_preference_history.save(db)

        privacy_preference_history.update_secondary_user_ids(
            db, {"ljt_readerID": "preference_history_test"}
        )
        privacy_preference_history.cache_system_status(
            db, system=system.fides_key, status=ExecutionLogStatus.complete
        )

        privacy_request_with_consent_policy.reviewed_by = user.id
        privacy_request_with_consent_policy.save(db)

        auth_header = generate_auth_header(scopes=[PRIVACY_PREFERENCE_HISTORY_READ])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["total"] == 1
        assert response.json()["page"] == 1
        assert response.json()["size"] == 50

        response_body = response.json()["items"][0]

        assert response_body["id"] == privacy_preference_history.id
        assert (
            response_body["privacy_request_id"]
            == privacy_request_with_consent_policy.id
        )
        assert response_body["user_id"] == "test@email.com"
        assert response_body["secondary_user_ids"] == {
            "ljt_readerID": "preference_history_test"
        }
        assert response_body["request_timestamp"] is not None
        assert response_body["request_origin"] == "privacy_center"
        assert response_body["request_status"] == "in_processing"
        assert response_body["request_type"] == "consent"
        assert response_body["approver_id"] == "test_fidesops_user"
        assert (
            response_body["privacy_notice_history_id"]
            == privacy_preference_history.privacy_notice_history_id
        )
        assert response_body["privacy_notice_history_id"] is not None
        assert response_body["preference"] == "opt_out"
        assert response_body["user_geography"] == "us_ca"
        assert response_body["relevant_systems"] == [system.fides_key]
        assert response_body["affected_system_status"] == {system.fides_key: "complete"}
        assert response_body["url_recorded"] == "example.com/privacy_center"
        assert (
            response_body["user_agent"]
            == "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_2) AppleWebKit/324.42 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/425.24"
        )

    def test_get_historical_preferences_ordering(
        self,
        api_client: TestClient,
        url,
        generate_auth_header,
        privacy_preference_history,
        privacy_preference_history_us_ca_provide,
        privacy_preference_history_eu_fr_provide_service_frontend_only,
    ) -> None:
        auth_header = generate_auth_header(scopes=[PRIVACY_PREFERENCE_HISTORY_READ])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 3
        assert response.json()["total"] == 3
        assert response.json()["page"] == 1
        assert response.json()["size"] == 50

        response_body = response.json()["items"]

        # Records ordered most recently created first
        assert (
            response_body[0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.id
        )
        assert response_body[1]["id"] == privacy_preference_history_us_ca_provide.id
        assert response_body[2]["id"] == privacy_preference_history.id

    def test_get_historical_preferences_date_filtering(
        self,
        api_client: TestClient,
        url,
        generate_auth_header,
        privacy_preference_history,
        privacy_preference_history_us_ca_provide,
        privacy_preference_history_eu_fr_provide_service_frontend_only,
    ) -> None:
        auth_header = generate_auth_header(scopes=[PRIVACY_PREFERENCE_HISTORY_READ])

        # Filter for everything created before the first preference
        response = api_client.get(
            url
            + f"?request_timestamp_lt={privacy_preference_history.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

        # Filter for everything created before the last preference plus an hour
        response = api_client.get(
            url
            + f"?request_timestamp_lt={(privacy_preference_history_eu_fr_provide_service_frontend_only.created_at + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 3

        assert (
            response.json()["items"][0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.id
        )
        assert (
            response.json()["items"][1]["id"]
            == privacy_preference_history_us_ca_provide.id
        )
        assert response.json()["items"][2]["id"] == privacy_preference_history.id

        # Filter for everything created after the first preference
        response = api_client.get(
            url
            + f"?request_timestamp_gt={privacy_preference_history.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert (
            response.json()["items"][0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.id
        )
        assert (
            response.json()["items"][1]["id"]
            == privacy_preference_history_us_ca_provide.id
        )

        # Invalid filter
        response = api_client.get(
            url
            + f"?request_timestamp_lt={privacy_preference_history.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}&request_timestamp_gt={privacy_preference_history_eu_fr_provide_service_frontend_only.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 400
        assert "Value specified for request_timestamp_lt" in response.json()["detail"]
        assert "must be after request_timestamp_gt" in response.json()["detail"]


class TestCurrentPrivacyPreferences:
    @pytest.fixture(scope="function")
    def url(self) -> str:
        return V1_URL_PREFIX + CURRENT_PRIVACY_PREFERENCES

    def test_get_current_preferences_not_authenticated(
        self, api_client: TestClient, url
    ) -> None:
        response = api_client.get(url, headers={})
        assert 401 == response.status_code

    def test_get_current_preferences_incorrect_scope(
        self, api_client: TestClient, url, generate_auth_header
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONSENT_READ])
        response = api_client.get(url, headers=auth_header)
        assert 403 == response.status_code

    @pytest.mark.parametrize(
        "role,expected_status",
        [
            ("owner", HTTP_200_OK),
            ("contributor", HTTP_200_OK),
            ("viewer_and_approver", HTTP_403_FORBIDDEN),
            ("viewer", HTTP_403_FORBIDDEN),
            ("approver", HTTP_403_FORBIDDEN),
        ],
    )
    def test_get_current_preferences_roles(
        self, role, expected_status, api_client: TestClient, url, generate_role_header
    ) -> None:
        auth_header = generate_role_header(roles=[role])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == expected_status

    def test_get_current_preferences(
        self,
        api_client: TestClient,
        url,
        generate_auth_header,
        privacy_preference_history,
    ) -> None:
        current_preference = privacy_preference_history.current_privacy_preference

        auth_header = generate_auth_header(scopes=[CURRENT_PRIVACY_PREFERENCE_READ])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
        assert response.json()["total"] == 1
        assert response.json()["page"] == 1
        assert response.json()["size"] == 50

        response_body = response.json()["items"][0]

        assert response_body["id"] == current_preference.id
        assert response_body["preference"] == current_preference.preference.value
        assert (
            response_body["privacy_notice_history_id"]
            == current_preference.privacy_notice_history.id
        )
        assert (
            response_body["provided_identity_id"]
            == privacy_preference_history.provided_identity.id
        )
        assert response_body["created_at"] is not None

    def test_get_current_preference_ordering(
        self,
        api_client: TestClient,
        url,
        generate_auth_header,
        privacy_preference_history,
        privacy_preference_history_us_ca_provide,
        privacy_preference_history_eu_fr_provide_service_frontend_only,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CURRENT_PRIVACY_PREFERENCE_READ])
        response = api_client.get(url, headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 3
        assert response.json()["total"] == 3
        assert response.json()["page"] == 1
        assert response.json()["size"] == 50

        response_body = response.json()["items"]

        # Records ordered most recently created first
        assert (
            response_body[0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.current_privacy_preference.id
        )
        assert (
            response_body[1]["id"]
            == privacy_preference_history_us_ca_provide.current_privacy_preference.id
        )
        assert (
            response_body[2]["id"]
            == privacy_preference_history.current_privacy_preference.id
        )

    def test_get_current_preferences_date_filtering(
        self,
        api_client: TestClient,
        url,
        generate_auth_header,
        privacy_preference_history,
        privacy_preference_history_us_ca_provide,
        privacy_preference_history_eu_fr_provide_service_frontend_only,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CURRENT_PRIVACY_PREFERENCE_READ])

        # Filter for everything updated before the first preference
        response = api_client.get(
            url
            + f"?updated_lt={privacy_preference_history.current_privacy_preference.updated_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

        # Filter for everything updated before the last preference plus an hour
        response = api_client.get(
            url
            + f"?updated_lt={(privacy_preference_history_eu_fr_provide_service_frontend_only.current_privacy_preference.updated_at + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 3

        assert (
            response.json()["items"][0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.current_privacy_preference.id
        )
        assert (
            response.json()["items"][1]["id"]
            == privacy_preference_history_us_ca_provide.current_privacy_preference.id
        )
        assert (
            response.json()["items"][2]["id"]
            == privacy_preference_history.current_privacy_preference.id
        )

        # Filter for everything updated after the first preference
        response = api_client.get(
            url
            + f"?updated_gt={privacy_preference_history.current_privacy_preference.updated_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert (
            response.json()["items"][0]["id"]
            == privacy_preference_history_eu_fr_provide_service_frontend_only.current_privacy_preference.id
        )
        assert (
            response.json()["items"][1]["id"]
            == privacy_preference_history_us_ca_provide.current_privacy_preference.id
        )

        # Invalid filter
        response = api_client.get(
            url
            + f"?updated_lt={privacy_preference_history.current_privacy_preference.updated_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}&updated_gt={privacy_preference_history_eu_fr_provide_service_frontend_only.current_privacy_preference.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            headers=auth_header,
        )
        assert response.status_code == 400
        assert "Value specified for updated_lt" in response.json()["detail"]
        assert "must be after updated_gt" in response.json()["detail"]