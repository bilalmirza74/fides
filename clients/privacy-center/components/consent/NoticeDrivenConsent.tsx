import { Divider, Stack, useToast } from "@fidesui/react";
import React, { useEffect, useMemo, useState } from "react";
import {
  ConsentContext,
  CookieKeyConsent,
  getConsentContext,
  getOrMakeFidesCookie,
  removeCookiesFromBrowser,
  saveFidesCookie,
  transformUserPreferenceToBoolean,
  getGpcStatusFromNotice,
  PrivacyNotice,
} from "fides-js";
import { useAppSelector } from "~/app/hooks";
import {
  selectCurrentConsentPreferences,
  selectUserRegion,
  selectPrivacyExperience,
  useUpdatePrivacyPreferencesMutation,
  useUpdateNoticesServedMutation,
} from "~/features/consent/consent.slice";

import {
  ConsentMechanism,
  ConsentMethod,
  ConsentOptionCreate,
  PrivacyNoticeResponseWithUserPreferences,
  PrivacyPreferencesRequest,
  ServingComponent,
  UserConsentPreference,
} from "~/types/api";
import { useRouter } from "next/router";
import { inspectForBrowserIdentities } from "~/common/browser-identities";
import { NoticeHistoryIdToPreference } from "~/features/consent/types";
import { ErrorToastOptions, SuccessToastOptions } from "~/common/toast-options";
import { useLocalStorage } from "~/common/hooks";
import ConsentItem from "./ConsentItem";
import SaveCancel from "./SaveCancel";
import PrivacyPolicyLink from "./PrivacyPolicyLink";

// DEFER(fides#3505): Use the fides-js version of this function
const resolveConsentValue = (
  notice: PrivacyNoticeResponseWithUserPreferences,
  context: ConsentContext
) => {
  const gpcEnabled =
    !!notice.has_gpc_flag && context.globalPrivacyControl === true;
  if (gpcEnabled) {
    return UserConsentPreference.OPT_OUT;
  }
  return notice.default_preference;
};

