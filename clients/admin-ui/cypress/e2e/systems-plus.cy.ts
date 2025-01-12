import {
  stubPlus,
  stubSystemCrud,
  stubSystemVendors,
  stubTaxonomyEntities,
  stubVendorList,
} from "cypress/support/stubs";

import {
  ADD_SYSTEMS_MANUAL_ROUTE,
  ADD_SYSTEMS_MULTIPLE_ROUTE,
  ADD_SYSTEMS_ROUTE,
  DATAMAP_ROUTE,
  SYSTEM_ROUTE,
} from "~/features/common/nav/v2/routes";

describe("System management with Plus features", () => {
  beforeEach(() => {
    cy.login();
    stubSystemCrud();
    stubTaxonomyEntities();
    stubPlus(true);
    cy.intercept("GET", "/api/v1/system", {
      fixture: "systems/systems.json",
    }).as("getSystems");
  });

  describe("vendor list", () => {
    beforeEach(() => {
      stubVendorList();
      cy.visit(`${SYSTEM_ROUTE}/configure/demo_analytics_system`);
      cy.wait("@getDictionaryEntries");
    });

    it("can display the vendor list dropdown", () => {
      cy.getSelectValueContainer("input-vendor_id");
    });

    it("contains type ahead dictionary entries", () => {
      cy.getSelectValueContainer("input-vendor_id").type("A");
      cy.get("#react-select-select-vendor_id-option-0").contains("Aniview LTD");
      cy.get("#react-select-select-vendor_id-option-1").contains(
        "Anzu Virtual Reality LTD"
      );
    });

    it("can switch entries", () => {
      cy.getSelectValueContainer("input-vendor_id").type("Aniview{enter}");
      cy.getSelectValueContainer("input-vendor_id").contains("Aniview LTD");

      cy.getSelectValueContainer("input-vendor_id").type("Anzu{enter}");
      cy.getSelectValueContainer("input-vendor_id").contains(
        "Anzu Virtual Reality LTD"
      );
    });

    // some DictSuggestionTextInputs don't get populated right, causing
    // the form to be mistakenly marked as dirty and the "unsaved changes"
    // modal to pop up incorrectly when switching tabs
    it("can switch between tabs after populating from dictionary", () => {
      cy.wait("@getSystems");
      cy.getSelectValueContainer("input-vendor_id").type("Anzu{enter}");
      cy.getByTestId("dict-suggestions-btn").click();
      cy.getByTestId("toggle-dict-suggestions").click();
      // the form fetches the system again after saving, so update the intercept with dictionary values
      cy.fixture("systems/dictionary-system.json").then((dictSystem) => {
        cy.fixture("systems/system.json").then((origSystem) => {
          cy.intercept(
            { method: "GET", url: "/api/v1/system/demo_analytics_system" },
            {
              body: {
                ...origSystem,
                ...dictSystem,
                fides_key: origSystem.fides_key,
                customFieldValues: undefined,
                data_protection_impact_assessment: undefined,
              },
            }
          ).as("getDictSystem");
        });
      });
      cy.intercept({ method: "PUT", url: "/api/v1/system*" }).as(
        "putDictSystem"
      );
      cy.getByTestId("save-btn").click();
      cy.wait("@putDictSystem");
      cy.wait("@getDictSystem");
      cy.getByTestId("input-dpo").should("have.value", "DPO@anzu.io");
      cy.getByTestId("tab-Data uses").click();
      cy.getByTestId("tab-System information").click();
      cy.getByTestId("tab-Data uses").click();
      cy.getByTestId("confirmation-modal").should("not.exist");
    });
  });

  describe("custom metadata", () => {
    beforeEach(() => {
      cy.intercept(
        {
          method: "GET",
          pathname: "/api/v1/plus/custom-metadata/allow-list",
          query: {
            show_values: "true",
          },
        },
        {
          fixture: "taxonomy/custom-metadata/allow-list/list.json",
        }
      ).as("getAllowLists");
      cy.intercept(
        "GET",
        `/api/v1/plus/custom-metadata/custom-field-definition/resource-type/*`,

        {
          fixture: "taxonomy/custom-metadata/custom-field-definition/list.json",
        }
      ).as("getCustomFieldDefinitions");
      cy.intercept(
        "GET",
        `/api/v1/plus/custom-metadata/custom-field/resource/*`,
        {
          fixture: "taxonomy/custom-metadata/custom-field/list.json",
        }
      ).as("getCustomFields");
      cy.intercept("POST", `/api/v1/plus/custom-metadata/custom-field/bulk`, {
        body: {},
      }).as("bulkUpdateCustomField");
    });

    it("can populate initial custom metadata", () => {
      cy.visit(`${SYSTEM_ROUTE}/configure/demo_analytics_system`);

      // Should not be able to save while form is untouched
      cy.getByTestId("save-btn").should("be.disabled");
      const testId =
        "input-customFieldValues.id-custom-field-definition-pokemon-party";
      cy.getByTestId(testId).contains("Charmander");
      cy.getByTestId(testId).contains("Eevee");
      cy.getByTestId(testId).contains("Snorlax");
      cy.getByTestId(testId).type("Bulbasaur{enter}");

      // Should be able to save now that form is dirty
      cy.getByTestId("save-btn").should("be.enabled");
      cy.getByTestId("save-btn").click();

      cy.wait("@putSystem");

      const expectedValues = [
        {
          custom_field_definition_id:
            "id-custom-field-definition-pokemon-party",
          id: "id-custom-field-pokemon-party",
          resource_id: "demo_analytics_system",
          value: ["Charmander", "Eevee", "Snorlax", "Bulbasaur"],
        },
        {
          custom_field_definition_id:
            "id-custom-field-definition-starter-pokemon",
          id: "id-custom-field-starter-pokemon",
          resource_id: "demo_analytics_system",
          value: "Squirtle",
        },
      ];
      cy.wait("@bulkUpdateCustomField").then((interception) => {
        expect(interception.request.body.upsert).to.eql(expectedValues);
      });
    });
  });

  describe("bulk system/vendor adding page", () => {
    beforeEach(() => {
      stubPlus(true);
      stubSystemVendors();
    });

    it("page loads with table and rows", () => {
      cy.visit(ADD_SYSTEMS_MULTIPLE_ROUTE);

      cy.wait("@getSystemVendors");
      cy.getByTestId("fidesTable");
      cy.getByTestId("fidesTable-body")
        .find("tr")
        .should("have.length.greaterThan", 0);
    });

    it("upgrade modal doesn't pop up if compass is enabled", () => {
      cy.visit(ADD_SYSTEMS_ROUTE);
      cy.getByTestId("multiple-btn").click();
      cy.wait("@getSystemVendors");
      cy.getByTestId("fidesTable");
    });

    it("upgrade modal pops up if compass isn't enabled and redirects to manual add", () => {
      stubPlus(true, {
        core_fides_version: "2.2.0",
        fidesplus_server: "healthy",
        system_scanner: {
          enabled: true,
          cluster_health: null,
          cluster_error: null,
        },
        dictionary: {
          enabled: false,
          service_health: null,
          service_error: null,
        },
        fidesplus_version: "",
        fides_cloud: {
          enabled: false,
        },
      });
      cy.visit(ADD_SYSTEMS_ROUTE);
      cy.getByTestId("multiple-btn").click();
      cy.getByTestId("confirmation-modal");
      cy.getByTestId("cancel-btn").click();
      cy.url().should("include", ADD_SYSTEMS_MANUAL_ROUTE);
    });
    it("can add new systems and redirects to datamap", () => {
      cy.visit(ADD_SYSTEMS_MULTIPLE_ROUTE);
      cy.wait("@getSystemVendors");
      cy.getByTestId("row-0").within(() => {
        cy.get('[type="checkbox"]').check({ force: true });
      });
      cy.getByTestId("add-multiple-systems-btn").click();
      cy.getByTestId("confirmation-modal");
      cy.getByTestId("continue-btn").click();
      cy.url().should("include", DATAMAP_ROUTE);
    });
  });
});
