Set objShell = CreateObject("WScript.Shell")
objShell.Run "cmd /c cd /d C:\Users\oates\Projects\polaris && C:\Users\oates\AppData\Local\Programs\Python\Python313\Scripts\polaris.exe schedule publish-due", 0, False
