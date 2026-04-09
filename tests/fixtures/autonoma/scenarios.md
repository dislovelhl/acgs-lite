---
scenario_count: 3
scenarios:
  - name: standard
    description: >
      Typical ACGS deployment with representative constitutional rules,
      validation actions, audit trail entries, compliance mappings, and users.
    entity_count: 68
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
      - compliance_framework_mapping
      - user_account
  - name: empty
    description: >
      Fresh installation with no user-created data.
    entity_count: 4
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
  - name: large
    description: >
      Stress scenario with high-volume data exceeding pagination thresholds.
    entity_count: 1137
    entity_types:
      - constitutional_rule
      - validation_action
      - audit_entry
      - clinical_record
      - compliance_framework_mapping
      - user_account
---
