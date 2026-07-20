# Catalyst deployment order

1. Confirm identity, India DC, project, organization, CLI version, and quotas.
2. Capture before-inventory and existing component IDs.
3. Validate JSON/YAML/JavaScript, environment configuration, origins, placeholders, and secret absence.
4. Provision/version Data Store schema and Stratus buckets/prefixes idempotently.
5. Configure Authentication and trusted role/scope mapping.
6. Deploy mandatory Functions and AppSail.
7. Configure API Gateway so direct service bypass is not the submitted path.
8. Deploy Slate/Web Client with a real production API URL.
9. Enable only mandatory Signals, schedules, and supported organizer services.
10. Execute live authenticated journeys and negative-scope tests.
11. Test application rollback while retaining compatible data.
12. Capture after-inventory, cost state, failures, remediation, and redacted evidence.

Never call a declaration, local fake, console configuration, or screenshot a live invocation.
