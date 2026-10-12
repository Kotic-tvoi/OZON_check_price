Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
command = "cmd.exe /c " & Chr(34) & Chr(34) & folder & "\ЗАПУСК.bat" & Chr(34) & Chr(34)
shell.Run command, 0, False
