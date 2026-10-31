# CMFGEN dated patch revisions

The maintained cumulative patch stream identifies itself as
`CMFGEN_VIEWER_PATCH 2026-10-31.1`. The date is the source release date; the final
number distinguishes releases made on the same day. It is not a compilation
timestamp. Every later revision must contain all earlier fixes in this stream.
A newer upstream CMFGEN date alone does not imply any local repairs.

## Runtime and model identification

```sh
/path/to/cmfgen_dev.exe --version
```

This prints the patch stream/revision and upstream release, then exits before
opening files, reading model inputs or allocating model arrays. The wrapper and
main subroutine share `new_main/cmfgen_version.inc`. It defines the readable
`PRODATE`, original `UPSTREAM_DATE`, and complete `PATCH_REVISION`.

OUTGEN, MODEL, MOD_SUM and RVTJ carry the producing patch
revision. The MOD_SUM parser, model information and run previews display it.
RVTJ keeps the revision on its existing Program Date row: native readers use
fixed header positions, so no new header row is inserted. The native V5 reader
was exercised against the stamped file.

Historical output stamps identify the producing calculation; they never grant
eligibility to a different currently installed executable.

The viewer queries the selected executable in an empty temporary directory with
closed stdin and a timeout. This also protects models when old executables
ignore the argument. Unidentified, malformed or foreign version reports cannot
authorize version-dependent remedies. Query results are cached against the
executable's path, inode, size and modification/change times; replacing the
executable invalidates the cache.

## Remedy requirements

The first fully stamped release, `2026-10-31.1`, includes numerical fixes 1–28,
optimizations 29–30, fixed-output support 31, opacity diagnostic 32 and the build /
versioning changes 33. Existing remedies that previously required authenticated
capabilities now require this minimum dated revision. Their measured-evidence,
conservation, guard and rollback checks are unchanged. Generic remedies that
never required patched numerical code retain their existing eligibility.

New remedies can specify a later minimum explicitly:

```python
repaired_runtime(ctx.native_plan, minimum='2026-11-02.1')
```

Do not raise the shared baseline minimum merely because a new release exists.
Keep the oldest sufficient requirement for each remedy. Source cherry-picks or
experimental branches missing cumulative fixes must not claim a later revision
of this stream.

`cmfgen-local-build.json` is now an optional maintainer audit record. Runtime
eligibility does not read it, its capability list, or executable hashes from it.
Older audit records may be retained as historical evidence.

## Apply or update the source patch set

Run the standalone updater from the viewer checkout (Python standard library
and `git` only; no viewer dependencies are required):

```sh
python3 cmfgen_patch.py /path/to/cur_cmf --check
python3 cmfgen_patch.py /path/to/cur_cmf
```

After updating the viewer repository, run the same command again to update the
source to its latest bundled patch set. `--check` is a read-only preview;
`--json` provides a structured plan. `--manifest PATH` can select an alternate
cumulative manifest and its adjacent patch file.

The updater always preserves `Makefile_definitions` and
`com/aliases_for_cmfgen.sh`, including local links to those settings. It does
not change source Git history, unrelated files, executables or model folders.
It recognizes pristine release 18jun25 files, already-current files, and earlier
managed patches. Older unrecorded patches can be recognized from exact hashes
in the viewer repository's local patch history. This requires running the
script from a checkout containing that history; it never fetches from the
network. Unrecognized edits or a different upstream baseline stop the entire
update before source files are changed. No force-overwrite mode is provided.

Each installation retains its patch and compact source manifest in
`.cmfgen-patches/`. This is update bookkeeping, independent of the optional build
record and runtime remedy eligibility. On subsequent updates the script reverses
only recognized old changes in an isolated staging directory, applies the new
patch, and verifies the resulting file hashes. Fixes removed from a newer patch
are restored to their upstream content; files added only by a retired patch
are removed. Source revision downgrades are refused.

Pre-update files and the change plan are kept under
`.cmfgen-backups/*-source-patch-*/`. Writes are atomic per file, competing updater
processes are locked out, and write failures roll back owned changes while
preserving concurrent external edits. Local source modifications must be
reviewed/merged rather than silently overwritten. An already-current install
is a no-op after its patch state has been registered.

The script patches **sources only**. Rebuild separately using the command below,
in an isolated checkout or between model jobs. No calculation or build is
started automatically.

## Rebuild and release

1. Update `new_main/cmfgen_version.inc` for every source-patch release. Increase
   the final revision number for further releases on the same date; update
   PRODATE when the day changes. Both main object dependencies include the file.
2. Update the consolidated patch/manifest and run relevant scientific tests.
3. Build serially, starting from a clean tree:

```sh
cd /path/to/cur_cmf
make -j1 clean && make -j1 all
./exe/cmfgen_dev.exe --version
```

Use a separate source/build directory while calculations use an installed
checkout. The top-level clean target removes executables and archives in that
tree. Its updated recipe also removes source-local module files. This build is
not parallel-safe: `make -j clean all` can race cleanup against compilation,
and recursive targets share archives/module directories.

The updated top-level all target performs three final links after every
recursive archive update, so this command is sufficient for a complete build
using the default layout. No JSON-recording step is required. The optional
record_local_build.py helper still validates sources/Makefiles, can repair final
links after selective builds, and can write provenance for maintainers.

The macOS clean-build test also exposed a missing partial-build module export:
`plane/Makefile` now publishes `mod_var_mom_j_cmf.mod` to MOD_DIR when building
that archive member through the forwarding rule. A stale local module is removed
before compilation, supporting both default module output and compiler `-J`
settings. This changes build dependencies/output placement, not numerical code.

Existing automatic jobs pin their executable. Install a new release between
jobs, after the current automatic loop stops, to avoid interrupting it.


## Release validation (31 October 2026)

Revision `2026-10-31.1` was validated after stopping an active automatic loop
through its normal cancellation handler. The loop reported stable-state
restoration, and a subsequent fresh-start preflight passed. This checks the
activation/cancellation handoff; it does not establish model convergence.

Validation includes a clean serial build of all 80 executables, current final
links, a no-output --version query, native zero-iteration initialization with
versioned OUTGEN/MODEL/RVTJ headers, and a checkpoint byte-identical to the
previous validated seed. The full consolidated patch applies and reverses with
all 52 file hashes checked. Runtime eligibility succeeds with no JSON build
record. The old record was retired to the rollback backup.

Installations preserve local compiler settings and aliases. Keep the source,
libraries, modules, executables and link objects needed for rollback together
under the installation's `.cmfgen-backups/` directory. Historical installation
locations and hashes remain in the patch manifest.
