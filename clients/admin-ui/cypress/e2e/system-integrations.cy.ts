import { stubPlus, stubSystemCrud } from "cypress/support/stubs";

import { SYSTEM_ROUTE } from "~/features/common/nav/v2/routes";

describe("System integrations", () => {
  beforeEach(() => {
    cy.login();
    cy.intercept("GET", "/api/v1/system", {
      fixture: "systems/systems.json",
    }).as("getSystems");
    cy.intercept("GET", "/api/v1/connection_type*", {
      fixture: "connectors/connection_types.json",
    }).as("getConnectionTypes");
    stubPlus(false);
    stubSystemCrud();
    cy.visit(SYSTEM_ROUTE);
  });

  it("should render the integration configuration panel when navigating to integrations tab", () => {
    cy.getByTestId("system-fidesctl_system").within(() => {
      cy.getByTestId("more-btn").click();
      cy.getByTestId("edit-btn").click();
    });
    cy.getByTestId("tab-Integrations").click();
    cy.getByTestId("tab-panel-Integrations").should("exist");
  });

  describe("Integration search", () => {
    beforeEach(() => {
      cy.getByTestId("system-fidesctl_system").within(() => {
        cy.getByTestId("more-btn").click();
        cy.getByTestId("edit-btn").click();
      });
      cy.getByTestId("tab-Integrations").click();
      cy.getByTestId("select-dropdown-btn").click();
    });

    it("should display Shopify when searching with upper case letters", () => {
      cy.getByTestId("input-search-integrations").type("Sho");
      cy.getByTestId("select-dropdown-list")
        .find('[role="menuitem"] p')
        .should("contain.text", "Shopify");
    });

    it("should display Shopify when searching with lower case letters", () => {
      cy.getByTestId("input-search-integrations").type("sho");
      cy.getByTestId("select-dropdown-list")
        .find('[role="menuitem"] p')
        .should("contain.text", "Shopify");
    });
  });
});
