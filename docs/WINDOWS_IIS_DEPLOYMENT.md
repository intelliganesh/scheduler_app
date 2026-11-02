# Windows and IIS Deployment Guide

This guide deploys Scheduler App on a Windows laptop or server using:

- IIS to serve the compiled React frontend.
- IIS URL Rewrite and Application Request Routing (ARR) to proxy API requests.
- Uvicorn to run the FastAPI backend on loopback port `8000`.
- WinSW to run Uvicorn as a Windows Service that starts with Windows.

The examples assume the application is installed at:

```text
C:\projects\scheduler_app
```

Change every path consistently if the application is installed elsewhere.

## 1. Deployment architecture

```text
Browser/LAN computer
        |
        | HTTP 8080
        v
IIS: SchedulerApp site
  |-- React static files from frontend\dist
  |-- /api/*    ----+
  |-- /health*  ----+--> 127.0.0.1:8000 --> FastAPI/Uvicorn
                                      |
                                      +--> SQL Server or MySQL
                                      +--> LDAP/Active Directory, when enabled
```

Do not create a second IIS site for the Python backend. IIS serves React and acts
as the public reverse proxy. The Windows Service runs FastAPI privately on
`127.0.0.1:8000`.

## 2. Port reference

| Port | Used by | Binding/exposure | Required |
| --- | --- | --- | --- |
| `8080/TCP` | IIS SchedulerApp site | `0.0.0.0` / LAN | Yes; allow inbound from the local subnet |
| `8000/TCP` | FastAPI/Uvicorn | `127.0.0.1` only | Yes; do not expose through Windows Firewall |
| `5173/TCP` | Vite development server | Development only | No in production |
| `1433/TCP` | Microsoft SQL Server | Database dependent | Only when using MSSQL |
| `3306/TCP` | MySQL | Database dependent | Only when using MySQL |
| `389/TCP` | LDAP with StartTLS | Directory dependent | Only when configured by IT |
| `636/TCP` | LDAPS | Directory dependent | Only when configured by IT |

The normal user-facing URLs are:

```text
Local:  http://localhost:8080
LAN:    http://<server-ip>:8080
```

The backend URL `http://127.0.0.1:8000` is for local diagnostics only.

## 3. Prerequisites

Install or confirm the following on the Windows host:

