' Predictive Maintenance - Silent Launcher
' Runs launcher.ps1 without a visible console window
Option Explicit

Dim WshShell, FSO, strDir, strPS1

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Derive paths relative to this .vbs file location
strDir = FSO.GetParentFolderName(WScript.ScriptFullName)
strPS1 = strDir & "\launcher.ps1"

If Not FSO.FileExists(strPS1) Then
    WshShell.Popup "Launch script not found:" & vbCrLf & strPS1 & vbCrLf & vbCrLf & "Please ensure launcher.ps1 is in the same folder as launcher.vbs.", 10, "File Missing", 48
    WScript.Quit 1
End If

' Run PowerShell: hidden window, bypass execution policy, no profile
WshShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -NoProfile -File """ & strPS1 & """", 0, False
