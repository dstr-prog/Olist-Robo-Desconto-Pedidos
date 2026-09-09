@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================
echo  Robo Olist - Desconto em Pedidos
echo  Instalacao do ambiente
echo ============================================
echo.
echo Esta etapa precisa de internet (PyPI / Playwright).
echo.

REM --- Python 3.10+ -------------------------------------------------------
set "PYTHON="

where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%I"
)

if not defined PYTHON (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%I"
  )
)

if not defined PYTHON (
  echo ERRO: Python 3 nao encontrado no PATH.
  echo.
  echo Instale Python 3.10 ou superior:
  echo   https://www.python.org/downloads/windows/
  echo Marque a opcao "Add python.exe to PATH" no instalador.
  echo Depois rode este install.bat de novo.
  echo.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)

echo Python encontrado: %PYTHON%
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo.
  echo ERRO: e necessario Python 3.10 ou superior.
  "%PYTHON%" -c "import sys; print('Versao atual:', sys.version)"
  pause
  exit /b 1
)

REM --- Chrome (obrigatorio para rodar; a instalacao segue mesmo assim) ----
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if "%CHROME%"=="" (
  echo AVISO: Google Chrome nao foi encontrado.
  echo O robo usa o Chrome ja aberto com depuracao. Instale o Chrome antes de executar.
  echo.
) else (
  echo Chrome encontrado: %CHROME%
)
echo.

REM --- Ambiente virtual ---------------------------------------------------
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Criando ambiente virtual em .venv ...
  "%PYTHON%" -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo ERRO: falha ao criar o ambiente virtual.
    pause
    exit /b 1
  )
) else (
  echo Ambiente virtual ja existe. Atualizando pacotes...
)

set "PYTHON_ROBO=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_ROBO%" (
  echo ERRO: python do ambiente nao encontrado em:
  echo %PYTHON_ROBO%
  pause
  exit /b 1
)

echo.
echo Instalando dependencias ^(Playwright^)...
"%PYTHON_ROBO%" -m pip install --upgrade pip
if errorlevel 1 (
  echo ERRO: falha ao atualizar o pip. Verifique a internet.
  pause
  exit /b 1
)

"%PYTHON_ROBO%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo ERRO: falha ao instalar requirements.txt. Verifique a internet.
  pause
  exit /b 1
)

echo.
echo Baixando suporte interno do Playwright...
"%PYTHON_ROBO%" -m playwright install chromium
if errorlevel 1 (
  echo ERRO: falha no playwright install chromium. Verifique a internet.
  pause
  exit /b 1
)

echo.
echo ============================================
echo  Instalacao concluida.
echo ============================================
echo.
echo Como usar:
echo   1. Feche todo o Chrome
echo   2. Rode iniciar_chrome_olist.bat  ^(login no Olist + filtro dos pedidos^)
echo   3. Rode executar_robo.bat         ^(informa o percentual e confirma com S^)
echo.
echo Se o Chrome ja estiver aberto pelo robo de exclusao ^(porta 9222^),
echo pule o passo 2 e va direto ao executar_robo.bat.
echo.
pause
exit /b 0