1. Windows 10, Windows 11, or Windows Server with administrator access.
2. Python 3.12, 64-bit.
3. Node.js 18 or newer with npm.
4. IIS and IIS Management Console.
5. [IIS URL Rewrite 2.1](https://www.iis.net/downloads/microsoft/url-rewrite).
6. [IIS Application Request Routing 3](https://www.iis.net/downloads/microsoft/application-request-routing).
7. Microsoft .NET Framework 4.6.1 or newer for `WinSW.NET461.exe`.
8. A reachable SQL Server or MySQL database.
9. Microsoft ODBC Driver 18 for SQL Server when `DB_DIALECT=mssql`.
10. A company network or VPN connection when LDAP/Active Directory is enabled.

Check Python and Node.js:

```powershell
py -3.12 --version
node --version
npm --version
```

Check the SQL Server ODBC driver:

```powershell
Get-OdbcDriver | Where-Object Name -Like "*ODBC Driver 18 for SQL Server*"
```

### Enable IIS

Open **Turn Windows features on or off** and enable:

```text
Internet Information Services
  Web Management Tools
    IIS Management Console
  World Wide Web Services
    Common HTTP Features
      Default Document
      HTTP Errors
      Static Content
```

Alternatively, from Administrator PowerShell:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole -All -NoRestart
Enable-WindowsOptionalFeature -Online -FeatureName IIS-ManagementConsole -All -NoRestart
```

Install URL Rewrite before ARR. ARR depends on URL Rewrite.

### Enable ARR proxying

After installing ARR:

1. Open **IIS Manager**.
2. Select the computer/server node, not the SchedulerApp site.
3. Open **Application Request Routing Cache**.
4. Select **Server Proxy Settings** in the Actions panel.
5. Select **Enable proxy**.
6. Click **Apply**.

Reverse proxy functionality is disabled until this setting is enabled.

## 4. Place the application on a local disk

Use a stable local path instead of Desktop, OneDrive, or a mapped network drive:

```text
C:\projects\scheduler_app
```

Confirm these folders exist:

```text
C:\projects\scheduler_app\backend
C:\projects\scheduler_app\frontend
C:\projects\scheduler_app\service
```

Avoid moving the application after installing the Windows Service. The current
service XML contains absolute paths.

## 5. Configure and prepare the backend

Open PowerShell:

```powershell
Set-Location "C:\projects\scheduler_app\backend"
```

### Create the Python virtual environment

Create one environment named `.venv`:

```powershell
py -3.12 -m venv .venv
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Validate important imports:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn, sqlalchemy, apscheduler; print('Backend dependencies OK')"
```

### Create `backend\.env`

Create the local configuration from the example when `.env` does not already
exist:

```powershell
Copy-Item .env.example .env
notepad .env
```

At minimum, configure:

```env
DB_DIALECT=mssql
DB_HOST=database-host
DB_PORT=1433
DB_NAME=generate_report
DB_USER=application-login
DB_PASSWORD=replace-with-a-real-secret
MSSQL_DRIVER=ODBC Driver 18 for SQL Server
MSSQL_TRUST_SERVER_CERTIFICATE=false

JWT_SECRET_KEY=replace-with-a-random-value-of-at-least-32-characters
AUTH_MODE=ldap
```

Generate a suitable JWT secret:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `JWT_SECRET_KEY`. Never commit `backend\.env`.

For local testing only, `AUTH_MODE=mock` may be used. Do not deploy mock
authentication to a shared or production system.

### Apply database migrations

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Only run the demo seeder when the environment should contain the built-in sample
data:

```powershell
.\.venv\Scripts\python.exe seed.py
```

### Test the backend manually

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

In another PowerShell window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health"
Invoke-RestMethod "http://127.0.0.1:8000/health/database"
```

Both calls should succeed. Press `Ctrl+C` in the Uvicorn window before installing
or starting the Windows Service.

Use exactly one Uvicorn worker. APScheduler runs inside the backend process;
multiple workers would create multiple schedulers.

## 6. Build the React frontend

The production frontend uses same-origin requests. The current source setting is:

```javascript
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
```

If `frontend\.env` exists, ensure it does not contain a localhost API override.
Use an empty value or remove the variable:

```env
VITE_API_BASE_URL=
```

Build the frontend:

```powershell
Set-Location "C:\projects\scheduler_app\frontend"
npm ci
npm run build
```

Confirm the output and IIS configuration exist:

```powershell
Test-Path "C:\projects\scheduler_app\frontend\dist\index.html"
Test-Path "C:\projects\scheduler_app\frontend\dist\web.config"
```

Both commands must return `True`. `frontend\public\web.config` is copied into
`frontend\dist` by Vite. 

The deployed `web.config` performs two tasks:

1. Proxies `/api/*` and `/health*` to `http://127.0.0.1:8000`.
2. Rewrites non-file React routes to `/index.html`.

## 7. Create the IIS site

### Using IIS Manager

1. Open **IIS Manager** as Administrator.
2. Under **Application Pools**, select **Add Application Pool**.
3. Use these values:

   ```text
   Name: SchedulerApp
   .NET CLR version: No Managed Code
   Managed pipeline mode: Integrated
   Start application pool immediately: selected
   ```

4. Under **Sites**, select **Add Website**.
5. Use these values:

   ```text
   Site name: SchedulerApp
   Application pool: SchedulerApp
   Physical path: C:\projects\scheduler_app\frontend\dist
   Binding type: http
   IP address: All Unassigned
   Port: 8080
   Host name: empty
   Start Website immediately: selected
   ```

6. Select the site and verify that **Default Document** contains `index.html`.

### Grant IIS access to the frontend

From Administrator PowerShell:

```powershell
icacls "C:\projects\scheduler_app\frontend\dist" /grant "IIS AppPool\SchedulerApp:(OI)(CI)RX" /T
```

The IIS application-pool identity needs Read and Execute access. Deploying from a
local path also avoids common OneDrive traversal and encryption ACL problems.

### Start and test IIS

```powershell
Import-Module WebAdministration
Start-WebAppPool -Name "SchedulerApp"
Start-Website -Name "SchedulerApp"
Invoke-WebRequest "http://localhost:8080" -UseBasicParsing
```

If IIS reports that port `8080` is already in use, inspect the listener:

```powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
```

## 8. Install the FastAPI backend as a Windows Service

The repository uses [WinSW](https://github.com/winsw/winsw) to host Uvicorn as a
real Windows Service.

The service folder must contain two files with the same base name:

```text
C:\projects\scheduler_app\service\SchedulerAppBackend.exe
C:\projects\scheduler_app\service\SchedulerAppBackend.xml
```

### Download WinSW when the executable is missing

From Administrator PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path "C:\projects\scheduler_app\service"

Invoke-WebRequest `
  -Uri "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW.NET461.exe" `
  -OutFile "C:\projects\scheduler_app\service\SchedulerAppBackend.exe"
```

Verify the SHA-256 digest:

```powershell
(Get-FileHash "C:\projects\scheduler_app\service\SchedulerAppBackend.exe" -Algorithm SHA256).Hash
```

Expected value for `WinSW.NET461.exe` v2.12.0:

```text
B5066B7BBDFBA1293E5D15CDA3CAAEA88FBEAB35BD5B38C41C913D492AADFC4F
```

Do not install the binary if the hash differs.

### Review the service configuration

`service\SchedulerAppBackend.xml` should contain:

```xml
<service>
  <id>SchedulerAppBackend</id>
  <name>Scheduler App Backend</name>
  <description>FastAPI backend and report scheduler for Scheduler App</description>

  <executable>C:\projects\scheduler_app\backend\.venv\Scripts\python.exe</executable>
  <arguments>-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1</arguments>
  <workingdirectory>C:\projects\scheduler_app\backend</workingdirectory>

  <env name="PYTHONUNBUFFERED" value="1" />

  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>

  <stoptimeout>30 sec</stoptimeout>
  <onfailure action="restart" delay="10 sec" />
  <resetfailure>1 hour</resetfailure>

  <logpath>C:\projects\scheduler_app\logs\service</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
</service>
```

`Automatic (Delayed Start)` means Windows starts the service automatically after
essential operating-system and networking services. To start it without the
delay, change this before installation:

```xml
<delayedAutoStart>false</delayedAutoStart>
```

### Confirm port 8000 is free

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
```

Stop the manual Uvicorn console or disable the old Task Scheduler task if the
command returns a listener. Do not run the scheduled task and Windows Service at
the same time.

### Install and start the service

Open PowerShell as Administrator:

```powershell
Set-Location "C:\projects\scheduler_app\service"
.\SchedulerAppBackend.exe install
.\SchedulerAppBackend.exe start
```

Verify it:

```powershell
Get-Service SchedulerAppBackend
Get-NetTCPConnection -LocalPort 8000 -State Listen
Invoke-RestMethod "http://127.0.0.1:8000/health"
Invoke-RestMethod "http://localhost:8080/health"
```

Expected service status: `Running`.

### Service management commands

```powershell
Get-Service SchedulerAppBackend
Start-Service SchedulerAppBackend
Stop-Service SchedulerAppBackend
Restart-Service SchedulerAppBackend
```

To remove it:

```powershell
Set-Location "C:\projects\scheduler_app\service"
.\SchedulerAppBackend.exe stop
.\SchedulerAppBackend.exe uninstall
```

Uninstalling the service does not delete the application or its data.

## 9. Allow other computers on the local network

The backend remains private on port 8000. Only IIS port 8080 needs an inbound
firewall rule.

From Administrator PowerShell:

```powershell
New-NetFirewallRule `
  -DisplayName "SchedulerApp IIS 8080" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8080 `
  -Profile Private,Public `
  -RemoteAddress LocalSubnet
```

Confirm the rule:

```powershell
Get-NetFirewallRule -DisplayName "SchedulerApp IIS 8080" |
  Format-List DisplayName,Enabled,Direction,Action,Profile
```

Find the host's IPv4 address:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred" }
```

For example, when the host IP is `10.0.0.36`, other computers connected to the
same permitted network use:

```text
http://10.0.0.36:8080
```

From another Windows computer:

```powershell
Test-NetConnection 10.0.0.36 -Port 8080
```

`TcpTestSucceeded` must be `True`.

If it remains `False` even though IIS works locally:

1. Confirm both computers are on the same LAN/VLAN.
2. Confirm the IIS binding uses **All Unassigned** and port `8080`.
3. Confirm the firewall rule covers the active Public or Private profile.
4. Check whether Wi-Fi client/AP isolation is enabled on the router.
5. Check for a corporate Group Policy that blocks local firewall rules. If
   `LocalFirewallRules` is reported as unavailable or GPO-only, an authorized IT
   administrator must permit inbound TCP 8080 from the local subnet.
6. Reserve the server's IP address in DHCP or assign an IT-approved static IP so
   the application URL does not change.

Do not add an inbound firewall rule for port 8000.

## 10. End-to-end verification

Run these checks on the host:

```powershell
Get-Service W3SVC,SchedulerAppBackend
Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-NetTCPConnection -LocalPort 8000 -State Listen

Invoke-WebRequest "http://localhost:8080" -UseBasicParsing
Invoke-RestMethod "http://localhost:8080/health"
Invoke-RestMethod "http://localhost:8080/health/database"
```

Then test from another computer:

```text
http://<server-ip>:8080
```

Finally, restart Windows and repeat the checks. The expected state after boot is:

- IIS site `SchedulerApp` is started.
- Windows Service `SchedulerAppBackend` is running.
- Port 8080 is owned by IIS/HTTP.sys.
- Port 8000 is owned by the service's Python/Uvicorn process.
- The root page, `/health`, and `/health/database` work through IIS.

## 11. Updating the deployment

### Backend update

From Administrator PowerShell:

```powershell
Stop-Service SchedulerAppBackend

Set-Location "C:\projects\scheduler_app\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head

Start-Service SchedulerAppBackend
Invoke-RestMethod "http://localhost:8080/health"
```

Back up the database and user-generated files before applying significant
application or schema updates.

### Frontend update

```powershell
Set-Location "C:\projects\scheduler_app\frontend"
npm ci
npm run build
Restart-WebAppPool -Name "SchedulerApp"
Invoke-WebRequest "http://localhost:8080" -UseBasicParsing
```

Changing service paths, the service name, or the service account may require a
service refresh or reinstall. Ordinary backend code changes require only a
service restart.

## 12. Logs and troubleshooting

### Log locations

```text
C:\projects\scheduler_app\logs\service
C:\projects\scheduler_app\logs\backend
C:\projects\scheduler_app\logs\jobs
C:\inetpub\logs\LogFiles
```

WinSW service logs normally include:

```text
SchedulerAppBackend.wrapper.log
SchedulerAppBackend.out.log
SchedulerAppBackend.err.log
```

### Common problems

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| WinError 10048 on port 8000 | Manual Uvicorn or another service already uses port 8000 | Stop the old process/task before starting the service |
| Service starts and immediately stops | Invalid `.env`, database failure, broken virtual environment, or insecure JWT secret | Check WinSW `.err.log`, `.wrapper.log`, and Windows Event Viewer |
| IIS `401.3` | IIS application-pool identity cannot read `frontend\dist` | Apply the documented `icacls` permission and use a local non-OneDrive path |
| IIS `500.19` mentioning rewrite | URL Rewrite missing or `web.config` invalid | Install URL Rewrite 2.1 and confirm `dist\web.config` |
| IIS `502.3` or API routes fail | Backend service is stopped or ARR proxy is disabled | Start `SchedulerAppBackend` and enable ARR proxy at the server node |
| React page opens but API calls target remote user's localhost | Frontend was built with a localhost API override | Set `VITE_API_BASE_URL=` and rebuild |
| `TcpTestSucceeded: False` from another computer | Firewall profile/GPO, IIS binding, or Wi-Fi isolation | Follow the LAN checklist in section 9 |
| Old frontend remains after rebuild | Browser or IIS cache | Hard refresh the browser and recycle the application pool |
| Service cannot access a network share | LocalSystem has no mapped user drives | Use UNC paths and an approved service account with explicit permissions |

Inspect a port owner when necessary:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess

Get-Process -Id <OwningProcess>
```

## 13. Security checklist

- Keep `backend\.env`, database passwords, LDAP credentials, and JWT secrets out
  of Git.
- Keep Uvicorn bound to `127.0.0.1`, not `0.0.0.0`.
- Expose only IIS port 8080 to the required local subnet.
- Use a trusted TLS certificate and an HTTPS IIS binding for production or any
  network carrying sensitive data.
- Use LDAPS or LDAP StartTLS with certificate validation when LDAP is enabled.
- Use a database login with only the permissions required by the application.
- Do not run mock authentication in production.
- Keep Python, Node.js, the ODBC driver, IIS modules, and Windows security updates
  maintained through the organization's approved process.
- Back up the database, generated reports, uploads, environment file, and any
  deployment-specific configuration.

## 14. Official references

- [Microsoft IIS URL Rewrite](https://www.iis.net/downloads/microsoft/url-rewrite)
- [Microsoft IIS Application Request Routing](https://www.iis.net/downloads/microsoft/application-request-routing)
- [Microsoft reverse proxy walkthrough for URL Rewrite and ARR](https://learn.microsoft.com/en-us/iis/extensions/url-rewrite-module/reverse-proxy-with-url-rewrite-v2-and-application-request-routing)
- [WinSW repository and documentation](https://github.com/winsw/winsw)
- [WinSW v2.12.0 release](https://github.com/winsw/winsw/releases/tag/v2.12.0)

