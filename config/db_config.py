"""
Configuração do Banco de Dados MariaDB
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuração do banco usando variáveis de ambiente
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),  # OBRIGATÓRIO: Configure via variável de ambiente (.env)
    'database': os.getenv('DB_NAME', 'person_tracking_db'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': False,  # Controlamos manualmente as transações
    
    # CORREÇÃO: Forçar autenticação nativa do MySQL
    # Resolve erro: "Authentication plugin 'auth_gssapi_client' not configured"
    'auth_plugin_map': {
        'auth_gssapi_client': 'mysql_native_password'
    },
    'connect_timeout': 10,  # Timeout de conexão em segundos
}

# Validação de segurança - avisar se senha não foi configurada
if not DB_CONFIG['password']:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("=" * 60)
    logger.warning("⚠️  ATENÇÃO: Senha do banco de dados não configurada!")
    logger.warning("   Configure a variável de ambiente DB_PASSWORD")
    logger.warning("   Exemplo: export DB_PASSWORD='sua_senha_aqui'")
    logger.warning("   Ou adicione no arquivo .env: DB_PASSWORD=sua_senha")
    logger.warning("=" * 60)

# Configurações de Reidentificação
REID_CONFIG = {
    'similarity_threshold': float(os.getenv('SIMILARITY_THRESHOLD', 0.65)),
    'cache_ttl_minutes': int(os.getenv('CACHE_TTL_MINUTES', 30)),
    'save_snapshots': os.getenv('SAVE_SNAPSHOTS', 'True').lower() == 'true',
    'snapshot_quality': float(os.getenv('SNAPSHOT_QUALITY', 0.7)),
    'min_detection_confidence': float(os.getenv('MIN_DETECTION_CONFIDENCE', 0.5)),
    'features': {  # Peso das features no cálculo de similaridade
        'height': 0.3,
        'aspect_ratio': 0.2,
        'histogram': 0.4,
        'color': 0.1
    }
}

import queue
import logging
import pymysql

logger = logging.getLogger(__name__)

class DatabaseConnectionPool:
    def __init__(self, db_config, max_connections=5):
        self.db_config = db_config
        self.max_connections = max_connections
        self.pool = queue.Queue(max_connections)
        for _ in range(max_connections):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)
        logger.info(f"Pool de conexões de banco de dados inicializado com {self.pool.qsize()} conexões.")

    def _create_connection(self):
        try:
            return pymysql.connect(
                host=self.db_config['host'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                port=self.db_config.get('port', 3306),
                charset=self.db_config.get('charset', 'utf8mb4'),
                cursorclass=pymysql.cursors.DictCursor,
                auth_plugin_map=self.db_config.get('auth_plugin_map'),
                connect_timeout=self.db_config.get('connect_timeout', 10)
            )
        except Exception as e:
            logger.error(f"Erro ao criar nova conexão de banco: {e}")
            return None

    def get_connection(self):
        try:
            conn = self.pool.get(timeout=3)
            # Validar se a conexão ainda está viva
            conn.ping(reconnect=True)
            return conn
        except queue.Empty:
            logger.warning("Pool de conexões esgotado. Criando conexão sob demanda.")
            return self._create_connection()
        except Exception as e:
            logger.error(f"Erro ao obter conexão do pool: {e}")
            return self._create_connection()

    def release_connection(self, conn):
        if conn is None:
            return
        if self.pool.qsize() < self.max_connections:
            try:
                self.pool.put_nowait(conn)
            except queue.Full:
                conn.close()
        else:
            conn.close()

    def close_all(self):
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass
        logger.info("Pool de conexões fechado.")

# Pool global de conexões
DB_POOL = DatabaseConnectionPool(DB_CONFIG)