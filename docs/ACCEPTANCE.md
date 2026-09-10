# Final acceptance record

All scoped implementation and acceptance gates are complete. The implementation and automated evidence are indexed in [IMPLEMENTATION.md](IMPLEMENTATION.md); owner decisions are in [DECISIONS.md](DECISIONS.md). Physical printing is waived in favor of direct PDF verification. Legacy migration is outside scope. Native-unit candidate `460c468` passed installation and production-key update preservation on macOS ARM, macOS Intel and Windows. The [candidate artifacts](evidence/native-release-artifacts.json) are retained in CI; no release was published and no update feed was advanced.

| Gate | Evidence and current state |
| --- | --- |
| Native model, lifecycle, review, prices, alternatives and recovery | Implemented and exercised by independent geometry cases, interface tests and the recorded real-browser sequence. |
| PDF scale, consistency and legibility | Passed automated vector/geometry checks and inspection of all 23 final pages. [Packet index](evidence/packets/acceptance.json). |
| Representative building workload | All five native-inch cached/full edit pairs agree. Fresh final-runtime baselines and hardware viewer timing meet the [selected local targets](performance.md), with the explicit 100-to-110-second local-opening budget adjustment (D028). |
| macOS ARM installation | The final `460c468` signed candidate passed DMG installation, the native smoke test, code-signature/notarization verification and production-key update preservation. [Final ARM evidence](evidence/updates/460c468-darwin-arm64.json). |
| macOS Intel installation | The final `460c468` signed candidate passed DMG installation, native smoke, code-signature/notarization verification and production-key update preservation. [Final Intel evidence](evidence/updates/460c468-darwin-x64.json). |
| Windows installation and update | The final candidate passed NSIS installation and native smoke. Its unchanged signed installer passed the corrected [focused update proof](https://github.com/getstud/stud/actions/runs/34493377698), including the Windows known-folder lock check and all six preservation assertions. [Final Windows evidence](evidence/updates/460c468-win32-x64.json). |
| Actual signed update and preservation | Final-candidate production-key preview.7-to-preview.8 updates preserve project identity, checkpoint, prompt, saved prices, PDF bytes and an unrelated file on all three platforms. The original Windows harness failure and its successful correction are explicitly recorded below. |
| DIY reader check | Passed by the owner on September 10 after the native-unit correction (D024/D026): “Reader check passed.” Workbench checkpoint `540026723064` and shed checkpoint `ea44f082fc42`; [packet identities and hashes](evidence/packets/verification.json). |

## Reader procedure

Give the reader only the [four-page workbench packet](evidence/packets/workbench/plans.pdf) and the [thirteen-page shed packet](evidence/packets/shed/plans.pdf). No physical printing or construction is required for this review. Record the packet's checkpoint/build references with the response.

1. From the workbench packet, identify the purchased boards, sheet and hardware packs; distinguish those purchases from finished parts and cut types.
2. Select one leg and one rail, find their cut lengths and marks, and trace them into the assembly view and fastening instruction.
3. From the shed packet, trace a wall opening, a roof bearing cut and a sheet edge to their corresponding details and parts.
4. Identify the shed's unresolved foundation/anchorage and rated uplift requirements, and explain what additional design decisions are needed before using it as a construction packet.
5. Report any missing instruction, ambiguous label, unreadable dimension or mismatch that prevents following the intended sequence.

Pass when a reader can complete these tasks from the packet, identify its explicit limitations and follow the sequence without an unexplained gap. Record the reader, date, packet versions and answers. A missing or incorrect instruction requires a revision and a repeat of the affected task. The owner completed this procedure on September 10 and answered “Reader check passed” for the packet versions identified above.

## Native release procedure

The `Desktop installers` workflow tests the same candidate on macOS ARM, macOS Intel and Windows. Dispatch it with `signed_candidate=true` to create production-signed candidate artifacts and run update acceptance without creating a tag, publishing a release or advancing a feed. Each host installs its own DMG or NSIS package and runs the full native smoke test. Signed candidates and signed tag builds also run `scripts/ci-native-update.mjs`, which selects the newest older published release, installs it into a marked temporary folder, verifies the candidate signature through Tauri and invokes the actual updater installer.

The update probe seeds a native fixture using the candidate runtime before upgrading the older app. This allows current native records to be checked even when the older public release predates the native project format. After the upgrade, the installed CLI must report the new version and reopen the fixture with identical project/checkpoint identity, prompt text, saved pricing, PDF bytes and unrelated file. The normal copy/reopen and update-lock checks then run again. A marker is written only after all preservation assertions pass. The production signing key is never downloaded to the test project.

Both macOS jobs passed completely in [candidate run 34487673963](https://github.com/getstud/stud/actions/runs/34487673963). Its Windows suite and ordinary installation passed, but the update probe reopened too early because its temporary `APPDATA` differed from NSIS's actual lock folder. The reviewed harness correction `c0384b0` passed [focused run 34493377698](https://github.com/getstud/stud/actions/runs/34493377698) using the unchanged signed Windows installer. The independent known-folder check reproduced the original bypass and verified the correction; the real update then recorded 121 blocked CLI polls before installation finished and all six preservation checks passed. The original workflow retains its failed Windows result; the focused run supplies the final Windows update evidence.

The probe exercises the current updater installing over a previous app with a supplied public key. It does not drive the previous app's update UI or verify that app's embedded feed/key configuration. Keep that limitation visible when assessing production rollout readiness.

The Windows probe is restricted to disposable GitHub-hosted runners and refuses an existing stud uninstall registration. NSIS also changes account-level registration, shortcuts and PATH, so a temporary install folder alone is insufficient isolation on a normal Windows user account. The runner checks use GitHub's documented [runner environment and temporary-directory variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables).

Windows signed-update probes preserve the runner's actual `APPDATA`, matching NSIS's Windows known-folder lock. Project and catalog data, `HOME` and `LOCALAPPDATA` remain isolated. An independent known-folder probe demonstrates that the former temporary `APPDATA` bypassed the installer lock and that the corrected environment rejects a CLI launch while that lock is held. The optional `recheck_windows_run` workflow input reuses an existing signed EXE and signature after a harness correction, rejects application-source changes, and records the original candidate commit, harness commit and payload hash. It does not build or publish a replacement installer.

Release preparation uses preview.8 because preview.7 is already public. An unpublished draft and local/test-key builds do not advance the public update feed. Keep a production-key update result distinct from a local test-key result; the evidence records the public-key fingerprint and key category.
