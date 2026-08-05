# Project TODO

## Upload lifecycle and isolation

- Add a configurable upload-size limit and reject oversized requests before
  saving or parsing them. FITS parsing should also have an explicit resource
  budget appropriate for in-memory Astropy/NumPy processing.
- Replace the shared `/tmp/cmfgen_viewer_uploads` default with an
  instance-specific upload namespace so separately configured viewer
  processes do not list or access each other's uploads. Create upload
  directories with restrictive permissions.
- Wire the existing upload TTL cleanup into application startup or a bounded
  periodic maintenance path so expired upload bundles do not accumulate.

## Related planning

- HR-diagram data and overlay work remains tracked in `TODO_HR.txt`.
