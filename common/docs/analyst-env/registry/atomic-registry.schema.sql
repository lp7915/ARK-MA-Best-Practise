-- 原子能力注册表 · MySQL 8.0 · utf8mb4
-- 约定: 所有表 InnoDB; 时间一律 DATETIME(3) UTC; 主键为自增 BIGINT; 对外标识用业务键(atomic_id 等)
-- 对应文档: ../原子能力注册表设计.md 第 2 节。改动表结构须同步更新该节。
-- 校验: 语法已用 sqlglot(mysql 方言)解析通过; 约束与查询逻辑已用等价的 sqlite 夹具验证。
--       尚未在真实 MySQL 8.0 上执行, 上线前必须在测试库实跑一遍。

-- ============ 1. 原子能力(身份, 不随版本变化) ============
CREATE TABLE atomic_capability (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  atomic_id     VARCHAR(96)  NOT NULL COMMENT '业务标识 <owner_topic>.<name>, 全局唯一, 创建后不可变',
  owner_topic   VARCHAR(24)  NOT NULL COMMENT '提供该能力的业务线 ID, 或中台保留标识 platform; 与 atomic_id 前缀一致, 冗余便于查询',
  name          VARCHAR(64)  NOT NULL COMMENT '名称(人读)',
  type          VARCHAR(16)  NOT NULL COMMENT 'skill|tool|mcp|knowledge|template|prompt',
  team          VARCHAR(64)  NOT NULL COMMENT '提供团队',
  owner_primary VARCHAR(64)  NOT NULL COMMENT '主责任人',
  owner_backup  VARCHAR(64)  NOT NULL COMMENT '备份责任人',
  description   VARCHAR(512) NOT NULL COMMENT '何时用/做什么/输入输出, 面向选用者',
  status        VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active|archived, 能力整体状态',
  latest_released_version_id BIGINT UNSIGNED NULL COMMENT '当前最新 released 的版本, 冗余加速查询',
  created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_atomic_id (atomic_id),
  KEY idx_team (team),
  KEY idx_type_status (type, status),
  KEY idx_owner_topic (owner_topic)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='原子能力主表';

-- ============ 2. 原子能力版本(内容不可变) ============
CREATE TABLE atomic_capability_version (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  capability_id  BIGINT UNSIGNED NOT NULL COMMENT '-> atomic_capability.id',
  version        VARCHAR(32)  NOT NULL COMMENT '语义化 主.次.修订',
  ver_major      INT UNSIGNED NOT NULL,
  ver_minor      INT UNSIGNED NOT NULL,
  ver_patch      INT UNSIGNED NOT NULL,
  fingerprint    CHAR(64)     NOT NULL COMMENT '内容指纹 SHA-256 十六进制',
  address        JSON         NOT NULL COMMENT '能力地址, 结构随 type 不同, 见规范 5.3',
  depends_on     JSON         NULL COMMENT '[{atomic_id, range}]',
  compat         JSON         NULL COMMENT '{ma_toolset, models, ma_docs_snapshot}',
  credentials    JSON         NULL COMMENT '[{kind, purpose}] 只写类型与用途, 不含值',
  changelog      VARCHAR(1024) NOT NULL DEFAULT '',
  status         VARCHAR(16)  NOT NULL DEFAULT 'draft' COMMENT 'draft|candidate|released|deprecated|retired; 预留 in_review|rejected(审核未启用,API 开关默认关闭)',
  deprecated_at  DATETIME(3)  NULL,
  retire_after   DATETIME(3)  NULL COMMENT '计划下线时间',
  replaced_by_version_id BIGINT UNSIGNED NULL COMMENT '建议替代版本',
  created_by     VARCHAR(64)  NOT NULL,
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_cap_version (capability_id, version),
  KEY idx_cap_semver (capability_id, ver_major, ver_minor, ver_patch),
  KEY idx_status (status),
  KEY idx_fingerprint (fingerprint),
  CONSTRAINT fk_ver_cap FOREIGN KEY (capability_id) REFERENCES atomic_capability(id),
  CONSTRAINT fk_ver_replaced FOREIGN KEY (replaced_by_version_id) REFERENCES atomic_capability_version(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='原子能力版本表; released 后内容字段不可变';

-- 主表 -> 版本表 的反向外键(放在版本表建好之后)
ALTER TABLE atomic_capability
  ADD CONSTRAINT fk_cap_latest FOREIGN KEY (latest_released_version_id) REFERENCES atomic_capability_version(id);

-- ============ 3. 原子能力 ↔ Agent 关联(被谁引用) ============
CREATE TABLE capability_agent_ref (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  capability_id  BIGINT UNSIGNED NOT NULL COMMENT '-> atomic_capability.id',
  topic          VARCHAR(24)  NOT NULL COMMENT '业务线',
  employee       VARCHAR(24)  NOT NULL COMMENT '数字员工',
  agent_role     VARCHAR(64)  NOT NULL COMMENT 'coordinator 或 subagent:<名称>',
  stage          VARCHAR(8)   NOT NULL COMMENT 'dev|staging|prod',
  version_range  VARCHAR(64)  NOT NULL COMMENT '业务方声明的可接受范围, 如 ^1.2.0',
  pinned_version_id BIGINT UNSIGNED NULL COMMENT '当前锁定版本; 声明后尚未发布时为空',
  ma_agent_id    VARCHAR(64)  NULL COMMENT '该智能体在 MA 上的 Agent ID(锁定后回填)',
  status         VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active|removed',
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_ref (capability_id, topic, employee, agent_role, stage),
  KEY idx_agent (topic, employee, agent_role, stage),
  KEY idx_pinned (pinned_version_id),
  KEY idx_ma_agent (ma_agent_id),
  CONSTRAINT fk_ref_cap FOREIGN KEY (capability_id) REFERENCES atomic_capability(id),
  CONSTRAINT fk_ref_pinned FOREIGN KEY (pinned_version_id) REFERENCES atomic_capability_version(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='原子能力被哪个智能体引用, 以及锁定在哪个版本';

-- ============ 4. 引用锁定历史(升级/回滚追溯) ============
CREATE TABLE capability_agent_ref_history (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ref_id          BIGINT UNSIGNED NOT NULL,
  from_version_id BIGINT UNSIGNED NULL,
  to_version_id   BIGINT UNSIGNED NULL,
  action          VARCHAR(16)  NOT NULL COMMENT 'declare|pin|upgrade|rollback|remove',
  reason          VARCHAR(256) NOT NULL DEFAULT '',
  operator        VARCHAR(64)  NOT NULL,
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_ref (ref_id, created_at),
  CONSTRAINT fk_hist_ref FOREIGN KEY (ref_id) REFERENCES capability_agent_ref(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='引用锁定变更历史';

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
