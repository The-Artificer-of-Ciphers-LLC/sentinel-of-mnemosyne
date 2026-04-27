"""sentinel_shared — code shared between sentinel-core and module containers.

Mounted into each container at build time via Docker Compose `additional_contexts`
and copied with `COPY --from=shared sentinel_shared/ /app/sentinel_shared/`.
Importable as `sentinel_shared.<module>` from any service.
"""
