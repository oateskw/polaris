Set objShell = CreateObject("WScript.Shell")
objShell.Run "cmd /c cd /d C:\Users\oates\Projects\polaris && C:\Users\oates\AppData\Local\Programs\Python\Python313\Scripts\polaris.exe leads reply-comments >> C:\Users\oates\Projects\polaris\logs\comment_replies.log 2>&1", 0, False
