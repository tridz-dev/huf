# DocType name clash audit (Frappe 16.61.0)

Every Huf DocType name was compared, ignoring case, with the DocType JSON files
of the apps on a Frappe 16.61.0 bench. Huf has 153 DocTypes.

| App | Version | DocTypes | Clashes with Huf |
|---|---|---|---|
| frappe (core) | 16.61.0 | 332 | none |
| erpnext | 16.61.0 | 534 | none |
| hrms | 16.60.0 | 161 | `Skill` (Huf module `Huf`, HRMS module `HR`) |
| payments | 16.0.1 | 10 | none |

## Core

Frappe core's `Flow` module ships `Flow Run`, which Huf also used. Huf's DocType
is now `Agent Flow Run` (patch `huf.patches.v1.rename_flow_run_to_agent_flow_run`).
`Flow Definition`, `Flow State` and `Flow Member State` do not clash.

CI (`.github/workflows/server-tests.yml`) has no Frappe version pin.

## Open: `Skill` and HRMS

Huf and HRMS both define a DocType named `Skill`. A site cannot hold both, so
installing Huf and HRMS on one site is not safe. This is not a core clash and is
not changed here: renaming Huf's `Skill` needs its own change and data patch.

Installing both on one site was not tried; this finding comes from the JSON files.