const NoticeDrivenConsent = () => {
  const router = useRouter();
  const toast = useToast();
  const [consentRequestId] = useLocalStorage("consentRequestId", "");
  const [verificationCode] = useLocalStorage("verificationCode", "");
  const consentContext = useMemo(() => getConsentContext(), []);
  const experience = useAppSelector(selectPrivacyExperience);
  const serverPreferences = useAppSelector(selectCurrentConsentPreferences);
  const cookie = getOrMakeFidesCookie();
  const { fides_user_device_id: fidesUserDeviceId } = cookie.identity;
  const [updatePrivacyPreferencesMutationTrigger] =
    useUpdatePrivacyPreferencesMutation();
  const region = useAppSelector(selectUserRegion);

  const browserIdentities = useMemo(() => {
    const identities = inspectForBrowserIdentities();
    const deviceIdentity = { fides_user_device_id: fidesUserDeviceId };
    return identities ? { ...deviceIdentity, ...identities } : deviceIdentity;
  }, [fidesUserDeviceId]);

  const initialDraftPreferences = useMemo(() => {
    const newPreferences = { ...serverPreferences };
    Object.entries(serverPreferences).forEach(([key, value]) => {
      if (!value) {
        const notices = experience?.privacy_notices ?? [];
        const notice = notices.filter(
          (n) => n.privacy_notice_history_id === key
        )[0];
        const defaultValue = notice
          ? resolveConsentValue(notice, consentContext)
          : UserConsentPreference.OPT_OUT;
        newPreferences[key] = defaultValue;
      }
    });
    return newPreferences;
  }, [serverPreferences, experience, consentContext]);

  const [draftPreferences, setDraftPreferences] =
    useState<NoticeHistoryIdToPreference>(initialDraftPreferences);

  useEffect(() => {
    setDraftPreferences(initialDraftPreferences);
  }, [initialDraftPreferences]);

  const [updateNoticesServedMutationTrigger, { data: servedNotices }] =
    useUpdateNoticesServedMutation();

  useEffect(() => {
    if (experience && experience.privacy_notices) {
      updateNoticesServedMutationTrigger({
        id: consentRequestId,
        body: {
          browser_identity: browserIdentities,
          privacy_experience_id: experience?.id,
          privacy_notice_history_ids: experience.privacy_notices.map(
            (p) => p.privacy_notice_history_id
          ),
          serving_component: ServingComponent.PRIVACY_CENTER,
        },
      });
    }
  }, [
    consentRequestId,
    updateNoticesServedMutationTrigger,
    experience,
    browserIdentities,
  ]);

  const items = useMemo(() => {
    if (!experience) {
      return [];
    }
    const { privacy_notices: notices } = experience;
    if (!notices || notices.length === 0) {
      return [];
    }

    return notices.map((notice) => {
      const preference = draftPreferences[notice.privacy_notice_history_id];
      const value = transformUserPreferenceToBoolean(preference);
      const gpcStatus = getGpcStatusFromNotice({
        value,
        notice: notice as PrivacyNotice,
        consentContext,
      });

      return {
        name: notice.name || "",
        description: notice.description || "",
        id: notice.id,
        historyId: notice.privacy_notice_history_id,
        highlight: false,
        url: undefined,
        value,
        gpcStatus,
        disabled: notice.consent_mechanism === ConsentMechanism.NOTICE_ONLY,
      };
    });
  }, [consentContext, experience, draftPreferences]);

  const handleCancel = () => {
    router.push("/");
  };

  /**
   * When saving, we need to:
   * 1. Send PATCH to Fides backend
   * 2. Save to cookie and window object
   * 3. Delete any cookies that have been opted out of
   */
  const handleSave = async () => {
    const notices = experience?.privacy_notices ?? [];

    // Reconnect preferences to notices
    const noticePreferences = Object.entries(draftPreferences).map(
      ([historyKey, preference]) => {
        const notice = notices.find(
          (n) => n.privacy_notice_history_id === historyKey
        );
        const servedNotice = servedNotices?.find(
          (sn) => sn.privacy_notice_history?.id === historyKey
        );
        return { historyKey, preference, notice, servedNotice };
      }
    );

    const preferences: ConsentOptionCreate[] = noticePreferences.map(
      ({ historyKey, preference, notice, servedNotice }) => {
        if (notice?.consent_mechanism === ConsentMechanism.NOTICE_ONLY) {
          return {
            privacy_notice_history_id: historyKey,
            preference: UserConsentPreference.ACKNOWLEDGE,
            served_notice_history_id: servedNotice?.served_notice_history_id,
          };
        }
        return {
          privacy_notice_history_id: historyKey,
          preference: preference ?? UserConsentPreference.OPT_OUT,
          served_notice_history_id: servedNotice?.served_notice_history_id,
        };
      }
    );

    const payload: PrivacyPreferencesRequest = {
      browser_identity: browserIdentities,
      preferences,
      user_geography: region,
      privacy_experience_id: experience?.id,
      method: ConsentMethod.BUTTON,
      code: verificationCode,
    };

    // 1. Send PATCH to Fides backend
    const result = await updatePrivacyPreferencesMutationTrigger({
      id: consentRequestId,
      body: payload,
    });
    const isError = "error" in result;
    if (isError || !result.data.preferences) {
      let description = "No preferences returned";
      if (isError) {
        description = typeof result.error === "string" ? result.error : "";
      }
      toast({
        title: "An error occurred while saving user consent preferences",
        description,
        ...ErrorToastOptions,
      });
      return;
    }

    // 2. Save the cookie and window obj on success
    const noticeKeyMap = new Map<string, boolean>(
      result.data.preferences.map((preference) => [
        preference.privacy_notice_history?.notice_key || "",
        transformUserPreferenceToBoolean(preference.preference),
      ])
    );
    const consentCookieKey: CookieKeyConsent = Object.fromEntries(noticeKeyMap);
    window.Fides.consent = consentCookieKey;
    const updatedCookie = { ...cookie, consent: consentCookieKey };
    saveFidesCookie(updatedCookie);
    toast({
      title: "Your consent preferences have been saved",
      ...SuccessToastOptions,
    });

    // 3. Delete any cookies that have been opted out of
    noticePreferences.forEach((noticePreference) => {
      if (
        noticePreference.preference === UserConsentPreference.OPT_OUT &&
        noticePreference.notice
      ) {
        removeCookiesFromBrowser(noticePreference.notice.cookies);
      }
    });
    router.push("/");
  };

  return (
    <Stack spacing={6} paddingX={12}>
      {items.map((item, index) => {
        const { id, highlight, url, name, description, historyId, disabled } =
          item;
        const handleChange = (value: boolean) => {
          const pref = value
            ? UserConsentPreference.OPT_IN
            : UserConsentPreference.OPT_OUT;
          setDraftPreferences({
            ...draftPreferences,
            ...{ [historyId]: pref },
          });
        };
        return (
          <React.Fragment key={id}>
            {index > 0 ? <Divider /> : null}
            <ConsentItem
              id={id}
              name={name}
              description={description}
              highlight={highlight}
              url={url}
              value={item.value}
              gpcStatus={item.gpcStatus}
              onChange={handleChange}
              disabled={disabled}
            />
          </React.Fragment>
        );
      })}
      <SaveCancel
        onSave={handleSave}
        onCancel={handleCancel}
        saveLabel={experience?.experience_config?.save_button_label}
        justifyContent="center"
      />
      <PrivacyPolicyLink alignSelf="center" experience={experience} />
    </Stack>
  );
};

export default NoticeDrivenConsent;
