# Changelog

## 0.2.0 — 2026-10-12

- Convert the uploaded local prototype into a clean independent repository.
- Remove actual environment configuration, dependency folders, caches, and job data from source.
- Add English/Chinese docs, MIT license, contributor templates, CI, and release checks.
- Default UI/API to mock mode; prevent external story-planning calls in mock mode even when a key exists.
- Reject live-provider requests without their required key.
- Validate job IDs and enforce file containment with resolved paths.
- Normalize duplicate story node IDs and keep the root valid.
- Make mock output selection deterministic and limit FFmpeg encoding threads.
- Add backend regression checks including a real FFmpeg generation job.
- Keep live smoke scripts separate from automated tests and guard their entry points.
- Lock dependencies and use Vite 7.3.7 / React plugin 5.1.4 for the verified frontend build.

The prototype's provider adapters, prompt memory, graph player, job persistence, and manual resume flow are retained.
