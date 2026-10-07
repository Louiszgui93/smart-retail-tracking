-- ============================================
-- SCRIPT COMPLETO CORRIGIDO PARA MariaDB
-- ============================================

SET FOREIGN_KEY_CHECKS = 0;

-- Criar banco
DROP DATABASE IF EXISTS person_tracking_db;
CREATE DATABASE person_tracking_db 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE person_tracking_db;

-- -----------------------------------------------------
-- TABELA: person_cache (Cache de Pessoas)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS person_cache (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    person_uuid CHAR(36) NOT NULL,
    external_id VARCHAR(100) DEFAULT NULL,
    first_seen TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    last_seen TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    embedding JSON,
    color_profile JSON,
    height_ratio DECIMAL(5,4) DEFAULT 0.0000,
    width_ratio DECIMAL(5,4) DEFAULT 0.0000,
    aspect_ratio DECIMAL(6,4) DEFAULT 0.0000,
    snapshot_path VARCHAR(512) DEFAULT NULL,
    snapshot_count SMALLINT UNSIGNED DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    confidence_score DECIMAL(3,2) DEFAULT 1.00,
    total_appearances INT UNSIGNED DEFAULT 0,
    total_duration_seconds INT UNSIGNED DEFAULT 0,
    requires_review TINYINT(1) DEFAULT 0,
    metadata JSON DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_person_uuid (person_uuid),
    KEY idx_external_id (external_id),
    KEY idx_is_active (is_active),
    KEY idx_last_seen (last_seen),
    KEY idx_confidence (confidence_score),
    KEY idx_requires_review (requires_review),
    CONSTRAINT chk_height_ratio CHECK (height_ratio >= 0 AND height_ratio <= 1),
    CONSTRAINT chk_width_ratio CHECK (width_ratio >= 0 AND width_ratio <= 1),
    CONSTRAINT chk_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Cache de pessoas para reidentificação';

-- -----------------------------------------------------
-- TABELA: person_occurrences (VERSÃO FINAL FUNCIONAL)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS person_occurrences (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    person_uuid CHAR(36) NOT NULL,
    camera_id VARCHAR(50) NOT NULL,
    detection_time TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    detection_date DATE NOT NULL, -- Coluna regular para particionamento
    bbox JSON NOT NULL,
    frame_width SMALLINT UNSIGNED DEFAULT 0,
    frame_height SMALLINT UNSIGNED DEFAULT 0,
    detection_confidence DECIMAL(4,3) DEFAULT 1.000,
    match_confidence DECIMAL(4,3) DEFAULT 1.000,
    is_reidentification TINYINT(1) DEFAULT 0,
    notes TEXT DEFAULT NULL,
    PRIMARY KEY (id, detection_date),
    KEY idx_person_uuid (person_uuid),
    KEY idx_camera_id (camera_id),
    KEY idx_detection_time (detection_time),
    KEY idx_camera_date (camera_id, detection_date),
    KEY idx_reidentification (is_reidentification),
    KEY idx_person_date (person_uuid, detection_date),
    CONSTRAINT chk_detection_confidence CHECK (detection_confidence >= 0 AND detection_confidence <= 1),
    CONSTRAINT chk_match_confidence CHECK (match_confidence >= 0 AND match_confidence <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Log de todas as detecções de pessoas'
PARTITION BY RANGE COLUMNS(detection_date) (
    PARTITION p2024_q1 VALUES LESS THAN ('2024-04-01'),
    PARTITION p2024_q2 VALUES LESS THAN ('2024-07-01'),
    PARTITION p2024_q3 VALUES LESS THAN ('2024-10-01'),
    PARTITION p2024_q4 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025_q1 VALUES LESS THAN ('2025-04-01'),
    PARTITION p2025_q2 VALUES LESS THAN ('2025-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

-- -----------------------------------------------------
-- TABELA: camera_sessions (VERSÃO CORRIGIDA)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS camera_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    session_uuid CHAR(36) NOT NULL,
    camera_id VARCHAR(50) NOT NULL,
    start_time TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    end_time TIMESTAMP(3) NULL DEFAULT NULL,
    
    -- Coluna regular que será calculada via trigger ou na aplicação
    duration_seconds INT UNSIGNED DEFAULT 0,
    
    connection_status ENUM('active', 'lost', 'restored', 'manual_stop') DEFAULT 'active',
    disconnect_reason VARCHAR(100) DEFAULT NULL,
    frames_processed INT UNSIGNED DEFAULT 0,
    persons_detected INT UNSIGNED DEFAULT 0,
    avg_processing_ms DECIMAL(8,2) DEFAULT 0.00,
    ip_address VARCHAR(45) DEFAULT NULL,
    camera_version VARCHAR(20) DEFAULT NULL,
    metadata JSON DEFAULT NULL,
    
    -- Coluna calculada para relatórios (opcional)
    is_ended BOOLEAN GENERATED ALWAYS AS (end_time IS NOT NULL) STORED,
    
    PRIMARY KEY (id),
    UNIQUE KEY uq_session_uuid (session_uuid),
    KEY idx_camera_id (camera_id),
    KEY idx_start_time (start_time),
    KEY idx_connection_status (connection_status),
    KEY idx_camera_status (camera_id, connection_status),
    KEY idx_duration (duration_seconds),
    KEY idx_is_ended (is_ended),
    KEY idx_start_end (start_time, end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Sessões de conexão das câmeras';

-- -----------------------------------------------------
-- TABELA: system_config (Configurações do Sistema)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS system_config (
    id SMALLINT UNSIGNED AUTO_INCREMENT,
    config_key VARCHAR(100) NOT NULL,
    config_value JSON NOT NULL,
    config_type ENUM('string', 'number', 'boolean', 'array', 'object') NOT NULL,
    description VARCHAR(500) DEFAULT NULL,
    is_active TINYINT(1) DEFAULT 1,
    updated_by VARCHAR(50) DEFAULT 'system',
    created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_config_key (config_key),
    KEY idx_is_active (is_active),
    KEY idx_config_type (config_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Configurações do sistema de tracking';

-- -----------------------------------------------------
-- TABELA: person_snapshots (Snapshots/Prints)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS person_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    person_uuid CHAR(36) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size INT UNSIGNED DEFAULT 0,
    resolution VARCHAR(20) DEFAULT NULL,
    format VARCHAR(10) DEFAULT 'png',
    capture_time TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
    camera_id VARCHAR(50) DEFAULT NULL,
    dominant_color CHAR(7) DEFAULT NULL,
    is_face_visible TINYINT(1) DEFAULT 1,
    quality_score DECIMAL(3,2) DEFAULT 1.00,
    is_archived TINYINT(1) DEFAULT 0,
    archive_path VARCHAR(512) DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_person_uuid (person_uuid),
    KEY idx_capture_time (capture_time),
    KEY idx_camera_id (camera_id),
    KEY idx_quality_score (quality_score),
    KEY idx_is_archived (is_archived),
    KEY idx_person_quality (person_uuid, quality_score),
    CONSTRAINT chk_quality_score CHECK (quality_score >= 0 AND quality_score <= 1),
    CONSTRAINT chk_dominant_color CHECK (dominant_color IS NULL OR dominant_color REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Registro de snapshots das pessoas';

-- -----------------------------------------------------
-- TABELA: alert_snapshots (Capturas de Alertas)
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS alert_snapshots (
    id INT AUTO_INCREMENT,
    person_uuid CHAR(36) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    zone VARCHAR(100) DEFAULT NULL,
    time_in_zone INT DEFAULT 0,
    file_path VARCHAR(512) DEFAULT NULL,
    camera_id VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_alert_person_uuid (person_uuid),
    KEY idx_alert_created_at (created_at),
    CONSTRAINT fk_alert_person_uuid FOREIGN KEY (person_uuid) REFERENCES person_cache(person_uuid) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Registro de snapshots e dados de alertas';

-- -----------------------------------------------------
-- ÍNDICES ADICIONAIS
-- -----------------------------------------------------
CREATE INDEX idx_cache_active_recent ON person_cache (is_active, last_seen DESC, confidence_score DESC);
CREATE INDEX idx_cache_features ON person_cache (height_ratio, aspect_ratio);
CREATE INDEX idx_cache_cleanup ON person_cache (is_active, last_seen);
CREATE INDEX idx_occurrences_person_time ON person_occurrences (person_uuid, detection_time DESC);
CREATE INDEX idx_occurrences_recent ON person_occurrences (detection_time DESC, camera_id);
CREATE INDEX idx_occurrences_cleanup ON person_occurrences (detection_date, camera_id);
CREATE INDEX idx_sessions_camera_active ON camera_sessions (camera_id, connection_status, start_time DESC);

-- -----------------------------------------------------
-- STORED PROCEDURES
-- -----------------------------------------------------
DELIMITER //

CREATE PROCEDURE sp_update_person_cache(
    IN p_person_uuid CHAR(36),
    IN p_height_ratio DECIMAL(5,4),
    IN p_color_profile JSON,
    IN p_confidence DECIMAL(3,2)
)
BEGIN
    UPDATE person_cache 
    SET 
        last_seen = CURRENT_TIMESTAMP(3),
        height_ratio = COALESCE(p_height_ratio, height_ratio),
        color_profile = COALESCE(p_color_profile, color_profile),
        confidence_score = GREATEST(0.1, LEAST(1.0, 
            confidence_score * 0.8 + COALESCE(p_confidence, 0.5) * 0.2
        )),
        total_appearances = total_appearances + 1,
        snapshot_count = snapshot_count + 1
    WHERE person_uuid = p_person_uuid;
END //

CREATE PROCEDURE sp_find_similar_person(
    IN p_height_ratio DECIMAL(5,4),
    IN p_color_r TINYINT UNSIGNED,
    IN p_color_g TINYINT UNSIGNED,
    IN p_color_b TINYINT UNSIGNED,
    IN p_min_confidence DECIMAL(3,2),
    IN p_max_results INT
)
BEGIN
    SELECT 
        pc.person_uuid,
        pc.confidence_score,
        pc.last_seen,
        pc.snapshot_path,
        (
            (1.0 - ABS(pc.height_ratio - p_height_ratio)) * 0.4 +
            (
                (1.0 - ABS(JSON_EXTRACT(pc.color_profile, '$.r') - p_color_r) / 255.0) * 0.2 +
                (1.0 - ABS(JSON_EXTRACT(pc.color_profile, '$.g') - p_color_g) / 255.0) * 0.2 +
                (1.0 - ABS(JSON_EXTRACT(pc.color_profile, '$.b') - p_color_b) / 255.0) * 0.2
            )
        ) AS similarity_score
    FROM person_cache pc
    WHERE pc.is_active = 1
        AND pc.last_seen > NOW() - INTERVAL 30 MINUTE
        AND pc.confidence_score >= p_min_confidence
        AND pc.height_ratio BETWEEN p_height_ratio - 0.1 AND p_height_ratio + 0.1
    ORDER BY similarity_score DESC
    LIMIT p_max_results;
END //

CREATE PROCEDURE sp_cleanup_old_data(
    IN p_days_to_keep INT
)
BEGIN
    DECLARE v_cutoff_date DATE;
    DECLARE v_occurrences_deleted INT;
    
    SET v_cutoff_date = CURDATE() - INTERVAL p_days_to_keep DAY;
    
    -- Marcar pessoas inativas
    UPDATE person_cache 
    SET is_active = 0 
    WHERE is_active = 1 
        AND last_seen < NOW() - INTERVAL 7 DAY;
    
    -- Deletar ocorrências antigas
    DELETE FROM person_occurrences 
    WHERE detection_date < v_cutoff_date;
    
    SET v_occurrences_deleted = ROW_COUNT();
    
    -- Arquivar snapshots antigos
    UPDATE person_snapshots 
    SET is_archived = 1,
        archive_path = CONCAT('archive/', file_path)
    WHERE capture_time < NOW() - INTERVAL 30 DAY
        AND is_archived = 0;
    
    SELECT 
        ROW_COUNT() AS persons_deactivated,
        v_occurrences_deleted AS occurrences_deleted;
END //

DELIMITER ;

-- -----------------------------------------------------
-- TRIGGERS
-- -----------------------------------------------------
DELIMITER //

-- Trigger para atualizar total_appearances
CREATE TRIGGER trg_after_occurrence_insert
AFTER INSERT ON person_occurrences
FOR EACH ROW
BEGIN
    UPDATE person_cache 
    SET total_appearances = total_appearances + 1
    WHERE person_uuid = NEW.person_uuid;
END //

-- Trigger para popular detection_date automaticamente
CREATE TRIGGER trg_before_occurrence_insert_date
BEFORE INSERT ON person_occurrences
FOR EACH ROW
BEGIN
    -- Se detection_date não foi fornecida, usa a data de detection_time
    IF NEW.detection_date IS NULL OR NEW.detection_date = '0000-00-00' THEN
        SET NEW.detection_date = DATE(NEW.detection_time);
    END IF;
END //

-- Trigger para finalizar sessão
CREATE TRIGGER trg_before_camera_session_update
BEFORE UPDATE ON camera_sessions
FOR EACH ROW
BEGIN
    IF NEW.connection_status IN ('lost', 'manual_stop') AND OLD.connection_status = 'active' THEN
        SET NEW.end_time = CURRENT_TIMESTAMP(3);
    END IF;
END //

DELIMITER ;

-- -----------------------------------------------------
-- VIEWS
-- -----------------------------------------------------
CREATE OR REPLACE VIEW vw_active_persons AS
SELECT 
    pc.person_uuid,
    pc.first_seen,
    pc.last_seen,
    pc.total_appearances,
    pc.confidence_score,
    pc.snapshot_path,
    TIMESTAMPDIFF(MINUTE, pc.first_seen, pc.last_seen) AS total_minutes_active,
    (
        SELECT po.camera_id 
        FROM person_occurrences po 
        WHERE po.person_uuid = pc.person_uuid 
        ORDER BY po.detection_time DESC 
        LIMIT 1
    ) AS last_camera_seen,
    (
        SELECT COUNT(DISTINCT camera_id) 
        FROM person_occurrences po 
        WHERE po.person_uuid = pc.person_uuid
    ) AS distinct_cameras_count
FROM person_cache pc
WHERE pc.is_active = 1
    AND pc.last_seen > NOW() - INTERVAL 1 HOUR
ORDER BY pc.last_seen DESC;

CREATE OR REPLACE VIEW vw_camera_stats_24h AS
SELECT 
    camera_id,
    COUNT(DISTINCT person_uuid) AS unique_persons,
    COUNT(*) AS total_detections,
    MIN(detection_time) AS first_detection,
    MAX(detection_time) AS last_detection,
    AVG(detection_confidence) AS avg_confidence,
    (
        SELECT HOUR(detection_time)
        FROM person_occurrences sub
        WHERE sub.camera_id = po.camera_id
            AND sub.detection_time > NOW() - INTERVAL 24 HOUR
        GROUP BY HOUR(detection_time)
        ORDER BY COUNT(*) DESC
        LIMIT 1
    ) AS peak_hour
FROM person_occurrences po
WHERE detection_time > NOW() - INTERVAL 24 HOUR
GROUP BY camera_id
ORDER BY total_detections DESC;

-- -----------------------------------------------------
-- CONFIGURAÇÕES INICIAIS
-- -----------------------------------------------------
INSERT INTO system_config (config_key, config_value, config_type, description) VALUES
('reidentification.threshold', '0.65', 'number', 'Threshold mínimo para reidentificação'),
('cache.ttl_minutes', '30', 'number', 'TTL do cache em minutos'),
('snapshot.quality_threshold', '0.7', 'number', 'Threshold de qualidade para salvar snapshot'),
('cleanup.keep_days', '90', 'number', 'Dias para manter dados históricos'),
('camera.reconnect_timeout', '60', 'number', 'Timeout de reconexão (segundos)'),
('feature.extraction.enabled', 'true', 'boolean', 'Habilita extração de características'),
('debug.mode', 'false', 'boolean', 'Modo debug para logs detalhados')
ON DUPLICATE KEY UPDATE 
    config_value = VALUES(config_value),
    updated_at = CURRENT_TIMESTAMP(3);

-- -----------------------------------------------------
-- USUÁRIO DA APLICAÇÃO
-- -----------------------------------------------------
CREATE USER IF NOT EXISTS 'tracking_app'@'localhost' IDENTIFIED BY 'SenhaSegura123!';
GRANT SELECT, INSERT, UPDATE, DELETE ON person_tracking_db.* TO 'tracking_app'@'localhost';
GRANT EXECUTE ON person_tracking_db.* TO 'tracking_app'@'localhost';
GRANT SELECT ON person_tracking_db.vw_active_persons TO 'tracking_app'@'localhost';
GRANT SELECT ON person_tracking_db.vw_camera_stats_24h TO 'tracking_app'@'localhost';
FLUSH PRIVILEGES;

-- -----------------------------------------------------
--CRIAR VIEW DE CALCULO
-- -----------------------------------------------------

-- View para calcular duration dinamicamente
CREATE OR REPLACE VIEW vw_camera_sessions_with_duration AS
SELECT 
    cs.*,
    CASE 
        WHEN cs.end_time IS NOT NULL THEN 
            TIMESTAMPDIFF(SECOND, cs.start_time, cs.end_time)
        ELSE 
            TIMESTAMPDIFF(SECOND, cs.start_time, NOW())
    END AS calculated_duration_seconds,
    CASE 
        WHEN cs.end_time IS NOT NULL THEN 'ended'
        ELSE 'active'
    END AS session_state
FROM camera_sessions cs;

------------------------------------------------------
----------------------------------------------------
-- SCRIPT RAPIDO
-------------------------------------------------------
-----------------------------------------------------

-- Script mínimo para criar o essencial
CREATE DATABASE IF NOT EXISTS person_tracking_db;
USE person_tracking_db;

-- Tabela principal (simplificada)
CREATE TABLE person_cache (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    person_uuid CHAR(36) NOT NULL UNIQUE,
    color_profile JSON,
    height_ratio DECIMAL(5,4),
    snapshot_path VARCHAR(255),
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE person_occurrences (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    person_uuid CHAR(36) NOT NULL,
    camera_id VARCHAR(50),
    detection_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    detection_date DATE,
    bbox JSON,
    detection_confidence DECIMAL(4,3)
);

CREATE TABLE IF NOT EXISTS alert_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_uuid CHAR(36) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    zone VARCHAR(100),
    time_in_zone INT DEFAULT 0,
    file_path VARCHAR(512),
    camera_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_alert_person (person_uuid)
);

-- Usuário para a aplicação
CREATE USER IF NOT EXISTS 'tracking_app'@'localhost' IDENTIFIED BY 'SenhaSegura123!';
GRANT ALL ON person_tracking_db.* TO 'tracking_app'@'localhost';
FLUSH PRIVILEGES;

-- -----------------------------------------------------
-- FINALIZAR
-- -----------------------------------------------------
SET FOREIGN_KEY_CHECKS = 1;

-- Verificar criação
SELECT '=== TABELAS CRIADAS ===' AS info;
SHOW TABLES;

SELECT '=== BANCO CRIADO COM SUCESSO! ===' AS finalizado;