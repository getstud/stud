# Final acceptance record

The implementation and automated evidence are indexed in [IMPLEMENTATION.md](IMPLEMENTATION.md). Owner decisions are in [DECISIONS.md](DECISIONS.md). Physical printing is waived in favor of direct PDF verification. Legacy migration is outside scope.

| Gate | Evidence and current state |
| --- | --- |
| Native model, lifecycle, review, prices, alternatives and recovery | Implemented and exercised by independent geometry cases, interface tests and the recorded real-browser sequence. |
| PDF scale, consistency and legibility | Passed automated vector/geometry checks and inspection of all 24 final pages. [Packet index](evidence/packets/acceptance.json). |
| Representative building workload | All five cached edit results match full evaluation. The portable runtime reproduces the same model and meets the selected [local targets](performance.md). |
| macOS ARM installation | The final runtime DMG was mounted and its installed copy passed the native workflow, data preservation and full-folder reopening checks. The compatible bundle audit found zero deployment violations across 682 Mach-O files. |
| macOS Intel and Windows installation | Initial native CI identified portability issues, which are fixed locally. The next CI push is awaiting owner approval after automatic approval review rejected the public push. |
| Actual signed update and preservation | The current native Tauri updater installed preview.8 over preview.7 and passed all preservation checks using a generated local test key. [Evidence](evidence/macos-arm64-test-key-update.json). The production-key CI trial remains required. |
| DIY reader check | Awaiting the owner's answer on whether direct PDF verification also satisfies this gate. If retained, use the short procedure below. |

## Reader procedure

Give the reader only the [four-page workbench packet](evidence/packets/workbench/plans.pdf) and the [fourteen-page shed packet](evidence/packets/shed/plans.pdf). No physical printing or construction is required for this review. Record the packet's checkpoint/build references with the response.

1. From the workbench packet, identify the purchased boards, sheet and hardware packs; distinguish those purchases from finished parts and cut types.
2. Select one leg and one rail, find their cut lengths and marks, and trace them into the assembly view and fastening instruction.
3. From the shed packet, trace a wall opening, a roof bearing cut and a sheet edge to their corresponding details and parts.
4. Identify the shed's unresolved foundation/anchorage and rated uplift requirements, and explain what additional design decisions are needed before using it as a construction packet.
5. Report any missing instruction, ambiguous label, unreadable dimension or mismatch that prevents following the intended sequence.

Pass when a reader can complete these tasks from the packet, identify its explicit limitations and follow the sequence without an unexplained gap. Record the reader, date, packet versions and answers. A missing or incorrect instruction requires a revision and a repeat of the affected task. This form is preparation for the check, not evidence that a reader has completed it.

## Native release procedure

The `Desktop installers` workflow tests the same candidate on macOS ARM, macOS Intel and Windows. Dispatch it with `signed_candidate=true` to create production-signed candidate artifacts and run update acceptance without creating a tag, publishing a release or advancing a feed. Each host installs its own DMG or NSIS package and runs the full native smoke test. Signed candidates and signed tag builds also run `scripts/ci-native-update.mjs`, which selects the newest older published release, installs it into a marked temporary folder, verifies the candidate signature through Tauri and invokes the actual updater installer.

The update probe seeds a native fixture using the candidate runtime before upgrading the older app. This allows current native records to be checked even when the older public release predates the native project format. After the upgrade, the installed CLI must report the new version and reopen the fixture with identical project/checkpoint identity, prompt text, saved pricing, PDF bytes and unrelated file. The normal copy/reopen and update-lock checks then run again. A marker is written only after all preservation assertions pass. The production signing key is never downloaded to the test project.

The probe exercises the current updater installing over a previous app with a supplied public key. It does not drive the previous app's update UI or verify that app's embedded feed/key configuration. Keep that limitation visible when assessing production rollout readiness.

The Windows probe is restricted to disposable GitHub-hosted runners and refuses an existing stud uninstall registration. NSIS also changes account-level registration, shortcuts and PATH, so a temporary install folder alone is insufficient isolation on a normal Windows user account. The runner checks use GitHub's documented [runner environment and temporary-directory variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables).

Release preparation uses preview.8 because preview.7 is already public. An unpublished draft and local/test-key builds do not advance the public update feed. Keep a production-key update result distinct from a local test-key result; the evidence records the public-key fingerprint and key category.
