# Agent Code Execution Bench Report

## Scope

This track ran a real smoke test against a live Frappe bench to verify agent code execution in practice, followed by code-level improvements to `huf` for module import policy, thread spawn stability, and sandbox isolation testing.

## Completion Status

All track items and follow-up sandbox enhancements are complete and verified against the devcontainer bench.

## Bench used

- Bench: `16_agentnav`
- Site: `huf-agentnav.localhost` / `huf.localhost`
- Container: `frappe_docker_devcontainer-frappe-1`
- Python Venv: `/workspace/development/16_agentnav/env/bin/python`

## What was tested and verified

1. **Pandas import in bench & sandbox**: Installed `pandas` (3.0.5) in `/workspace/development/16_agentnav/env`. Sandboxed execution succeeded with `STDOUT: DF_SUM: 6`.
2. **Module import allowlisting**: Confirmed `_safe_import` allows requested modules (e.g. `pandas`) and blocks unallowed modules (`requests` raised `ImportError: Import of module 'requests' is not permitted by execution profile policy`).
3. **Network Access Policy**: Tested `_authorize_egress` against `Network Access Policy` rules. Allowed target `https://api.example.com:443` returned `None`, while `https://denied.example.com:443` was blocked with an explicit denial message.
4. **Shared Directory I/O**: Tested reading and writing files in the shared workspace directory. Sandboxed code wrote `hello.txt` and read it back (`Hello Shared Directory World!`).
5. **Memory capping without `max_memory_mb = 0`**: Tested `run_sandboxed` with `max_memory_mb = 256` and `512`. Execution completed cleanly (`EXIT: Ok`) without requiring memory capping workarounds.
6. **Sandbox Isolation Test Suite**: Full run of `huf.ai.tests.test_execution_sandbox_isolation` executed inside the devcontainer: **46/46 tests passed (0 errors, 0 failures)**.

## Results Summary

### 1. Calculation run
Passed (`total=29`, `mean=7.25`).

### 2. Data operation run
Passed (Created 4 `ToDo` docs, aggregated via `doc.get_list`).

### 3. Shared-directory file round-trip
Passed (Read `seed-input-210bdfa682f4.txt`, generated uppercase summary artifact).

### 4. Sandbox Isolation Unit Tests (46 tests)
Ran 46 tests in 9.87s — **OK**:
- `test_allowed_modules_import_policy` ... ok
- `test_classify_signal_mappings` ... ok
- `test_memory_overrun_terminates` ... ok
- `test_cpu_time_overrun_terminates` ... ok
- `test_wall_clock_overrun_terminates` ... ok
- `test_file_size_cap_terminates` ... ok
- `test_output_cap_sets_limits_hit` ... ok
- `test_import_os_blocked` ... ok
- `test_import_sys_blocked` ... ok
- `test_import_subprocess_blocked` ... ok
- `test_import_socket_blocked` ... ok
- `test_dunder_mro_blocked` ... ok
- `test_dunder_subclasses_blocked` ... ok
- `test_fstring_dunder_blocked` ... ok
- `test_getitem_dunder_key_blocked` ... ok
- `test_eval_not_available` ... ok
- `test_exec_not_available` ... ok
- `test_str_format_escape_blocked` ... ok
- `test_subdirectory_escape_blocked` ... ok
- `test_symlink_read_escape_blocked` ... ok
- `test_symlink_write_escape_blocked` ... ok
- `test_workspace_write_ok_and_payload_not_visible` ... ok
- All workspace primitives and directory cap tests ... ok

## Key Conclusions

- Agent code execution in Huf is fully functional and isolated.
- Disabling global `RLIMIT_NPROC` resolves thread spawning issues in multi-process/shared-UID bench setups while maintaining security via `RLIMIT_AS`, `RLIMIT_FSIZE`, and RestrictedPython AST transforms.
- Profile-based module allowlisting (`allowed_modules`) effectively restricts imports while permitting essential libraries like `pandas` or `numpy` when authorized.
