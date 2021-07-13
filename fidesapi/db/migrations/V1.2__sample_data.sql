
INSERT INTO ORGANIZATION(id, fides_key, version_stamp, description) values (2, 'Ethyca', 0, 'An account modelling Ethyca systems');

INSERT INTO REGISTRY(id, organization_id, fides_key, name, description) values(1,1,'test', 'Test registry', 'A registry for testing setups');
INSERT INTO REGISTRY(id, organization_id, fides_key, name, description) values(2,2,'es', 'Test ES registry', 'A test registry for modelling ES');

INSERT INTO SYSTEM_OBJECT(id, organization_id, fides_key, version_stamp, system_type, description,system_dependencies)
values (1,1,'test_system_1',0, 'SYSTEM','some test system','[]');
INSERT INTO PRIVACY_DECLARATION(system_id, `name`, data_categories, data_use, data_qualifier, data_subjects, dataset_references, raw_datasets)
values (1,'a','["telemetry_data"]', 'provide','aggregated_data','[]','[]', '[]');

INSERT INTO SYSTEM_OBJECT(id, organization_id, fides_key,version_stamp, system_type, description, system_dependencies) values (2,1,'test_system_2',0,'SYSTEM','some other test system','[]');
INSERT INTO PRIVACY_DECLARATION(system_id, `name`, data_categories, data_use, data_qualifier, data_subjects, dataset_references, raw_datasets)
values (2,'b','["end_user_identifiable_information", "personal_data_of_children"]', 'provide','identified_data','[]','[]', '[]');


INSERT INTO POLICY(id, organization_id, version_stamp, fides_key, description) values (1,1,0,'test policy 1', 'random policy');

INSERT INTO POLICY_RULE(id, policy_id, organization_id, fides_key, description, data_categories, data_subjects, data_uses, data_qualifier, action)
values (1,1,1,'test_policy_rule_1', 'random rule 1', '{"inclusion":"ANY","values":[ ]}','{"inclusion":"ANY","values":[ ]}',
        '{"inclusion":"NONE","values":[ "provide" ]}','unlinked_pseudonymized_data','REQUIRE');
INSERT INTO POLICY_RULE(id, policy_id, organization_id, fides_key, description, data_categories, data_subjects, data_uses, data_qualifier, action)
values (2,1,1,'test_policy_rule_2', 'random rule 2', '{"inclusion":"ANY","values":[ "customer_content_data" ]}','{"inclusion":"ANY","values":[ "customer" ]}',
        '{"inclusion":"ANY","values":[ "provide" ]}','identified_data','REJECT');

INSERT INTO USER(id, organization_id, user_name, first_name, last_name, role, api_key) values (1,1,'demo1','Iama','Sample','ADMIN','test_api_key');

INSERT INTO APPROVAL( organization_id, system_id, user_id, version_stamp, status, action) values (1,1,1,0,'PASS','test data');

INSERT INTO DATASET(id, organization_id, fides_key, version_stamp, name, location, dataset_type) values (1,1,'test_dataset',0, 'my test dataset', 'us-east-1', 'SQL');
INSERT INTO DATASET(id, organization_id, fides_key, version_stamp, name, location, dataset_type) values (2,1,'test_dataset2',0, 'my test dataset 2', 'us-east-1', 'SQL');
INSERT INTO DATASET_FIELD(dataset_id, name, `path`, data_categories, data_qualifier) values (1,'field1', null, '["credentials"]','aggregated_data');
INSERT INTO DATASET_FIELD(dataset_id, name, `path`, data_categories, data_qualifier) values (1,'field2', null, '[]','pseudonymized_data');
INSERT INTO DATASET_FIELD(dataset_id, name, `path`, data_categories, data_qualifier) values (2,'field1', null, '["credentials"]','aggregated_data');
INSERT INTO DATASET_FIELD(dataset_id, name, `path`, data_categories, data_qualifier) values (2,'field2', null, '[]','pseudonymized_data');