-- 可选: 变更审计表。MVP 不建; 需要时在主脚本之后执行。
-- 对应文档: ../原子能力注册表设计.md 第 2 节、6.5。

-- ============ 5. 变更审计(谁在何时改了什么) ============
CREATE TABLE registry_audit_log (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  entity_type  VARCHAR(24)  NOT NULL COMMENT 'capability|version|ref',
  entity_id    BIGINT UNSIGNED NOT NULL,
  action       VARCHAR(24)  NOT NULL,
  before_json  JSON         NULL,
  after_json   JSON         NULL,
  operator     VARCHAR(64)  NOT NULL,
  request_id   VARCHAR(64)  NULL,
  created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_entity (entity_type, entity_id, created_at),
  KEY idx_operator (operator, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='注册表审计日志, 只追加';
