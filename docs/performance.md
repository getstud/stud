# Measured workloads

These September 10 measurements use the corrected inch-authored projects on an Apple M4 running macOS 26.6.2 and Python 3.13. They are local acceptance measurements, not a hardware-independent capacity promise. Browser measurements use Chrome with ANGLE Metal. Native execution, including the full Python design, remains in a worker process.

## Workload and targets

The workbench has 12 parts, the detailed shed 181, and the repeated framing case 360. The mansion is a 5,488 ft² two-storey courtyard framing study with 6,630 physical parts, 107 native shape assets and 11,334 native requirements at its default settings. It includes nested rotated wings, openings, stair voids, sloped rafters, sheet edges and a deliberate bore. Its authored omissions remain visible; it is not a complete site or structural design.

A local edit still executes all source geometry. Native relationship checks can take minutes for a building-wide change; navigation and review remain available while they run. These targets distinguish interactive review from background geometry work.

| Operation on this machine | Acceptance target |
| --- | --- |
| Workbench / shed / repeated framing worker | 3 / 15 / 6 seconds |
| Mansion cold worker / whole-building rotation | 420 / 360 seconds |
| Mansion local opening / shared windows or roof/module edit | 110 / 150 seconds |
| Mansion peak worker resident memory | 1.5 GiB |
| Mansion estimate / archived checkpoint read / common-price comparison | 1 / 1 / 7.5 seconds |
| Mansion three authored drawing views | 15 seconds |
| Mansion viewer ready on hardware rendering | 8 seconds |
| Mansion scene application / unchanged patch | 300 / 50 milliseconds |
| Mansion hardware-rendered frame interval, p95 | 34 milliseconds |

The former 100-second local-opening target was exceeded after correcting the example geometry to native inches: the pilot took 104.5 seconds and the complete sequence took 103.9 seconds. The selected budget is now 110 seconds (D028). This is an explicit adjustment, not a pass against the old target. The complete sequence spent 73.7 seconds executing source and 28.8 seconds checking relationships. Exact native cache identities remain intact. The eight-second viewer target was selected earlier after two 6.6-second opens; the final native-inch viewer is comfortably within it.

## Final runtime baselines

All four baselines use commit `460c468`, including the read-only `Model.units` guard. All requested native checks pass.

| Workload | Parts | Worker seconds | Peak GiB | Plan seconds |
| --- | ---: | ---: | ---: | ---: |
| Workbench | 12 | 1.61 | 0.444 | 1.81 |
| Shed | 181 | 9.86 | 0.451 | 2.32 |
| Repeated framing | 360 | 3.11 | 0.451 | 2.68 |
| Mansion | 6,630 | 259.61 | 0.881 | 7.00 |

The mansion captured source in 2.2 ms, executed geometry/publication in 71.62 seconds and checked native relationships in 186.65 seconds. Native archiving took 0.75 seconds and tessellation 1.96 seconds; these timers are included in execution and must not be added to it. Its estimate took 0.78 seconds and an archived checkpoint read took 0.39 seconds. The drawing measurement covers three authored views on one page, excluding thousands of cut-list rows; it is not a complete mansion construction-packet measurement.

The final mansion published 93 durable partial snapshots and coalesced 1,290 intermediate submissions. Snapshot preparation cost 2.23 seconds and background writes 6.14 seconds. Partial files totaled 220.3 MB, the completed manifest was 19.7 MB, and 107 mesh assets totaled 64,904 bytes. Partial snapshots retain geometry and measurement references. Completed manifests retain requirements, quantities, instructions and drawing definitions.

## Native edit sequence

Every edited source was evaluated with query reuse and again with reuse explicitly disabled. All five pairs passed the full native comparison. Each edit was finalized and compared with the default checkpoint at a common saved price basis.

