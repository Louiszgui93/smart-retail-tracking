"""
Configuração do Banco de Dados MariaDB
"""

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # ALTERE PARA SUA SENHA!
    'database': 'person_tracking_db',
    'port': 3306,
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': False  # Controlamos manualmente as transações
}

# Configurações de Reidentificação
REID_CONFIG = {
    'similarity_threshold': 0.65,   # Threshold para considerar mesma pessoa
    'cache_ttl_minutes': 30,        # Tempo que mantém pessoas no cache
    'save_snapshots': True,         # Salvar prints das pessoas
    'snapshot_quality': 0.7,        # Qualidade mínima para salvar snapshot
    'min_detection_confidence': 0.5, # Confiança mínima da detecção
    'features': {                    # Peso das features no cálculo de similaridade
        'height': 0.3,
        'aspect_ratio': 0.2,
        'histogram': 0.4,
        'color': 0.1
    }
}