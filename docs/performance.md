# Measured workloads

These are local acceptance measurements, not a hardware-independent capacity promise. The test machine is an Apple M4 running macOS 26.6.2 with Python 3.13. The browser measurements use Chrome with ANGLE Metal; software-rendered results are reported separately. Native execution, including the full Python design, remains in a worker process.

## Workload and targets

The workbench has 12 parts, the detailed shed 181, and the repeated framing case 360. The mansion is a 509.9 m² two-storey courtyard framing study with 6,630 physical parts, 114 reusable shape assets and 11,334 native requirements at its default settings. It includes nested rotated wings, openings, stair voids, sloped rafters, sheet edges and a deliberate bore. It is not a complete site or structural design; its authored omissions remain visible.

The following targets were chosen from measured work and the distinction between interactive review and background geometry work. A local edit still executes all source geometry. Native relationship checks can take minutes for a building-wide change; navigation and review remain available while they run.

| Operation on this machine | Acceptance target |
| --- | --- |
| Workbench / shed / repeated framing worker | 3 / 15 / 6 seconds |
| Mansion cold worker / whole-building rotation | 420 / 360 seconds |
| Mansion local opening / shared windows or roof/module edit | 100 / 150 seconds |
| Mansion peak worker resident memory | 1.5 GiB |
| Mansion estimate / archived checkpoint read / common-price comparison | 1 / 1 / 7.5 seconds |
| Mansion three authored drawing views | 15 seconds |
| Mansion viewer ready on hardware rendering | 6 seconds |
| Mansion scene application / unchanged patch | 300 / 50 milliseconds |
| Mansion hardware-rendered frame interval, p95 | 34 milliseconds |

## Native measurements

The initial four-case run measured the workbench at 1.83 seconds, the shed at 10.85 seconds and framing at 4.07 seconds. Their full plan packets took 1.91, 2.43 and 2.69 seconds. The initial mansion worker took 434.24 seconds and peaked at 1.28 GiB. Its source layout was subsequently corrected into a continuous courtyard; it retained the same part count and geometry mix, so this earlier result describes the diagnosed cost rather than a controlled same-source speedup.

The measured bottlenecks were repeated native relationship queries and repeated serialization of growing partial manifests. Native shape archiving and tessellation were comparatively small. A proposed full-metadata deep-copy implementation increased latency and was rejected before final acceptance.

| Mansion change | Parts | Worker seconds | Native checks seconds | Peak GiB | Common-price comparison seconds | Fresh full evaluation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Cold default | 6,630 | 358.30 | 223.18 | 0.87 | — | Cold checks |
| Local opening | 6,628 | 76.74 | 1.04 | 0.96 | 5.08 | Matches |
| Shared window widths | 6,793 | 127.21 | 47.36 | 0.88 | 5.47 | Matches |
| Whole-building rotation, 23° | 6,793 | 318.53 | 230.94 | 1.00 | 5.37 | Matches |
| Remove module, change roof slope and bore | 6,169 | 130.26 | 61.77 | 0.86 | 5.02 | Matches |
| Restore defaults | 6,630 | 74.34 | 0.21 | 0.97 | 5.22 | Matches |

The cold default captured source in 2.3 ms, executed geometry/publication in 133.66 seconds, archived native shapes in 1.42 seconds and tessellated in 2.52 seconds. Archive/tessellation timers are included in execution and must not be added to it. The estimate took 0.55 seconds, the archived checkpoint read 0.43 seconds, and three authored drawing views took 10.45 seconds. That drawing measurement excludes the thousands of cut-list rows and is not a complete mansion construction-packet measurement.

The final baseline published 144 durable partial snapshots and coalesced 1,239 intermediate submissions. Snapshot preparation cost 4.15 seconds and background writes 16.76 seconds. Partial files totaled 445 MB; the completed manifest was 20.9 MB and the 114 mesh assets totaled 68,640 bytes. Preview snapshots retain geometry and measurement references; completed manifests retain all requirements, quantities, instructions and drawing definitions.

## Correctness of reuse

The native query cache is disposable and scoped to the runtime fingerprint. Keys include exact native BREP identities, relevant world placements, targets, numerical policy, thresholds, tolerances and millimeter units. Local stock-fit checks can share an entry for identical local solids and blanks. World relationship checks invalidate on placement changes. Cache misses and malformed entries execute the native query. No bounding-box result substitutes for a native measurement.

Each edited source is evaluated once with query reuse and again with reuse explicitly disabled. The comparison includes geometry, placements, authored references, quantities, findings, instructions and drawings, excluding only execution identities, timings, provenance paths and cache keys. Every edit is finalized and compared at a common saved price basis. Unit cases separately cover every query kind, cache corruption, publication replacement and current-job priority over historical evaluation.

The viewer shares immutable mesh assets and patches persistent object instances. Its ordered event stream replaces repeated idle native model/check downloads. Missing-asset and disconnected-event recovery are exercised by the complete browser acceptance script.

## Reproduction

Run `python scripts/benchmark-native.py --plans` for the four workloads and `python scripts/benchmark-native.py mansion --plans --edits` for the cached/full adversarial sequence. The script prints its isolated project and JSON evidence path. `--full-checks` is also available through the evaluate CLI for independent native checks.

Run `node scripts/benchmark-viewer.mjs PROJECT OUTPUT.json` against a closed, already evaluated benchmark project. Set `STUD_RENDERER=default` for the normal hardware backend; the default forces SwiftShader and records that limitation. The browser script asserts retained instances, no repeated asset requests, no idle model/check downloads and no page errors. See [implementation evidence](IMPLEMENTATION.md) for the broader recovery, packet and installer checks.