| Mansion change | Parts | Worker seconds | Native checks seconds | Peak GiB | Common-price comparison seconds | Fresh full evaluation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Cold default | 6,630 | 259.83 | 183.48 | 0.886 | — | Cold checks |
| Local opening | 6,631 | 103.89 | 28.82 | 0.940 | 4.87 | Matches |
| Shared window widths | 6,796 | 143.83 | 67.25 | 0.769 | 5.32 | Matches |
| Whole-building rotation, 23° | 6,796 | 278.97 | 188.85 | 0.868 | 5.37 | Matches |
| Remove module, change roof slope and bore | 6,169 | 132.35 | 62.46 | 0.907 | 5.15 | Matches |
| Restore defaults | 6,630 | 93.18 | 17.00 | 0.885 | 5.15 | Matches |

This sequence ran under the frozen `cb1ce6e` runtime. The subsequent `460c468` change prevents public reassignment of `Model.units`; geometry, query, cache and publication algorithms are unchanged. Its real-worker regression covers both unit directions, before and after part publication. The fresh final-runtime baselines above confirm the measured workload after that guard. The evidence records both commits separately and retains the five same-runtime comparisons, both manifest hashes, full-build identities and the reviewed comparator hash. [Native evidence](evidence/native-performance.json).

Earlier metric-authored measurements and rejected experiments remain in that evidence file as historical records. They diagnosed repeated native relationship queries and repeated serialization of growing partial manifests. The native-inch measurements above are the current acceptance record; the earlier examples had different physical dimensions and are not a controlled same-source comparison.

## Browser measurements

The final native-inch mansion opened in 4.50 seconds. Preparing its assets took 2.09 seconds and applying the 6,630-instance scene took 148 ms. An isolated fresh scene took 156 ms; its unchanged patch took 9.6 ms, retained every object instance and requested zero additional assets. Hardware rendering had a 16.7 ms median and 33.4 ms p95 frame interval. There were no page errors or idle model/check requests. [Browser evidence](evidence/mansion-viewer-performance.json), [screen](evidence/mansion-viewer-performance.png).

Hardware rendering is required for this interaction budget. An earlier SwiftShader measurement had about 150 ms median and 167 ms p95 frame intervals and did not meet it.

## Correctness of reuse

The native query cache is disposable and scoped to the runtime fingerprint. Keys include exact native BREP identities, relevant world placements, targets, numerical policy, thresholds, tolerances and declared project units. Local stock-fit checks can share an entry for identical local solids and blanks. World relationship checks invalidate on placement changes. Cache misses and malformed entries execute the native query. No bounding-box result substitutes for a native measurement.

The benchmark compares source/runtime, authored metadata, placements, quantities, measured values, statuses, coverage, instructions and drawings exactly. When OCCT emits distinct BREP bytes for the same geometry, it verifies both native hashes, requires matching topology counts and requires both directional solid differences to complete as empty compounds, without added fuzzy tolerance. Only derived bounding-box padding (native kernel precision plus arithmetic ULPs) and supplementary contact-distance roundoff (at most 1e-12 native units) have numeric allowances. Added tiny bores, moved equal-volume bores, split solids, placement/quantity changes and corrupt archives are rejected by regressions, including under optimized Python. Exact cache keys and the conservative production-history identity check are unchanged. Unit cases separately cover every query kind, cache corruption, publication replacement and current-job priority over historical evaluation.

The viewer shares immutable mesh assets and patches persistent object instances. Its ordered event stream replaces repeated idle native model/check downloads. Missing-asset and disconnected-event recovery are exercised by the complete browser acceptance script.

## Reproduction

Run `python scripts/benchmark-native.py --plans` for the four workloads and `python scripts/benchmark-native.py mansion --plans --edits` for the cached/full adversarial sequence. The script prints its isolated project and JSON evidence path. `--full-checks` is also available through the evaluate CLI for independent native checks.

Run `node scripts/benchmark-viewer.mjs PROJECT OUTPUT.json` against a closed, already evaluated benchmark project. Set `STUD_RENDERER=default` for the normal hardware backend; the default forces SwiftShader and records that limitation. The browser script asserts retained instances, no repeated asset requests, no idle model/check downloads and no page errors. See [implementation evidence](IMPLEMENTATION.md) for recovery, packet and installer checks.
