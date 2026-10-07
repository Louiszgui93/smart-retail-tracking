# 📸 IA Varejo - Sistema de Tracking com Reidentificação

Sistema inteligente de rastreamento e reidentificação de pessoas em ambientes de varejo usando YOLO v8, BoT-SORT tracking e Google Vision API.

## 🚀 Funcionalidades

- ✅ Detecção de pessoas em tempo real (YOLO v8)
- ✅ Tracking persistente com BoT-SORT
- ✅ Reidentificação de pessoas com banco de dados
- ✅ Análise de zonas e heatmap
- ✅ Sistema de alertas comportamentais
- ✅ Integração com Google Vision API (emoções e atributos)
- ✅ Dashboard web em tempo real
- ✅ Suporte a streams RTSP

## 📋 Pré-requisitos

- Python 3.10 ou superior
- MariaDB/MySQL
- Câmera IP com suporte RTSP
- (Opcional) Conta Google Cloud para Vision API

## 🔧 Instalação

### 1. Clonar o repositório
```bash
git clone <seu-repositorio>
cd iavarejo_atualizado
```

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar Banco de Dados

#### Criar banco de dados:
```sql
CREATE DATABASE person_tracking_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

#### Configurar credenciais:
Edite o arquivo `config/db_config.py` ou use variáveis de ambiente:
```bash
export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=sua_senha_aqui
export DB_NAME=person_tracking_db
export DB_PORT=3306
```

### 4. Configurar Google Vision API (Opcional)

Se você deseja usar análise de emoções e atributos faciais:

1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com)
2. Ative a Vision API
3. Crie uma Service Account e baixe o JSON de credenciais
4. Copie o arquivo de credenciais:
```bash
cp seu_arquivo_baixado.json config/vision_service_account.json
```

**Nota:** O sistema funciona perfeitamente sem a Vision API. Ela é opcional para análises avançadas.

### 5. Configurar Câmera RTSP

Edite o arquivo `main.py` e configure sua URL RTSP:
```python
RTSP_URL = "rtsp://usuario:senha@ip_camera:porta/caminho"
```

Ou use variáveis de ambiente:
```bash
export RTSP_URL="rtsp://usuario:senha@ip_camera:porta/caminho"
```

### 6. Configurar Zonas

Edite o arquivo `config/zones.json` para definir as zonas do seu estabelecimento:
```json
{
  "entrada_saida": {
    "points": [[100, 100], [200, 100], [200, 200], [100, 200]],
    "color": [0, 255, 0]
  },
  "ilhas_promocionais": {
    "points": [[300, 300], [400, 300], [400, 400], [300, 400]],
    "color": [255, 0, 0]
  }
}
```

## 🎯 Uso

### Iniciar o sistema de tracking:
```bash
python main.py
```

### Iniciar o dashboard web:
```bash
python dashboard.py
```

Acesse: `http://localhost:5000`

## 📁 Estrutura do Projeto

```
iavarejo_atualizado/
├── main.py                 # Script principal de tracking
├── dashboard.py            # Dashboard web
├── config/                 # Configurações
│   ├── db_config.py       # Config do banco de dados
│   ├── zones.json         # Definição de zonas
│   └── vision_service_account.json  # Credenciais Google Vision (não incluído)
├── detection/             # Detecção e tracking
│   ├── detector.py
│   └── tracker.py
├── reid/                  # Reidentificação
│   ├── db_manager.py
│   └── id_manager.py
├── analytics/             # Análises
│   ├── zones.py
│   ├── heatmap.py
│   └── metrics.py
├── alerts/               # Sistema de alertas
│   ├── behavior.py
│   └── rules.py
├── api/                  # Integrações externas
│   └── vision_integration.py
├── capture/              # Captura de vídeo
│   └── rtsp_reader.py
├── templates/            # Templates HTML
│   └── dashboard.html
├── logs/                 # Logs do sistema
├── snapshots/            # Capturas de pessoas
└── models/               # Modelos YOLO
    └── yolov8n.pt
```

## ⚙️ Configurações Avançadas

### Ajustar threshold de reidentificação:
```python
# Em main.py
person_db.similarity_threshold = 0.55  # Padrão: 0.55 (0-1)
```

### Ajustar tempo de alerta de zona:
```python
# Em main.py
ZONE_ALERT_THRESHOLD = 60  # segundos
```

### Ajustar confiança de detecção:
```python
# Em detection/detector.py
conf=0.4  # Padrão: 0.4 (0-1)
```

## 🔐 Segurança

⚠️ **IMPORTANTE:**
- Nunca commite credenciais (senhas, tokens, etc) no Git
- Use variáveis de ambiente para dados sensíveis
- Adicione `vision_service_account.json` ao `.gitignore`
- Mantenha as senhas do banco seguras

## 📊 Banco de Dados

O sistema cria automaticamente as seguintes tabelas:
- `persons` - Pessoas detectadas e reidentificadas
- `detections` - Histórico de detecções
- `person_features` - Features para reidentificação
- `alert_snapshots` - Capturas de alertas

## 🐛 Troubleshooting

### Erro de conexão com banco de dados:
- Verifique se o MariaDB está rodando
- Confirme as credenciais em `config/db_config.py`
- Verifique se o banco foi criado

### Erro ao conectar com câmera RTSP:
- Teste a URL RTSP em um player (VLC)
- Verifique firewall e rede
- Confirme usuário e senha

### Vision API não funciona:
- Verifique se as credenciais estão corretas
- Confirme que a API está ativada no Google Cloud
- O sistema funciona sem ela - é opcional

### FPS baixo:
- Reduza a resolução da câmera
- Ajuste `conf` em detector.py para valor maior
- Use GPU se disponível

## 📝 Logs

Os logs são salvos em `logs/tracking_YYYYMMDD_HHMMSS.log`

Para visualizar logs em tempo real:
```bash
tail -f logs/tracking_*.log
```

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se livre para:
- Reportar bugs
- Sugerir novas funcionalidades
- Enviar pull requests

## 📄 Licença

[Adicione sua licença aqui]

## 👥 Autores

Luiz Guilherme

## 📧 Suporte

Para dúvidas e suporte, abra uma issue no repositório.

---

**Desenvolvido com ❤️ para ambientes de varejo inteligentes**
