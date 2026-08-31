-- ─────────────────────────────────────────────────────────────────────
-- Schema delta — POST_ATTACHMENTS columns required by data_router's
-- storage subsystem.
--
-- Targets V3.13 (TEAM/AREA SNAP columns). POST_ATTACHMENTS is NOT in
-- the V3.13 SNAP-affected list (only POSTS / POST_COMMENTS / POST_REACTIONS
-- among community tables got SNAP_TEAM_ID + SNAP_AREA_ID). So this
-- delta is independent of V3.13 and can be applied before or after.
--
-- Apply order (idempotent):
--   1. ALTER TABLE statements below
--   2. Drop the existing 15-day archive lifecycle policy on the
--      OCI bucket "univ_attachments" (see "OCI bucket cleanup" at the
--      end of this file).
--
-- These additions are NULL-tolerant for backfill safety; once the
-- router writes new attachments, the columns will be populated. Rows
-- created before this delta keep working — only the canonical URL
-- field needs to remain readable.
-- ─────────────────────────────────────────────────────────────────────

ALTER TABLE POST_ATTACHMENTS ADD (
  STORAGE_ID    VARCHAR2(300 CHAR),                  -- "o:univ_attachments/2026/04/<uuid>.png" or "b:ab/<uuid>.png"
  BACKEND       VARCHAR2(20 CHAR),                   -- "oci_os" | "block"
  BUCKET_NAME   VARCHAR2(100 CHAR),                  -- non-null only when BACKEND='oci_os'
  OBJECT_KEY    VARCHAR2(200 CHAR),                  -- backend-specific key
  BYTE_SIZE     NUMBER(19),
  CONTENT_TYPE  VARCHAR2(100 CHAR),
  SHA256        VARCHAR2(64 CHAR)
);

ALTER TABLE POST_ATTACHMENTS
  ADD CONSTRAINT CK_PA_BACKEND
      CHECK (BACKEND IS NULL OR BACKEND IN ('oci_os','block'));

-- ─────────────────────────────────────────────────────────────────────
-- URL 컬럼 NULL 허용 (2026-05-12)
-- ─────────────────────────────────────────────────────────────────────
-- 신규 row 는 STORAGE_ID 만 채우는 게 정상. legacy URL 컬럼은 보존 (구 데이터),
-- 단 NOT NULL 제약을 풀어서 STORAGE_ID-only INSERT 를 허용.
--
-- 아직 적용 전이면 main 의 board.postCreate 는 URL 에 `storage:<id>` placeholder
-- 박는 우회 사용. 적용 후엔 placeholder 제거 + URL NULL 로 INSERT 변경.
ALTER TABLE POST_ATTACHMENTS MODIFY (URL VARCHAR2(2000 CHAR) NULL);

-- Index for backend-level analytics (e.g. "how much have we written to
-- block since OS hit threshold?"). Cheap, single-column.
CREATE INDEX IX_PA_BACKEND ON POST_ATTACHMENTS (BACKEND);

-- Optional: deduplication / integrity. SHA256 is unique per content,
-- but the same image attached to two posts is legitimate, so we don't
-- enforce uniqueness — just index for ad-hoc lookups.
CREATE INDEX IX_PA_SHA256 ON POST_ATTACHMENTS (SHA256);

-- ─────────────────────────────────────────────────────────────────────
-- Notes for any other table that holds attachment URLs
-- ─────────────────────────────────────────────────────────────────────
-- The schema's "첨부 URL" domain type currently lives only in
-- POST_ATTACHMENTS. If we later add attachments to PROSPECT_HISTORY,
-- DAILY_REPORTS, etc., apply the same column set there.

-- ─────────────────────────────────────────────────────────────────────
-- OCI bucket cleanup (run from a shell with OCI CLI configured)
-- ─────────────────────────────────────────────────────────────────────
-- The bucket univ_attachments was created with a 15-day Archive
-- lifecycle policy. data_router's design no longer uses Archive — drop
-- the policy so new uploads stay in Standard.
--
-- Bash:
--   oci os object-lifecycle-policy delete \
--     -ns axcrgpzz5ity --bucket-name univ_attachments --force
--
-- Existing objects: bucket is currently empty (verified 2026-05-03);
-- safe to drop without restoring anything.

-- ─────────────────────────────────────────────────────────────────────
-- V3.17 (2026-05-11) — TELEGRAM_PAIRINGS (페어링 코드 방식)
-- ─────────────────────────────────────────────────────────────────────
-- 어드민이 채팅방 chat_id 를 직접 입력하던 방식 (TelegramConnectModal
-- 의 input 필드) 을 폐기. 대신 `/pair {code}` 슬래시 명령으로 봇이
-- chat_id + title 회수.
--
-- fresh install: sql/04_telegram.sql 에 동기화됨.
--
-- 운영 ATP 적용 (Phase 16-A):
--   migration/19_telegram_pairings.py 또는 data_router /v1/exec 호출로
--   아래 DDL 일괄 실행. 기존 BROADCAST_SETTINGS row 영향 0 (새 테이블
--   추가만, 컬럼 변경 X).
--
-- CREATE TABLE TELEGRAM_PAIRINGS (
--   CODE              VARCHAR2(16 CHAR)            NOT NULL,
--   TEAM_ID           VARCHAR2(30 CHAR)            NOT NULL,
--   CHANNEL_TYPE      VARCHAR2(30 CHAR)            NOT NULL,
--   ISSUED_BY_SABUN   VARCHAR2(20 CHAR)            NOT NULL,
--   ISSUED_AT         TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
--   EXPIRES_AT        TIMESTAMP(6) WITH TIME ZONE  NOT NULL,
--   COMPLETED_AT      TIMESTAMP(6) WITH TIME ZONE,
--   CHAT_ID           VARCHAR2(50 CHAR),
--   CHAT_TITLE        VARCHAR2(200 CHAR),
--   CREATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
--   UPDATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
--   SCHEMA_VERSION    NUMBER(3)                    DEFAULT 1 NOT NULL,
--   CONSTRAINT PK_TELEGRAM_PAIRINGS PRIMARY KEY (CODE),
--   CONSTRAINT FK_TP_TEAM   FOREIGN KEY (TEAM_ID)         REFERENCES TEAMS(TEAM_ID),
--   CONSTRAINT FK_TP_SABUN  FOREIGN KEY (ISSUED_BY_SABUN) REFERENCES USERS(SABUN)
-- ) ORGANIZATION INDEX;
--
-- CREATE UNIQUE INDEX UQ_TP_ACTIVE ON TELEGRAM_PAIRINGS (
--   CASE WHEN COMPLETED_AT IS NULL THEN TEAM_ID || '|' || CHANNEL_TYPE END
-- );
--
-- CREATE INDEX IX_TP_PENDING ON TELEGRAM_PAIRINGS (COMPLETED_AT, EXPIRES_AT);
--
-- 추가 변경: BROADCAST_SETTINGS.config JSON 에 새 키 추가 (스키마 변경
-- 아닌 application-level convention):
--   {channelType}ChatTitle: 봇이 회수한 텔레그램 방 제목. UI 에서 chat_id
--     대신 표시. 미연결 시 NULL.
-- 기존 {channelType}ChatId 와 같은 row 의 CONFIG CLOB 안에서 함께 저장.
-- 따라서 SQL DDL 변경 없음 — application 코드만 정합 (Phase 16-B-3
-- (pair-complete 핸들러), Phase 16-D-3 (TelegramConnectModal)).
