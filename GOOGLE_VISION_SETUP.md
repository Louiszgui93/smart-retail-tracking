# Configuração da Google Cloud Vision API

Para que a integração com a Google Cloud Vision API funcione corretamente, você precisa seguir estes passos:

## 1. Criar um Projeto no Google Cloud
1. Vá para o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto ou selecione um existente.

## 2. Ativar a Vision API
1. No menu lateral, vá em **APIs e Serviços** > **Biblioteca**.
2. Procure por **Cloud Vision API** e clique em **Ativar**.

## 3. Criar uma Conta de Serviço e Chave JSON
1. Vá em **IAM e Administrador** > **Contas de Serviço**.
2. Clique em **Criar Conta de Serviço**.
3. Dê um nome e conceda o papel de **Usuário da Cloud Vision API**.
4. Após criar, clique na conta, vá na aba **Chaves** > **Adicionar Chave** > **Criar nova chave**.
5. Selecione o formato **JSON** e baixe o arquivo.

## 4. Configurar a Variável de Ambiente
No seu terminal ou no arquivo onde você executa o projeto, configure o caminho para o arquivo JSON baixado:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/caminho/para/seu/arquivo-de-chave.json"
```

## O que foi implementado:
- **`api/vision_integration.py`**: Novo módulo que encapsula as chamadas à API.
- **Análise de Emoções**: Detecta alegria, tristeza, raiva e surpresa.
- **Análise de Atributos**: Detecta uso de acessórios de cabeça (headwear), se a imagem está borrada ou subexposta.
- **Detecção de Objetos**: Permite identificar itens específicos no ambiente de varejo.
- **Integração no `main.py`**: O sistema agora realiza uma análise via Vision API a cada 100 frames para as pessoas detectadas.
