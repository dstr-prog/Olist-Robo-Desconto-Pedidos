@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_ROBO=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON_ROBO%" (
  echo ERRO: ambiente Python nao encontrado em:
  echo %PYTHON_ROBO%
  echo.
  echo Recrie o ambiente conforme a secao Instalacao do README.md.
  pause
  exit /b 1
)

echo Verificando conexao com o Chrome e a grid de Pedidos de venda...
"%PYTHON_ROBO%" "%~dp0desconto_pedidos_olist.py" --verificar
if errorlevel 1 (
  echo.
  echo A verificacao falhou. Confira a mensagem acima.
  pause
  exit /b 1
)

echo.
echo Informe o percentual de desconto a aplicar em cada pedido.
echo Exemplos: 10    10,5    10%%
echo Pedidos que ja tiverem desconto preenchido serao ignorados.
echo O Total da venda nao ficara abaixo de R$ 10,00.
echo.
set /p PERCENTUAL="Percentual: "
if "%PERCENTUAL%"=="" (
  echo Nenhum percentual informado. Encerrando.
  pause
  exit /b 1
)

echo.
echo ATENCAO: a proxima etapa edita os pedidos visiveis na tela, um a um.
choice /C SN /N /M "Deseja aplicar o desconto de %PERCENTUAL%%% ? [S/N] "
if errorlevel 2 exit /b 0

"%PYTHON_ROBO%" "%~dp0desconto_pedidos_olist.py" --percentual "%PERCENTUAL%"
set "RESULTADO=%ERRORLEVEL%"
echo.
if not "%RESULTADO%"=="0" echo O robo terminou com erro. Consulte a mensagem e a pasta logs.
pause
exit /b %RESULTADO%
