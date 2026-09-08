; The installer owns this lock. Tauri's updater exits the app before NSIS
; replaces files, so a GUI-owned lock alone cannot protect the runtime.
Var StudLockHandle
Var StudLockOverlapped

!macro StudUnlockRuntime
  ${If} $StudLockHandle != ""
  ${AndIf} $StudLockHandle != -1
    System::Call 'kernel32::CloseHandle(p $StudLockHandle)'
  ${EndIf}
  ${If} $StudLockOverlapped != ""
    System::Free $StudLockOverlapped
  ${EndIf}
  StrCpy $StudLockHandle ""
  StrCpy $StudLockOverlapped ""
!macroend

!macro StudLockRuntime
  CreateDirectory "$APPDATA\app.stud.desktop"
  ; GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
  ; OPEN_ALWAYS. Lock the same whole-file range as fs2 in the CLI.
  System::Call 'kernel32::CreateFileW(w "$APPDATA\app.stud.desktop\runtime.lock", i 0xC0000000, i 3, p 0, i 4, i 0x80, p 0) p.r0'
  StrCpy $StudLockHandle $0
  ${If} $StudLockHandle == -1
    SetErrorLevel 2
    Abort "Could not open stud's runtime lock."
  ${EndIf}
  System::Alloc 32
  Pop $StudLockOverlapped
  System::Call '*$StudLockOverlapped(p 0, p 0, i 0, i 0, p 0)'
  ; LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY.
  System::Call 'kernel32::LockFileEx(p $StudLockHandle, i 3, i 0, i -1, i -1, p $StudLockOverlapped) i.r0'
  ${If} $0 == 0
    !insertmacro StudUnlockRuntime
    MessageBox MB_OK|MB_ICONEXCLAMATION "Stop running stud viewers and CLI commands, then run this installer again." /SD IDOK
    SetErrorLevel 2
    Abort "stud is in use. No application files have been changed."
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro StudLockRuntime
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ExecWait '"$INSTDIR\stud-desktop.exe" --install-cli' $0
  ${If} $0 != 0
    DetailPrint "CLI setup did not finish. Open stud and choose Install CLI."
  ${EndIf}
  !insertmacro StudUnlockRuntime
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro StudLockRuntime
  ExecWait '"$INSTDIR\stud-desktop.exe" --uninstall-cli' $0
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  !insertmacro StudUnlockRuntime
!macroend
