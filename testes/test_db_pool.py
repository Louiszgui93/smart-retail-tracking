import sys
import os
import threading
import time
import logging

# Adicionar caminho do projeto para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.db_config import DB_POOL, DB_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_db_pool")


def worker(worker_id):
    logger.info(f"Worker {worker_id} iniciando...")
    conn = DB_POOL.get_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 AS val")
                res = cursor.fetchone()
                logger.info(f"Worker {worker_id} obteve resultado: {res}")
            time.sleep(1)  # Simula trabalho com a conexão
        except Exception as e:
            logger.error(f"Worker {worker_id} falhou: {e}")
        finally:
            DB_POOL.release_connection(conn)
            logger.info(f"Worker {worker_id} liberou a conexão.")
    else:
        logger.error(f"Worker {worker_id} não conseguiu conexão!")


def test_concurrency():
    logger.info("Iniciando teste de concorrência com o Pool...")
    threads = []
    # Criar 8 workers (mais do que as 5 conexões padrão para testar fila e conexões sob demanda)
    for i in range(8):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    logger.info("Teste de concorrência concluído!")


if __name__ == "__main__":
    test_concurrency()
    DB_POOL.close_all()
