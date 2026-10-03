' Launch the mania-render node supervisor with NO visible console window.
'
' Why a VBS wrapper instead of "powershell.exe -WindowStyle Hidden":
'   -WindowStyle Hidden still allocates a console and relies on the window manager not
'   painting it; started from Task Scheduler in the interactive session a window can
'   still flash for a frame. WScript.Shell.Run with an intWindowStyle of 0 asks Windows
'   for a process that has no window at all, which is deterministic.
'
' WHY wait = True  (this is load-bearing -- do not "optimise" it to False)
' ----------------------------------------------------------------------
'   Task Scheduler puts a task's processes in a job object and terminates that job as
'   soon as the task's ACTION process exits. With wait = False, wscript.exe returns
'   immediately after spawning powershell, the task counts as finished, and Task
'   Scheduler then kills the supervisor -- and its ssh and render service -- with it.
'   That was observed here: the task reported LastTaskResult=0 while no supervisor
'   process, no ssh process and no log file existed anywhere on the machine.
'   Waiting keeps wscript.exe alive exactly as long as the supervisor runs, so the task
'   stays Running and nothing is torn down. The visible side effect is that Task
'   Scheduler permanently shows this task as Running -- which doubles as a status light.

Option Explicit

Dim fso, shell, here, script, cmd, i, args
Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

here = fso.GetParentFolderName(WScript.ScriptFullName)
script = here & "\render-node.ps1"

args = ""
For i = 0 To WScript.Arguments.Count - 1
    args = args & " " & WScript.Arguments(i)
Next

' -File needs the script path QUOTED: it contains spaces, and an unquoted path makes
' powershell.exe fail with "the file does not have a '.ps1' extension".
cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ _
    & script & """" & args

' 0 = hidden window, True = wait for it to exit (see the note above).
shell.Run cmd, 0, True

