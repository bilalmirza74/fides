import { Box, Breadcrumb, BreadcrumbItem, Heading, Text } from "@fidesui/react";
import NextLink from "next/link";
import React from "react";

import Layout from "~/features/common/Layout";
import { CONFIGURE_CONSENT_ROUTE } from "~/features/common/nav/v2/routes";
import ConfigureConsent from "~/features/configure-consent/ConfigureConsent";

const ConfigureConsentPage = () => (
  <Layout title="Configure consent">
    <Box mb={4}>
      <Heading fontSize="2xl" fontWeight="semibold" mb={2} data-testid="header">
        Configure consent
      </Heading>
      <Box>
        <Breadcrumb
          fontWeight="medium"
          fontSize="sm"
          color="gray.600"
          data-testid="breadcrumbs"
        >
          <BreadcrumbItem>
            <NextLink href={CONFIGURE_CONSENT_ROUTE}>Consent</NextLink>
          </BreadcrumbItem>
          <BreadcrumbItem color="complimentary.500">
            <NextLink href="#">Configure consent</NextLink>
          </BreadcrumbItem>
        </Breadcrumb>
      </Box>
    </Box>
    <Text fontSize="sm" mb={8} width={{ base: "100%", lg: "50%" }}>
      Your current cookies and tracking information.
    </Text>
    <Box data-testid="configure-consent-page">
      <ConfigureConsent />
    </Box>
  </Layout>
);

export default ConfigureConsentPage;
