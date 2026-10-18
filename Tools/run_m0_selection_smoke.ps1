Remove-Item 'E:\AI\Tread\Tread\Saved\Reports\M0_Selection_Smoke.json' -Force -ErrorAction SilentlyContinue
$exe='G:\epicgame\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$p=Start-Process -FilePath $exe -ArgumentList 'E:\AI\Tread\Tread\Tread.uproject','-game','-ResX=1280','-ResY=720','-NoSplash','-TreadM0SelectionSmoke' -WorkingDirectory 'E:\AI\Tread\Tread' -PassThru
$done=$false
for($i=0;$i -lt 60;$i++){Start-Sleep -Seconds 1; if(Test-Path 'E:\AI\Tread\Tread\Saved\Reports\M0_Selection_Smoke.json'){$done=$true;break}; if(-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)){break}}
Write-Output ('done='+$done)
if(Test-Path 'E:\AI\Tread\Tread\Saved\Reports\M0_Selection_Smoke.json'){Get-Content -Raw 'E:\AI\Tread\Tread\Saved\Reports\M0_Selection_Smoke.json'}
if(Get-Process -Id $p.Id -ErrorAction SilentlyContinue){Stop-Process -Id $p.Id -Force}
