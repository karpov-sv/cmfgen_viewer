# Model-operation permission review

Reviewed on 26 October 2026 after fixing copies from read-only source models.
This review covers source-side locking and permissions inherited by newly
created working files. It does not change ownership or ACLs on existing sources.

## Findings and fixes

| Operation | Finding | Result |
|---|---|---|
| New Model from Current / CLI copy | Previously created a mutation lock in the source and inherited read-only permissions. | Already corrected: use a read-only guard, share an existing readable lock, check file consistency, and publish an owner-writable destination. |
| Prepare LTE/hydro workspace | Root inputs and templates copied with `copy2` could remain read-only in the new workspace. | New working inputs are owner-writable. Template and root source permissions remain unchanged; the saved old structure still uses the backup-copy policy. |
| Outputs to inputs (`out2in`) | Read-only population/GAMMAS outputs produced read-only startup inputs. | New staged startup inputs are owner-writable. Original outputs and transaction rollback files retain their write permissions. |
| Promote LTE/hydro results | Read-only generated products became read-only root structure/opacity files, potentially preventing later native updates. | Newly promoted products are owner-writable. The atomic-copy default used for rollback retains the existing permission policy. |

`workflow_permissions.copy_working_file` explicitly distinguishes new working
copies from `copy_readable`, which remains appropriate for archives and exact
rollback paths. Promotion requests owner-write permission on its new atomic
copies, while rollback uses the default. No global umask, blanket recursive
chmod, or source-side chmod is introduced.

## Other operations checked

- Template resolution, parameter display, copy/cleanup planning, structure
  previews, and archive previews read their sources without creating model
  mutation locks. Read-only inspection still requires readable files and
  sufficient process visibility where activity is checked.
- Editing parameters, applying structure changes, cleanup, out2in, history
  restoration, promotion, and runner launch mutate the selected model. Their
  model-side write locks are necessary and remain in place.
- Rename/move also retains mutation locking. It needs access to an existing
  writable mutation lock, or permission to create one in the source directory,
  even where the operating system could rename a read-only directory using
  parent-directory permissions alone. It preserves
  the moved model's permissions; copying is the supported way to create a new
  writable model from an immutable source.
- Existing readability helpers already skip unnecessary chmod/fchmod calls on
  shared readable artifacts. This avoids requiring ownership merely to open
  an already permitted shared file.
- Temporary-control restoration, input-history restoration, and transaction
  rollback retain their established permission policies. They are not treated
  as new editable working copies. Protected existing locks are not replaced,
  unlinked, or made writable to bypass another user's access restrictions.

## Validation

Regression tests exercise read-only templates, generated outputs, working-copy
writes, preservation of source modes, and promotion failure followed by rollback
to read-only originals. Existing workflow, out2in, promotion, permission-helper,
archive-restoration and copy/locking tests cover the surrounding operations.
All 185 targeted tests passed, along with compile and whitespace checks.
Only temporary test models are modified; installed CMFGEN sources and user
models are not changed.
