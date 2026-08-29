-- Run as system_a_owner after `alembic upgrade head`.
REVOKE ALL ON SCHEMA evaluation FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM PUBLIC;
REVOKE ALL ON SCHEMA evaluation FROM system_a_api;
REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM system_a_api;

GRANT USAGE ON SCHEMA platform TO system_a_api;
GRANT SELECT ON TABLE platform.dataset_versions TO system_a_api;
GRANT SELECT ON TABLE public.alembic_version TO system_a_api;
GRANT USAGE ON SCHEMA reporting TO system_a_api;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO system_a_api;

GRANT USAGE ON SCHEMA platform, evaluation TO system_a_generator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA platform TO system_a_generator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA evaluation TO system_a_generator;

GRANT USAGE ON SCHEMA platform, evaluation TO system_a_evaluator;
GRANT SELECT ON TABLE platform.dataset_versions TO system_a_evaluator;
GRANT SELECT ON ALL TABLES IN SCHEMA evaluation TO system_a_evaluator;
GRANT USAGE ON SCHEMA reporting TO system_a_evaluator;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO system_a_evaluator;

ALTER DEFAULT PRIVILEGES FOR ROLE system_a_owner IN SCHEMA platform
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO system_a_generator;
ALTER DEFAULT PRIVILEGES FOR ROLE system_a_owner IN SCHEMA evaluation
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO system_a_generator;
ALTER DEFAULT PRIVILEGES FOR ROLE system_a_owner IN SCHEMA evaluation
    GRANT SELECT ON TABLES TO system_a_evaluator;
ALTER DEFAULT PRIVILEGES FOR ROLE system_a_owner IN SCHEMA reporting
    GRANT SELECT ON TABLES TO system_a_api, system_a_evaluator;
