import cv2
import time
import logging
import threading

logger = logging.getLogger(__name__)


class RTSPReader:
    """
    Leitor de stream RTSP assíncrono com thread em segundo plano,
    reconexão automática e eliminação de lag de buffer.
    """
    
    def __init__(self, rtsp_url, reconnect_attempts=3, reconnect_delay=2):
        """
        Inicializa o leitor RTSP.
        
        Args:
            rtsp_url: URL do stream RTSP
            reconnect_attempts: Número de tentativas de reconexão (padrão: 3)
            reconnect_delay: Delay entre tentativas em segundos (padrão: 2)
        """
        self.rtsp_url = rtsp_url
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.cap = None
        self.is_connected = False
        self.last_reconnect_time = 0
        self.failed_reads = 0
        self.max_failed_reads = 5  # Número de leituras falhadas antes de reconectar
        
        # Variáveis de controle de thread
        self.frame = None
        self.frame_id = 0
        self.stopped = False
        self.lock = threading.Lock()
        self.thread = None
        
        # Conectar inicialmente
        self._connect()
        
        # Iniciar thread se conectado
        if self.is_connected:
            self.start()
            
    def _connect(self):
        """Estabelece conexão com o stream RTSP"""
        try:
            logger.info(f"[RTSP] Conectando ao stream: {self._sanitize_url(self.rtsp_url)}")
            
            self.cap = cv2.VideoCapture(self.rtsp_url)
            
            # Configurar buffer para reduzir latência
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if self.cap.isOpened():
                self.is_connected = True
                self.failed_reads = 0
                logger.info("[RTSP] ✅ Conexão estabelecida com sucesso")
                
                # Log de informações do stream
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(self.cap.get(cv2.CAP_PROP_FPS))
                logger.info(f"[RTSP] Stream: {width}x{height} @ {fps} FPS")
                
                return True
            else:
                self.is_connected = False
                logger.error("[RTSP] ❌ Falha ao abrir stream")
                return False
                
        except Exception as e:
            self.is_connected = False
            logger.error(f"[RTSP] ❌ Erro ao conectar: {e}")
            return False
            
    def start(self):
        """Inicia a thread de leitura contínua"""
        self.stopped = False
        self.thread = threading.Thread(target=self._update, name="RTSPReaderThread", daemon=True)
        self.thread.start()
        logger.info("[RTSP] Thread de captura iniciada em segundo plano")
        
    def _update(self):
        """Método de loop rodando na thread secundária"""
        while not self.stopped:
            if not self.is_connected:
                # Tentar reconectar na própria thread se perdeu conexão
                if not self._reconnect():
                    time.sleep(self.reconnect_delay)
                    continue
            
            try:
                ret, frame = self.cap.read()
                
                if not ret or frame is None:
                    self.failed_reads += 1
                    logger.debug(f"[RTSP] Falha na leitura ({self.failed_reads}/{self.max_failed_reads})")
                    
                    # Se muitas leituras falharam, forçar reconexão
                    if self.failed_reads >= self.max_failed_reads:
                        logger.warning("[RTSP] ⚠️  Muitas falhas de leitura, forçando reconexão...")
                        self.is_connected = False
                        self.failed_reads = 0
                    continue
                
                # Leitura bem-sucedida, atualizar frame com lock
                self.failed_reads = 0
                with self.lock:
                    self.frame = frame.copy()  # Copia o frame para evitar concorrência de memória
                    self.frame_id += 1
                    
            except Exception as e:
                logger.error(f"[RTSP] Erro ao ler frame na thread: {e}")
                self.is_connected = False
                time.sleep(0.1)
                
    def _reconnect(self):
        """Tenta reconectar ao stream RTSP"""
        current_time = time.time()
        
        # Evitar reconexões muito frequentes
        if current_time - self.last_reconnect_time < self.reconnect_delay:
            return False
        
        self.last_reconnect_time = current_time
        logger.warning("[RTSP] ⚠️  Tentando reconectar na thread...")
        
        # Liberar conexão antiga
        if self.cap is not None:
            try:
                self.cap.release()
            except:
                pass
        
        # Tentar reconectar múltiplas vezes
        for attempt in range(1, self.reconnect_attempts + 1):
            logger.info(f"[RTSP] Tentativa {attempt}/{self.reconnect_attempts}")
            
            if self._connect():
                return True
            
            if attempt < self.reconnect_attempts:
                time.sleep(self.reconnect_delay)
        
        logger.error(f"[RTSP] ❌ Falha de reconexão após {self.reconnect_attempts} tentativas")
        return False
        
    def read(self):
        """
        Retorna o frame mais recente capturado pela thread de segundo plano.
        
        Returns:
            frame: Frame capturado ou None se falhou ou ainda não há frames
        """
        with self.lock:
            # Se a thread parou ou não foi criada (ex: falhou ao conectar na inicialização),
            # e a conexão agora está de pé, iniciá-la.
            if not self.is_connected and (self.thread is None or not self.thread.is_alive()):
                self._reconnect()
                if self.is_connected:
                    self.start()
            return self.frame
            
    def release(self):
        """Para a thread de leitura e libera recursos"""
        self.stopped = True
        if self.thread is not None:
            self.thread.join(timeout=2)
            
        try:
            if self.cap is not None:
                self.cap.release()
                logger.info("[RTSP] Conexão liberada")
                self.is_connected = False
        except Exception as e:
            logger.error(f"[RTSP] Erro ao liberar conexão: {e}")
            
    def is_opened(self):
        """Verifica se a conexão está aberta"""
        return self.is_connected and self.cap is not None and self.cap.isOpened()
        
    def _sanitize_url(self, url):
        """Remove credenciais da URL para logging seguro"""
        try:
            import re
            pattern = r'(rtsp://)[^:]+:[^@]+(@)'
            sanitized = re.sub(pattern, r'\1***:***\2', url)
            return sanitized
        except:
            return "rtsp://***"
            
    def get_stats(self):
        """Retorna estatísticas da conexão"""
        return {
            'connected': self.is_connected,
            'failed_reads': self.failed_reads,
            'last_reconnect': self.last_reconnect_time
        }
