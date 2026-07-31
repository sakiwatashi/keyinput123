Unicode True
RequestExecutionLevel admin
SetCompressor /SOLID lzma

!define PRODUCT_NAME "智慧優先注音"
!define PRODUCT_VERSION "0.6.1"
!define PRODUCT_PUBLISHER "Smart Priority Bopomofo contributors"
!define PRODUCT_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\SmartPriorityBopomofo"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\release\Smart-Priority-Bopomofo-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES32\SmartPriorityBopomofo"
InstallDirRegKey HKLM "${PRODUCT_KEY}" "InstallLocation"
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "0.6.1.0"
VIAddVersionKey /LANG=1028 "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=1028 "CompanyName" "${PRODUCT_PUBLISHER}"
VIAddVersionKey /LANG=1028 "FileDescription" "${PRODUCT_NAME} 安裝程式"
VIAddVersionKey /LANG=1028 "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=1028 "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey /LANG=1028 "LegalCopyright" "Copyright (c) 2026 Smart Priority Bopomofo contributors"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_NOAUTOCLOSE
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\release-staging\THIRD_PARTY_NOTICES.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "TradChinese"

Section "安裝智慧優先注音" SEC_MAIN
    SetShellVarContext current
    SetOutPath "$INSTDIR"
    File "install.ps1"
    File "native_ui_preference.ps1"
    File "uninstall.ps1"
    File "..\release-staging\THIRD_PARTY_NOTICES.txt"
    File "..\release-staging\PIME-LICENSE.txt"
    File "..\release-staging\libchewing-COPYING.txt"
    File "..\release-staging\rime-essay-LICENSE.txt"
    File "..\release-staging\MOE-OPEN-DATA-NOTICE.txt"
    File "..\release-staging\McBopomofo-LICENSE.txt"

    InitPluginsDir
    SetOutPath "$PLUGINSDIR\payload"
    File /oname=PIME-1.3.0-stable-setup.exe "..\vendor\PIME-1.3.0-stable-setup.exe"
    SetOutPath "$PLUGINSDIR\payload\overlay"
    File /r "..\dist\PIME-overlay\*"

    ${If} ${RunningX64}
        StrCpy $1 "$WINDIR\SysNative\WindowsPowerShell\v1.0\powershell.exe"
    ${Else}
        StrCpy $1 "$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    ${EndIf}
    nsExec::ExecToLog '"$1" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\install.ps1" -PayloadRoot "$PLUGINSDIR\payload"'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP|MB_OK "安裝失敗（結束碼 $0）。詳細記錄：%ProgramData%\SmartPriorityBopomofo\install.log"
        Abort
    ${EndIf}

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "${PRODUCT_KEY}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr HKLM "${PRODUCT_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr HKLM "${PRODUCT_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr HKLM "${PRODUCT_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${PRODUCT_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "${PRODUCT_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${PRODUCT_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    SetShellVarContext current
    ${If} ${RunningX64}
        StrCpy $1 "$WINDIR\SysNative\WindowsPowerShell\v1.0\powershell.exe"
    ${Else}
        StrCpy $1 "$WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
    ${EndIf}
    nsExec::ExecToLog '"$1" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\uninstall.ps1"'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP|MB_OK "解除安裝未完成（結束碼 $0）。詳細記錄：%ProgramData%\SmartPriorityBopomofo\uninstall.log"
        Abort
    ${EndIf}
    DeleteRegKey HKLM "${PRODUCT_KEY}"
    RMDir /r "$INSTDIR"
SectionEnd
