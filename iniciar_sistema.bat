@echo off
:: Configura o encoding para UTF-8 para evitar caracteres quebrados
chcp 65001 > nul

echo =========================================================
echo 📸 IA VAREJO - INICIANDO SISTEMA COM DEPENDÊNCIAS
echo =========================================================

:: Verifica se a pasta venv existe
if not exist venv (
    echo [ERRO] Pasta 'venv' do ambiente virtual não encontrada!
    echo Certifique-se de que rodou: python -m venv venv
    pause
    exit /b
)

echo [1/3] Ativando ambiente virtual (venv)...
call venv\Scripts\activate.bat

echo [2/3] Iniciando o Dashboard Web...
:: Inicia o dashboard em uma janela paralela minimizada ou em segundo plano
start "VisionTrack AI - Dashboard" /min venv\Scripts\python.exe dashboard.py

echo [3/3] Iniciando o Rastreamento de Vídeo (YOLO/ReID)...
:: Executa o loop de tracking na janela atual
venv\Scripts\python.exe main.py

pause
