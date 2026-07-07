---
name: tests
description: "Skill for the Tests area of github-sync. 66 symbols across 13 files."
---

# Tests

66 symbols | 13 files | Cohesion: 87%

## When to Use

- Working with code in `tests/`
- Understanding how normalize_platform, build_url, test_build_url_github_ssh work
- Modifying tests-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_platform.py` | test_build_url_github_ssh, test_build_url_github_pat, test_build_url_gitee_ssh, test_build_url_gitee_pat, test_build_url_cnb_pat (+7) |
| `tests/test_sync.py` | test_check_conflict_no_commits, test_check_conflict_only_source_has_commits, test_check_conflict_only_target_has_commits, test_check_conflict_source_equals_target, test_check_conflict_target_is_ancestor_of_source (+5) |
| `tests/test_config.py` | test_load_minimal_config, test_load_full_config, test_load_config_defaults, test_load_config_missing_sync_key_raises, test_load_config_topology_not_list_raises (+4) |
| `tests/test_credential.py` | test_get_secret_name_ssh, test_get_secret_name_pat, test_load_credentials_missing_all_raises, test_load_credentials_collects_all_set, test_load_credentials_required_missing_raises (+1) |
| `tests/test_git_helper.py` | test_get_head_sha_returns_commit, test_get_head_sha_missing_branch_returns_none, test_clone_or_fetch_clones_bare_url, test_clone_or_fetch_fetches_updates, test_push_branch_to_bare (+1) |
| `src/git_helper.py` | get_head_sha, _run, clone_or_fetch, push_branch, prepare_ssh_key |
| `src/config.py` | _parse_endpoint, _parse_entry, _parse_settings, load_config |
| `src/sync.py` | check_conflict, _merge_base, _resolve_credentials, sync_topology_entry |
| `tests/test_main.py` | test_run_sync_empty_topology, test_run_sync_missing_config_raises, test_run_sync_returns_nonzero_on_failure |
| `src/platform.py` | normalize_platform, build_url |

## Entry Points

Start here when exploring this area:

- **`normalize_platform`** (Function) — `src/platform.py:25`
- **`build_url`** (Function) — `src/platform.py:30`
- **`test_build_url_github_ssh`** (Function) — `tests/test_platform.py:13`
- **`test_build_url_github_pat`** (Function) — `tests/test_platform.py:18`
- **`test_build_url_gitee_ssh`** (Function) — `tests/test_platform.py:23`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `normalize_platform` | Function | `src/platform.py` | 25 |
| `build_url` | Function | `src/platform.py` | 30 |
| `test_build_url_github_ssh` | Function | `tests/test_platform.py` | 13 |
| `test_build_url_github_pat` | Function | `tests/test_platform.py` | 18 |
| `test_build_url_gitee_ssh` | Function | `tests/test_platform.py` | 23 |
| `test_build_url_gitee_pat` | Function | `tests/test_platform.py` | 28 |
| `test_build_url_cnb_pat` | Function | `tests/test_platform.py` | 33 |
| `test_build_url_cnb_ssh_raises` | Function | `tests/test_platform.py` | 38 |
| `test_build_url_cnb_missing_token_raises` | Function | `tests/test_platform.py` | 44 |
| `test_build_url_gitcode_ssh` | Function | `tests/test_platform.py` | 49 |
| `test_build_url_gitcode_pat` | Function | `tests/test_platform.py` | 54 |
| `test_build_url_unknown_platform_raises` | Function | `tests/test_platform.py` | 59 |
| `test_build_url_pat_missing_token_raises` | Function | `tests/test_platform.py` | 64 |
| `test_normalize_platform_case_insensitive` | Function | `tests/test_platform.py` | 69 |
| `load_config` | Function | `src/config.py` | 129 |
| `test_load_minimal_config` | Function | `tests/test_config.py` | 16 |
| `test_load_full_config` | Function | `tests/test_config.py` | 34 |
| `test_load_config_defaults` | Function | `tests/test_config.py` | 94 |
| `test_load_config_missing_sync_key_raises` | Function | `tests/test_config.py` | 120 |
| `test_load_config_topology_not_list_raises` | Function | `tests/test_config.py` | 127 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → _parse_endpoint` | cross_community | 5 |
| `Main → Normalize_platform` | cross_community | 5 |
| `Main → _run` | cross_community | 5 |
| `Main → _parse_settings` | cross_community | 4 |
| `Main → Get_secret_name` | cross_community | 4 |
| `Main → _resolve_credentials` | cross_community | 4 |
| `Main → Get_head_sha` | cross_community | 4 |

## How to Explore

1. `context({name: "normalize_platform"})` — see callers and callees
2. `query({query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
