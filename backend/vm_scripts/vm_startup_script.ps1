<powershell>
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

function Write-EC2Log {
    param ([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path "C:\CloudRAM\startup.log" -Value $logMessage -ErrorAction SilentlyContinue
}

# Ensure log directory exists
New-Item -Path "C:\CloudRAM" -ItemType Directory -Force | Out-Null
New-Item -Path "C:\Users\vm_user\SyncedNotepadFiles" -ItemType Directory -Force | Out-Null
New-Item -Path "C:\CloudRAM\logs" -ItemType Directory -Force

# Path to track script state
$stateFile = "C:\CloudRAM\script_state.txt"

# Function to get current state
function Get-ScriptState {
    if (Test-Path $stateFile) {
        return Get-Content -Path $stateFile
    }
    return "INITIAL"
}

# Function to set state
function Set-ScriptState {
    param ([string]$State)
    $State | Out-File -FilePath $stateFile -Force
}

# Create a scheduled task to resume script after reboot
function Register-ResumeTask {
    $taskName = "CloudRAM-ResumeScript"
    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File $PSCommandPath"
    $taskTrigger = New-ScheduledTaskTrigger -AtStartup
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Force -ErrorAction SilentlyContinue
}

# Main script logic with state machine
$currentState = Get-ScriptState
Write-EC2Log "Current state: $currentState"

switch ($currentState) {
    "INITIAL" {
        # Set Administrator password
        try {
            $adminPassword = "CloudRAM123!"
            net user Administrator $adminPassword
            net user Administrator /active:yes
        } catch {
            Write-EC2Log "ERROR: Failed to set Administrator password - $($_.Exception.Message)"
            exit 1
        }

        # Install Chocolatey
        try {
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        } catch {
            Write-EC2Log "ERROR: Failed to install Chocolatey - $($_.Exception.Message)"
            exit 1
        }

        # Install Python and dependencies
        try {
            Start-Process -FilePath "choco" -ArgumentList "install python python-pip -y" -Wait -NoNewWindow -PassThru
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c pip install websockify flask flask-cors psutil boto3 watchdog" -Wait -NoNewWindow -PassThru
        } catch {
            Write-EC2Log "ERROR: Failed to install Python or packages - $($_.Exception.Message)"
            exit 1
        }

        # Install UltraVNC
        try {
            Start-Process -FilePath "choco" -ArgumentList "install ultravnc -y" -Wait -NoNewWindow -PassThru
        } catch {
            Write-EC2Log "ERROR: Failed to install UltraVNC - $($_.Exception.Message)"
            exit 1
        }

        # Install Chrome
        try {
            Start-Process -FilePath "choco" -ArgumentList "install googlechrome -y --ignore-checksums" -Wait -NoNewWindow -PassThru
        } catch {
            Write-EC2Log "ERROR: Failed to install Google Chrome - $($_.Exception.Message)"
            exit 1
        }

        # Install Notepad++
        try {
            Start-Process -FilePath "choco" -ArgumentList "install notepadplusplus -y --ignore-checksums" -Wait -NoNewWindow -PassThru
        } catch {
            Write-EC2Log "ERROR: Failed to install Notepad++ - $($_.Exception.Message)"
            exit 1
        }

        # Install Visual Studio Code
        try {
            Start-Process -FilePath "choco" -ArgumentList "install vscode -y --ignore-checksums" -Wait -NoNewWindow -PassThru
        } catch {
            Write-EC2Log "ERROR: Failed to install VSCode - $($_.Exception.Message)"
            exit 1
        }

        # Configure auto-login and disable Ctrl+Alt+Del
        try {
            $username = "Administrator"
            $password = "CloudRAM123!"
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "AutoAdminLogon" -Value "1"
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "DefaultUserName" -Value $username
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "DefaultPassword" -Value $password
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "ForceAutoLogon" -Value "1"
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "DisableCAD" -Value 1
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "PromptOnSecureDesktop" -Value 0
            Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" -Name "NoLockScreen" -Value 1
            powercfg /change monitor-timeout-ac 0
            powercfg /change monitor-timeout-dc 0
            powercfg /change standby-timeout-ac 0
            powercfg /change standby-timeout-dc 0
            powercfg /change hibernate-timeout-ac 0
            powercfg /change hibernate-timeout-dc 0
            Write-EC2Log "Auto-login and power settings configured"
            Register-ResumeTask
            Set-ScriptState "POST_REBOOT_1"
            Restart-Computer -Force
        } catch {
            Write-EC2Log "ERROR: Failed to configure auto-login or power settings - $($_.Exception.Message)"
            exit 1
        }
    }

    "POST_REBOOT_1" {
        # Configure UltraVNC
        try {
            $ultravncIniPath = "C:\Program Files\uvnc bvba\UltraVNC\ultravnc.ini"
            if (-not (Test-Path $ultravncIniPath)) {
                $ultravncIniPath = "C:\Program Files\UltraVNC\ultravnc.ini"
            }
            $ultravncConfig = @"
[ultravnc]
passwd=
passwd2=
[admin]
UseRegistry=0
MSLogonRequired=0
NewMSLogon=0
DebugMode=0
Avilog=0
path=C:\Program Files\UltraVNC
accept_reject_mesg=
DebugLevel=0
DisableTrayIcon=0
rdpmode=0
LoopbackOnly=0
UseDSMPlugin=0
AllowLoopback=1
AuthRequired=0
ConnectPriority=0
DSMPlugin=
AuthHosts=
AllowShutdown=1
AllowProperties=1
AllowEditClients=1
[poll]
TurboMode=1
PollUnderCursor=0
PollFullScreen=1
OnlyPollConsole=0
OnlyPollOnEvent=0
MaxCpu=40
EnableDriver=0
EnableHook=1
EnableVirtual=0
SingleWindow=0
SingleApplicationName=
"@
            $ultravncConfig | Out-File -FilePath $ultravncIniPath -Encoding ASCII -Force
            $winvncPath = "C:\Program Files\uvnc bvba\UltraVNC\winvnc.exe"
            if (-not (Test-Path $winvncPath)) {
                $winvncPath = "C:\Program Files\UltraVNC\winvnc.exe"
            }
            Start-Process -FilePath $winvncPath -ArgumentList "-install" -NoNewWindow -Wait
            Start-Service -Name "uvnc_service" -ErrorAction Stop
        } catch {
            Write-EC2Log "ERROR: Failed to configure UltraVNC - $($_.Exception.Message)"
            exit 1
        }

        # Configure firewall
        try {
            New-NetFirewallRule -DisplayName "Allow VNC (TCP 5900)" -Direction Inbound -Protocol TCP -LocalPort 5900 -Action Allow -Enabled True -ErrorAction Stop
            New-NetFirewallRule -DisplayName "Allow noVNC (TCP 8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Enabled True -ErrorAction Stop
            New-NetFirewallRule -DisplayName "Allow Flask (TCP 5000)" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Enabled True -ErrorAction Stop
            New-NetFirewallRule -DisplayName "Allow RDP (TCP 3389)" -Direction Inbound -Protocol TCP -LocalPort 3389 -Action Allow -Enabled True -ErrorAction Stop
        } catch {
            Write-EC2Log "ERROR: Failed to configure firewall - $($_.Exception.Message)"
            exit 1
        }

        # Download and configure noVNC
        try {
            Invoke-WebRequest -Uri "https://github.com/novnc/noVNC/archive/refs/heads/master.zip" -OutFile "C:\CloudRAM\noVNC.zip"
            Expand-Archive -Path "C:\CloudRAM\noVNC.zip" -DestinationPath "C:\CloudRAM\noVNC" -Force
            $indexPath = "C:\CloudRAM\noVNC\noVNC-master\index.html"
            $indexContent = @"
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url=vnc.html?autoconnect=true&reconnect=true&reconnect_delay=5000&host=127.0.0.1&port=8080">
</head>
<body>
    <p>Redirecting to VNC client...</p>
</body>
</html>
"@
            $indexContent | Set-Content -Path $indexPath -Force
        } catch {
            Write-EC2Log "ERROR: Failed to setup noVNC - $($_.Exception.Message)"
            exit 1
        }

        # Download Flask server script from S3
        try {
            $s3Url = "https://cloud-ram-scripts.s3.us-east-1.amazonaws.com/vm_server.py"
            Invoke-WebRequest -Uri $s3Url -OutFile "C:\CloudRAM\vm_server.py" -ErrorAction Stop
        } catch {
            Write-EC2Log "ERROR: Failed to download vm_server.py from S3 - $($_.Exception.Message)"
            exit 1
        }

        # Create Websockify script
        $websockifyScript = @"
Get-Process | Where-Object { `$_.CommandLine -like "*websockify*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "python" -ArgumentList "-m websockify 8080 localhost:5900 --web C:\CloudRAM\noVNC\noVNC-master" -NoNewWindow
"@
        $websockifyScript | Out-File -FilePath "C:\CloudRAM\run-websockify.ps1" -Encoding ASCII -Force

        # Create startup script
        $startupScript = @"
# Wait for VM/network to stabilize
Start-Sleep -Seconds 30

# Kill existing UltraVNC process (ignore error if not running)
taskkill /F /IM winvnc.exe 2>$null

# Start UltraVNC server
Start-Process -FilePath "C:\Program Files\uvnc bvba\UltraVNC\winvnc.exe" -ArgumentList "-run" -NoNewWindow

# Start Websockify bridge in a new PowerShell process
Start-Process -FilePath "powershell" -ArgumentList "-ExecutionPolicy Bypass -File C:\CloudRAM\run-websockify.ps1" -NoNewWindow

# Ensure logs directory exists before logging
if (!(Test-Path "C:\CloudRAM\logs")) {
    New-Item -ItemType Directory -Path "C:\CloudRAM\logs" | Out-Null
}

python C:\CloudRAM\vm_server.py
"@
        $startupScript | Out-File -FilePath "C:\CloudRAM\startup_services.ps1" -Encoding ASCII -Force

        # Create scheduled task for services
        try {
            $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\CloudRAM\startup_services.ps1"
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -TaskName "CloudRAM-Services" -Description "Start Cloud RAM VNC services" -Force
        } catch {
            Write-EC2Log "ERROR: Failed to create scheduled task for services - $($_.Exception.Message)"
            exit 1
        }

        # Start services now
        try {
            Start-Service -Name "uvnc_service" -ErrorAction Stop
            Start-Process -FilePath "powershell" -ArgumentList "-ExecutionPolicy Bypass -File C:\CloudRAM\run-websockify.ps1" -NoNewWindow
            Start-Process -FilePath "python" -ArgumentList "C:\CloudRAM\vm_server.py" -NoNewWindow
        } catch {
            Write-EC2Log "ERROR: Failed to start services - $($_.Exception.Message)"
            exit 1
        }

        # Finalize setup
        Set-ScriptState "COMPLETED"
        Write-EC2Log "Setup completed successfully"
        
        # Clean up resume task
        Unregister-ScheduledTask -TaskName "CloudRAM-ResumeScript" -Confirm:$false -ErrorAction SilentlyContinue
    }

    "COMPLETED" {
        Write-EC2Log "Script has already completed. No further action required."
    }

    default {
        Set-ScriptState "INITIAL"
    }
}
</powershell>