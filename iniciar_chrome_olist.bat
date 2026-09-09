@echo off
REM Fecha o Chrome completamente ANTES de rodar este bat (senao a porta 9222 nao abre).
REM Se o Chrome ja estiver aberto pelo bat de exclusao de pedidos, NAO rode este arquivo:
REM use direto executar_robo.bat com a aba Pedidos de venda filtrada.

set PORT=9222

REM Reutiliza o perfil do robo de exclusao de pedidos (mesmo login), se existir.
set PROFILE_PEDIDOS=%~dp0..\robo-exclusao\chrome-perfil-olist
if exist "%PROFILE_PEDIDOS%" (
  set PROFILE=%PROFILE_PEDIDOS%
) else (
  set PROFILE=%~dp0chrome-perfil-olist
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

set CHROME=
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe

if "%CHROME%"=="" (
  echo Chrome nao encontrado.
  pause
  exit /b 1
)

echo Iniciando Chrome com depuracao na porta %PORT% ...
echo Perfil: %PROFILE%
echo.
echo 1^) Faca login no Olist ^(se ainda nao estiver logado neste perfil^)
echo 2^) Abra Pedidos de venda e aplique o filtro
echo 3^) Rode: executar_robo.bat
echo.

start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" "https://erp.olist.com/vendas#list"
