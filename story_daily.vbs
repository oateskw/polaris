Set objShell = CreateObject("WScript.Shell")
objShell.Run "cmd /c cd /d C:\Users\oates\Projects\polaris && C:\Users\oates\AppData\Local\Programs\Python\Python313\Scripts\polaris.exe content post-story >> C:\Users\oates\Projects\polaris\logs\stories.log 2>&1", 0, False
